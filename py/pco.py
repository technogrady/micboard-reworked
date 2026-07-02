"""Planning Center Online (PCO) Services integration.

Pulls the scheduled roster for the upcoming service from Planning Center and writes
each person's name onto the matching Micboard slot (via config.update_slot -> the
existing `extended_name` field).

Design notes for self-hosted, open-source installs:
  * Auth is a Personal Access Token (App ID + Secret) supplied per-install. No OAuth,
    no callback URL, no shared secret in the repo.
  * Credentials live ONLY in a separate `pco.env` file (or PCO_APP_ID / PCO_SECRET
    environment variables) read by this backend. They are never written into
    config.json and never served over /data.json.
  * The non-secret mapping config (which PCO team fills which Micboard group, etc.)
    lives in config_tree['pco'] and is safe to serve to the browser.
"""

import os
import re
import json
import base64
import logging
import datetime
from urllib.parse import urlencode

from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado import ioloop

import config

BASE_URL = 'https://api.planningcenteronline.com/services/v2'
CRED_FILE_NAME = 'pco.env'

# keys allowed to be persisted into config_tree['pco'] — guards against a client
# ever sneaking credentials into the served config.
ALLOWED_CONFIG_KEYS = {
    'service_type_id', 'service_type_name', 'auto_poll', 'poll_interval',
    'mappings', 'last_synced',
}

_poller = None


class PCOError(Exception):
    """Raised for any Planning Center request/config problem; carries an HTTP code."""
    def __init__(self, message, code=502):
        super().__init__(message)
        self.message = message
        self.code = code


# --------------------------------------------------------------------------- #
# Credentials (secret — never enters config_tree / data.json)
# --------------------------------------------------------------------------- #

def credentials_file():
    return os.path.join(os.path.dirname(config.config_file()), CRED_FILE_NAME)


def load_credentials():
    """Return (app_id, secret) from the environment or pco.env, else None."""
    app_id = os.environ.get('PCO_APP_ID')
    secret = os.environ.get('PCO_SECRET')
    if app_id and secret:
        return (app_id, secret)

    path = credentials_file()
    if not os.path.exists(path):
        return None

    app_id = secret = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key, value = key.strip(), value.strip()
            if key == 'PCO_APP_ID':
                app_id = value
            elif key == 'PCO_SECRET':
                secret = value

    if app_id and secret:
        return (app_id, secret)
    return None


def save_credentials(app_id, secret):
    path = credentials_file()
    with open(path, 'w') as f:
        f.write('# Planning Center Online personal access token — DO NOT COMMIT.\n')
        f.write('PCO_APP_ID={}\n'.format(app_id))
        f.write('PCO_SECRET={}\n'.format(secret))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def is_configured():
    return load_credentials() is not None


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #

async def _get(path, params=None):
    creds = load_credentials()
    if not creds:
        raise PCOError('Planning Center credentials are not configured.', 400)
    app_id, secret = creds

    url = BASE_URL + path
    if params:
        url += '?' + urlencode(params)

    token = base64.b64encode('{}:{}'.format(app_id, secret).encode()).decode()
    request = HTTPRequest(
        url, method='GET',
        headers={'Authorization': 'Basic ' + token, 'Accept': 'application/json'},
        connect_timeout=10, request_timeout=20,
    )

    try:
        resp = await AsyncHTTPClient().fetch(request, raise_error=False)
    except Exception as exc:  # noqa: BLE001 — DNS/TLS/connection failures
        raise PCOError('Could not reach Planning Center: {}'.format(exc), 502)

    if resp.code == 401:
        raise PCOError('Planning Center rejected the credentials (401).', 401)
    if resp.code == 429:
        raise PCOError('Planning Center rate limit reached (429) — try again shortly.', 429)
    if resp.code < 200 or resp.code >= 300:
        raise PCOError('Planning Center API error (HTTP {}).'.format(resp.code), 502)

    try:
        return json.loads(resp.body)
    except (ValueError, TypeError) as exc:
        raise PCOError('Unexpected response from Planning Center: {}'.format(exc), 502)


async def _get_all(path, params=None):
    """Follow Services v2 offset pagination; return (data_items, included_items)."""
    params = dict(params or {})
    params.setdefault('per_page', 100)
    items, included, offset = [], [], 0
    while True:
        params['offset'] = offset
        payload = await _get(path, params)
        items.extend(payload.get('data', []))
        included.extend(payload.get('included', []))
        nxt = (payload.get('meta') or {}).get('next') or {}
        if nxt.get('offset') is None:
            break
        offset = nxt['offset']
    return items, included


