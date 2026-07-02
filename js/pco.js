'use strict';

import { micboard, updateHash } from './app.js';
import { postJSON } from './data.js';

// Local working copy of the (non-secret) PCO config returned by /api/pco/status.
let pcoState = {
  configured: false,
  service_type_id: null,
  service_type_name: null,
  auto_poll: false,
  poll_interval: 300,
  last_synced: null,
  mappings: [],
};

let serviceTypes = [];
let teams = [];          // teams for the currently-selected service type
let serviceTypesError = null;  // last error from loading service types / teams
let handlersBound = false;

function getJSON(url) {
  return fetch(url).then(r => r.json());
}

function groups() {
  return (micboard.config && micboard.config.groups) || [];
}

function optionList(items, valueKey, labelFn, selected) {
  return items.map((it) => {
    const v = it[valueKey];
    const sel = String(v) === String(selected) ? ' selected' : '';
    return `<option value="${v}"${sel}>${labelFn(it)}</option>`;
  }).join('');
}

// --------------------------------------------------------------------------- //
// Loaders
// --------------------------------------------------------------------------- //

function loadStatus() {
  return getJSON('api/pco/status').then((data) => {
    pcoState = Object.assign(pcoState, data);
    pcoState.mappings = data.mappings || [];
  });
}

function loadServiceTypes() {
  serviceTypesError = null;
  return getJSON('api/pco/service_types').then((data) => {
    if (data && data.error) {
      serviceTypes = [];
      serviceTypesError = data.error;
      return;
    }
    serviceTypes = data.service_types || [];
  }).catch((err) => {
    serviceTypes = [];
    serviceTypesError = 'Could not reach the Micboard server: ' + err;
  });
}

function loadTeams() {
  if (!pcoState.service_type_id) {
    teams = [];
    return Promise.resolve();
  }
  return getJSON('api/pco/teams?service_type_id=' + encodeURIComponent(pcoState.service_type_id))
    .then((data) => {
      teams = (data && data.teams) || [];
      if (data && data.error) serviceTypesError = data.error;
    })
    .catch(() => { teams = []; });
}

// --------------------------------------------------------------------------- //
// Rendering
// --------------------------------------------------------------------------- //

function renderCredStatus() {
  const el = document.getElementById('pco-cred-status');
  if (pcoState.configured) {
    el.innerHTML = '<span class="pco-ok">&#10003; Connected to Planning Center</span>';
  } else {
    el.innerHTML = '<span class="pco-warn">Not connected — enter a Personal Access Token below.</span>';
  }
}

function renderServiceType() {
  const sel = document.getElementById('pco-service-type');
  sel.innerHTML = '<option value="">— choose a service type —</option>'
    + optionList(serviceTypes, 'id', s => s.name, pcoState.service_type_id);

  const err = document.getElementById('pco-service-type-error');
  if (err) {
    if (serviceTypesError) {
      err.innerHTML = '<span class="pco-warn">Couldn\'t load service types: ' + serviceTypesError
        + '</span><br><small class="pco-hint">Re-check the App ID and Secret above (a 401 usually '
        + 'means they were mistyped or swapped), then save the token again.</small>';
    } else if (pcoState.configured && !serviceTypes.length) {
      err.innerHTML = '<span class="pco-hint">No service types were returned for this account.</span>';
    } else {
      err.innerHTML = '';
    }
  }
}