# --------------------------------------------------------------------------- #
# Read-through fetchers (used by the mapping UI)
# --------------------------------------------------------------------------- #

async def get_service_types():
    items, _ = await _get_all('/service_types')
    return [{'id': d['id'], 'name': (d['attributes'].get('name') or '').strip()}
            for d in items]


async def get_teams(service_type_id):
    teams, _ = await _get_all('/service_types/{}/teams'.format(service_type_id))
    positions, _ = await _get_all(
        '/service_types/{}/team_positions'.format(service_type_id),
        {'include': 'team'},
    )
    pos_by_team = {}
    for p in positions:
        team_data = ((p.get('relationships') or {}).get('team') or {}).get('data') or {}
        pos_by_team.setdefault(team_data.get('id'), []).append(p['attributes'].get('name'))

    return [{
        'id': t['id'],
        'name': (t['attributes'].get('name') or '').strip(),
        'positions': pos_by_team.get(t['id'], []),
    } for t in teams]


async def get_plans(service_type_id, count=8):
    payload = await _get(
        '/service_types/{}/plans'.format(service_type_id),
        {'filter': 'future', 'order': 'sort_date', 'per_page': count},
    )
    return [{
        'id': p['id'],
        'dates': p['attributes'].get('dates'),
        'sort_date': p['attributes'].get('sort_date'),
    } for p in payload.get('data', [])]


async def get_next_plan(service_type_id):
    plans = await get_plans(service_type_id, count=1)
    return plans[0] if plans else None


def _norm_status(raw):
    """Normalize PCO status ('C'/'U'/'D' or 'confirmed'/...) to a stable word."""
    if not raw:
        return 'unconfirmed'
    first = raw.strip().lower()[:1]
    if first == 'c':
        return 'confirmed'
    if first == 'd':
        return 'declined'
    return 'unconfirmed'


async def get_roster(service_type_id, plan_id):
    """Return a flat list of roster entries for a plan."""
    items, included = await _get_all(
        '/service_types/{}/plans/{}/team_members'.format(service_type_id, plan_id),
        {'include': 'person'},
    )
    people_attrs = {inc['id']: inc.get('attributes', {})
                    for inc in included if inc.get('type') == 'Person'}

    roster = []
    for d in items:
        attrs = d.get('attributes', {})
        rels = d.get('relationships', {})
        person_ref = (rels.get('person') or {}).get('data') or {}
        team_ref = (rels.get('team') or {}).get('data') or {}
        pid = person_ref.get('id') or d.get('id')
        pattr = people_attrs.get(pid, {})
        name = attrs.get('name') or '{} {}'.format(
            pattr.get('first_name', ''), pattr.get('last_name', '')).strip()
        # names end up in extended_name, which the frontend renders as HTML on
        # every dashboard — strip anything tag-like from this third-party data
        name = re.sub(r'[<>]', '', name)
        roster.append({
            'person_id': str(pid),
            'name': name,
            'first_name': pattr.get('first_name', ''),
            'last_name': pattr.get('last_name', ''),
            'position': attrs.get('team_position_name') or '',
            'team_id': str(team_ref.get('id') or ''),
            'status': _norm_status(attrs.get('status')),
        })
    return roster


# --------------------------------------------------------------------------- #
# Assignment logic
# --------------------------------------------------------------------------- #

def _natural_key(text):
    """Sort key so 'Mic 2' sorts before 'Mic 10'."""
    return [int(tok) if tok.isdigit() else tok.lower()
            for tok in re.split(r'(\d+)', text or '')]


def resolve_assignments(mapping, group, roster):
    """Pure function: decide which roster person lands on which slot.

    Returns {slot_number: {'name', 'person_id', 'status'}} for a single mapping.
    Pins (sticky person_id -> slot) win; everyone else fills remaining pool slots
    in a deterministic order.
    """
    pool = list(group.get('slots') or [])
    team_id = str(mapping.get('team_id') or '')
    positions = mapping.get('positions') or []
    status_filter = mapping.get('status_filter', 'confirmed')
    pins = mapping.get('pins') or {}

    people = []
    for r in roster:
        if team_id and r['team_id'] != team_id:
            continue
        if positions and r['position'] not in positions:
            continue
        if status_filter == 'confirmed' and r['status'] != 'confirmed':
            continue
        if status_filter == 'not_declined' and r['status'] == 'declined':
            continue
        people.append(r)

    assignments = {}
    used_slots = set()
    used_people = set()

    # Sticky pins first.
    for r in people:
        slot = pins.get(r['person_id'])
        if slot in pool and slot not in used_slots:
            assignments[slot] = {'name': r['name'], 'person_id': r['person_id'],
                                 'status': r['status']}
            used_slots.add(slot)
            used_people.add(r['person_id'])

    # Everyone else fills the remaining slots in a stable order.
    remaining_people = [r for r in people if r['person_id'] not in used_people]
    remaining_people.sort(key=lambda r: (_natural_key(r['position']),
                                          (r['last_name'] or r['name']).lower(),
                                          r['person_id']))
    remaining_slots = [s for s in pool if s not in used_slots]

    for r, slot in zip(remaining_people, remaining_slots):
        assignments[slot] = {'name': r['name'], 'person_id': r['person_id'],
                             'status': r['status']}

    return assignments