function renderMappings() {
  const holder = document.getElementById('pco-mappings');
  holder.innerHTML = '';

  pcoState.mappings.forEach((m, idx) => {
    const div = document.createElement('div');
    div.className = 'pco-mapping';
    div.dataset.idx = idx;
    div.innerHTML = `
      <div class="form-row align-items-end">
        <div class="col">
          <label>PCO Team</label>
          <select class="form-control pco-m-team">
            <option value="">— team —</option>${optionList(teams, 'id', t => t.name, m.team_id)}
          </select>
        </div>
        <div class="col">
          <label>Micboard Group (mic pool)</label>
          <select class="form-control pco-m-group">
            <option value="">— group —</option>${optionList(groups(), 'group',
              g => `Group ${g.group}: ${g.title || ''} [${(g.slots || []).join(', ')}]`, m.group)}
          </select>
        </div>
        <div class="col">
          <label>Fill mode</label>
          <select class="form-control pco-m-mode">
            <option value="auto">Auto-assign</option>
            <option value="manual">Manual (pins only)</option>
          </select>
        </div>
        <div class="col">
          <label>Include</label>
          <select class="form-control pco-m-status">
            <option value="confirmed">Confirmed only</option>
            <option value="not_declined">All except declined</option>
            <option value="all">Everyone scheduled</option>
          </select>
        </div>
        <div class="col-auto">
          <button type="button" class="btn btn-sm btn-info pco-m-pins">Assign / Pins</button>
          <button type="button" class="btn btn-sm btn-danger pco-m-del">&times;</button>
        </div>
      </div>
      <div class="pco-pins" style="display:none"></div>`;
    holder.appendChild(div);
    div.querySelector('.pco-m-mode').value = m.mode || 'auto';
    div.querySelector('.pco-m-status').value = m.status_filter || 'confirmed';
  });
}

function renderFooter() {
  document.getElementById('pco-autopoll').checked = !!pcoState.auto_poll;
  document.getElementById('pco-interval').value = pcoState.poll_interval || 300;
  const last = document.getElementById('pco-last-synced');
  last.textContent = pcoState.last_synced
    ? 'Last synced: ' + new Date(pcoState.last_synced).toLocaleString()
    : 'Never synced';
}

function renderAll() {
  renderCredStatus();
  renderServiceType();
  renderMappings();
  renderFooter();
}

// --------------------------------------------------------------------------- //
// Pins / roster preview
// --------------------------------------------------------------------------- //

function slotOptions(pool, selected) {
  let opts = '<option value="">— auto —</option>';
  pool.forEach((s) => {
    const sel = String(s) === String(selected) ? ' selected' : '';
    opts += `<option value="${s}"${sel}>Slot ${s}</option>`;
  });
  return opts;
}

function openPins(idx, container) {
  const m = pcoState.mappings[idx];
  const group = groups().find(g => String(g.group) === String(m.group));
  if (!group) {
    container.innerHTML = '<p class="pco-warn">Pick a Micboard group first.</p>';
    container.style.display = 'block';
    return;
  }
  const pool = group.slots || [];
  container.innerHTML = '<p>Loading roster for the next plan…</p>';
  container.style.display = 'block';

  getJSON('api/pco/roster?service_type_id=' + encodeURIComponent(pcoState.service_type_id))
    .then((data) => {
      if (data.error) {
        container.innerHTML = '<p class="pco-warn">' + data.error + '</p>';
        return;
      }
      let roster = data.roster || [];
      if (m.team_id) {
        roster = roster.filter(r => String(r.team_id) === String(m.team_id));
      }
      if (!roster.length) {
        container.innerHTML = '<p>No one is scheduled on this team for the next plan.</p>';
        return;
      }
      m.pins = m.pins || {};
      let html = '<table class="pco-roster"><thead><tr>'
        + '<th>Person</th><th>Position</th><th>Status</th><th>Mic</th></tr></thead><tbody>';
      roster.forEach((r) => {
        html += `<tr data-person="${r.person_id}"><td>${r.name}</td><td>${r.position}</td>`
          + `<td>${r.status}</td><td><select class="form-control form-control-sm pco-pin">`
          + slotOptions(pool, m.pins[r.person_id]) + '</select></td></tr>';
      });
      html += '</tbody></table>';
      container.innerHTML = html;

      container.onchange = (ev) => {
        if (!ev.target.classList.contains('pco-pin')) return;
        const pid = ev.target.closest('tr').dataset.person;
        if (ev.target.value) {
          m.pins[pid] = parseInt(ev.target.value, 10);
        } else {
          delete m.pins[pid];
        }
      };
    });
}

// --------------------------------------------------------------------------- //
// Collect + save
// --------------------------------------------------------------------------- //

function collectMappings() {
  const rows = document.querySelectorAll('#pco-mappings .pco-mapping');
  const out = [];
  rows.forEach((row) => {
    const idx = parseInt(row.dataset.idx, 10);
    const prev = pcoState.mappings[idx] || {};
    const teamSel = row.querySelector('.pco-m-team');
    const teamId = teamSel.value;
    const group = parseInt(row.querySelector('.pco-m-group').value, 10);
    if (!teamId || !group) return;
    out.push({
      team_id: teamId,
      team_name: teamSel.options[teamSel.selectedIndex].text,
      group,
      mode: row.querySelector('.pco-m-mode').value,
      status_filter: row.querySelector('.pco-m-status').value,
      positions: prev.positions || [],
      pins: prev.pins || {},
    });
  });
  return out;
}

function saveMappings(callback) {
  const svcSel = document.getElementById('pco-service-type');
  const payload = {
    service_type_id: svcSel.value || null,
    service_type_name: svcSel.value ? svcSel.options[svcSel.selectedIndex].text : null,
    auto_poll: document.getElementById('pco-autopoll').checked,
    poll_interval: parseInt(document.getElementById('pco-interval').value, 10) || 300,
    mappings: collectMappings(),
  };
  postJSON('api/pco/mappings', payload, () => {
    if (callback) callback();
  });
}

function flash(message, ok) {
  const el = document.getElementById('pco-sync-result');
  el.innerHTML = '<span class="' + (ok ? 'pco-ok' : 'pco-warn') + '">' + message + '</span>';
}

function runSync() {
  flash('Syncing from Planning Center…', true);
  fetch('api/pco/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }).then(r => r.json()).then((data) => {
    if (data.error) {
      flash(data.error, false);
      return;
    }
    const n = (data.assignments || []).filter(a => a.name).length;
    flash('Assigned ' + n + ' mic(s). Reloading…', true);
    setTimeout(() => window.location.reload(), 900);
  }).catch((err) => flash('Sync failed: ' + err, false));
}

// --------------------------------------------------------------------------- //
// Wiring
// --------------------------------------------------------------------------- //

function bindHandlers() {
  if (handlersBound) return;
  handlersBound = true;

  $('#pco-cred-save').click(() => {
    const payload = {
      app_id: document.getElementById('pco-app-id').value.trim(),
      secret: document.getElementById('pco-secret').value.trim(),
    };
    if (!payload.app_id || !payload.secret) return;
    postJSON('api/pco/credentials', payload, () => {
      document.getElementById('pco-secret').value = '';
      loadStatus().then(loadServiceTypes).then(loadTeams).then(renderAll);
    });
  });

  $('#pco-service-type').on('change', function () {
    pcoState.service_type_id = this.value || null;
    pcoState.service_type_name = this.value ? this.options[this.selectedIndex].text : null;
    loadTeams().then(renderMappings);
  });

  $('#pco-add-mapping').click(() => {
    pcoState.mappings.push({ team_id: '', group: '', mode: 'auto', status_filter: 'confirmed', pins: {} });
    renderMappings();
  });

  // delegated controls inside the mapping list
  $('#pco-mappings').on('click', '.pco-m-del', function () {
    const idx = parseInt($(this).closest('.pco-mapping')[0].dataset.idx, 10);
    pcoState.mappings.splice(idx, 1);
    renderMappings();
  });

  $('#pco-mappings').on('click', '.pco-m-pins', function () {
    const row = $(this).closest('.pco-mapping')[0];
    const idx = parseInt(row.dataset.idx, 10);
    // sync the row's team/group choice into state before loading the roster
    pcoState.mappings[idx].team_id = row.querySelector('.pco-m-team').value;
    pcoState.mappings[idx].group = parseInt(row.querySelector('.pco-m-group').value, 10);
    openPins(idx, row.querySelector('.pco-pins'));
  });

  $('#pco-save').click(() => saveMappings(() => flash('Saved.', true)));

  $('#pco-sync').click(() => saveMappings(runSync));

  $('#pco-close').click(() => {
    micboard.settingsMode = 'NONE';
    updateHash();
    window.location.reload();
  });
}

export function initPcoEditor() {
  if (micboard.settingsMode === 'PCO') return;
  micboard.settingsMode = 'PCO';
  updateHash();
  $('#micboard').hide();
  $('.settings').hide();
  $('.sidebar-nav').hide();
  $('.pco-settings').show();

  bindHandlers();
  loadStatus().then(loadServiceTypes).then(loadTeams).then(renderAll);
}