# --------------------------------------------------------------------------- #
# Config (non-secret) persistence
# --------------------------------------------------------------------------- #

def status():
    cfg = config.config_tree.get('pco') or {}
    return {
        'configured': is_configured(),
        'service_type_id': cfg.get('service_type_id'),
        'service_type_name': cfg.get('service_type_name'),
        'auto_poll': bool(cfg.get('auto_poll')),
        'poll_interval': cfg.get('poll_interval', 300),
        'last_synced': cfg.get('last_synced'),
        'mappings': cfg.get('mappings', []),
    }


def save_config(incoming):
    """Merge sanitized (secret-free) mapping config into config_tree['pco']."""
    cleaned = {k: v for k, v in (incoming or {}).items() if k in ALLOWED_CONFIG_KEYS}
    if 'poll_interval' in cleaned:
        try:
            cleaned['poll_interval'] = max(30, int(cleaned['poll_interval']))
        except (TypeError, ValueError):
            cleaned['poll_interval'] = 300
    cfg = config.config_tree.get('pco') or {}
    cfg.update(cleaned)
    config.config_tree['pco'] = cfg
    config.save_current_config()
    maybe_start_poller()
    return status()


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #

async def sync(plan_id=None):
    """Pull the roster for the target plan and write names onto pool slots."""
    cfg = config.config_tree.get('pco') or {}
    service_type_id = cfg.get('service_type_id')
    if not service_type_id:
        raise PCOError('No Planning Center service type is configured.', 400)
    if not is_configured():
        raise PCOError('Planning Center credentials are not configured.', 400)

    if not plan_id:
        plan = await get_next_plan(service_type_id)
        if not plan:
            raise PCOError('No upcoming plan found for the configured service type.', 404)
        plan_id = plan['id']

    roster = await get_roster(service_type_id, plan_id)

    results = []
    for mapping in cfg.get('mappings', []):
        group = config.get_group_by_number(mapping.get('group'))
        if not group:
            continue
        assignments = resolve_assignments(mapping, group, roster)
        for slot in (group.get('slots') or []):
            slot_cfg = config.get_slot_by_number(slot)
            if slot_cfg is None:
                continue  # group references a slot that isn't configured — skip
            info = assignments.get(slot)
            name = info['name'] if info else ''
            payload = {'slot': slot, 'extended_name': name}
            # preserve any manually-set extended_id (update_slot would otherwise clear it)
            if slot_cfg.get('extended_id'):
                payload['extended_id'] = slot_cfg['extended_id']
            config.update_slot(payload)
            results.append({
                'group': mapping.get('group'),
                'slot': slot,
                'name': name,
                'person_id': info['person_id'] if info else None,
                'status': info['status'] if info else None,
            })

    cfg['last_synced'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    config.config_tree['pco'] = cfg
    config.save_current_config()

    return {'plan_id': plan_id, 'assignments': results}


# --------------------------------------------------------------------------- #
# Optional background poller
# --------------------------------------------------------------------------- #

async def _poll_tick():
    try:
        await sync()
        logging.info('PCO auto-sync complete')
    except Exception as exc:  # noqa: BLE001 — poller must never crash the loop
        logging.warning('PCO auto-sync failed: %s', exc)


def maybe_start_poller():
    """Start/stop the auto-poll PeriodicCallback based on current config.

    Must be called from within the Tornado IOLoop thread.
    """
    global _poller
    if _poller:
        _poller.stop()
        _poller = None

    cfg = config.config_tree.get('pco') or {}
    if cfg.get('auto_poll') and is_configured():
        try:
            interval = max(30, int(cfg.get('poll_interval') or 300))
        except (TypeError, ValueError):  # hand-edited config.json
            interval = 300
        interval_ms = interval * 1000
        _poller = ioloop.PeriodicCallback(_poll_tick, interval_ms)
        _poller.start()
        logging.info('PCO auto-sync poller started (%ss)', interval_ms // 1000)
