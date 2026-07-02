# Planning Center mic assignments

Micboard can pull the scheduled roster for your upcoming service from
[Planning Center Online (PCO) Services](https://www.planningcenter.com/services)
and automatically label each mic with the name of the person assigned to it.

The flow, once set up, is: open **Planning Center** in Micboard → click **Sync from
Planning Center** → every mic in a mapped group shows the name of the volunteer/staffer
scheduled on it for the next plan.

---

## 1. Create a Personal Access Token

Micboard authenticates to Planning Center with a **Personal Access Token (PAT)** — an
App ID + Secret. This is the right choice for a self-hosted install: no OAuth callback,
no app to register, and nothing shared between churches. Each install uses its own token.

1. Sign in to Planning Center as an **Administrator** (or a service account with
   read access to Services).
2. Go to **[api.planningcenteronline.com](https://api.planningcenteronline.com)** →
   **Developers** → **Personal Access Tokens** → **New Personal Access Token**.
3. Give it a description (e.g. "Micboard") and create it.
4. Copy the **Application ID** and **Secret**.

> **Tip:** create the token under an admin or dedicated service account, not a personal
> volunteer login — a PAT stops working if the account that owns it loses access.

Micboard only ever *reads* from Planning Center.

## 2. Connect Micboard

1. In Micboard, open the menu (&#9776;) → **planning center**, or press **`p`**, or use
   the **Plan Center** toolbar button.
2. Under **1. Connect**, paste the **Application ID** and **Secret** and click
   **Save token**.

The token is stored **server-side only**, in a file named `pco.env` next to your
`config.json` (see [Configuration](configuration.md) for where that lives on each OS).
It is written with `0600` permissions, is git-ignored, and is **never** sent to the
browser or included in `/data.json`.

You can also supply the credentials via environment variables instead of the UI —
handy for Docker / systemd:

```
PCO_APP_ID=your-app-id
PCO_SECRET=your-secret
```

## 3. Pick your service type

Under **2. Service type**, choose the service that holds the plans you schedule mics for
(e.g. *Sunday Worship Service*).

## 4. Map teams to mic pools

A **mapping** links a **Planning Center team** to a **Micboard group**. The group's slot
list becomes the *pool* of mics that team's people can be assigned to.

For each mapping (**3. Team → mic-pool mappings → + Add mapping**):

| Field | Meaning |
|-------|---------|
| **PCO Team** | The team whose scheduled people you want on mics (e.g. *Worship Vocalist*). |
| **Micboard Group** | The group whose slots are the available mics for that team. |
| **Fill mode** | `Auto-assign` fills the pool automatically; `Manual` only places people you've pinned. |
| **Include** | Which roster statuses count — *Confirmed only*, *All except declined*, or *Everyone scheduled*. |

### Auto-assign

In auto mode, Micboard fills the group's slots in order from the filtered roster. Ordering
is deterministic (by team position — so "Mic 1" before "Mic 2" — then by last name), so the
same roster always produces the same layout.

### Pinning a person to a specific mic (sticky)

Click **Assign / Pins** on a mapping to load the next plan's roster and choose a specific
slot for any person. Pins are **remembered week to week** (keyed by the person's Planning
Center ID), so someone who always uses the same handheld keeps landing on it. Auto-assign
fills the remaining, unpinned slots around your pins.

Click **Save mappings** when done.

### Naming tip

If you name your Planning Center **team positions** consistently (for example
"Mic 1", "Mic 2", … "Mic 8"), auto-assign ordering lines up naturally with your physical
mic numbers.

## 5. Sync

- Click **Sync from Planning Center** to pull the next upcoming plan and label the mics now.
- Enable **Auto-refresh every N seconds** to keep names updated automatically as the roster
  changes (useful if people are still being scheduled/confirmed). Leave it off to sync only
  on demand — the safer choice during a live service.

Names are written into each slot's *extended name*, the same field the manual
[name editor](configuration.md) uses.

---

## Notes & limitations

- **Names can be cleared by a hardware rename.** Micboard anchors an assigned name to the
  receiver channel's name at the moment of sync. If someone later renames that channel on
  the receiver itself, Micboard treats the assignment as stale and clears it. Re-sync to
  restore it.
- **Slots must already exist.** A mapping can only fill slots that are configured in
  Micboard and listed in the chosen group. Set up your devices/slots and groups first (see
  [Configuration](configuration.md)).
- **Rate limits.** A sync makes only a few API calls; Planning Center's per-token limit
  (100 requests / 20 seconds) is not a concern for normal use.
- **Credentials live only in `pco.env`** (or the environment). The mapping configuration
  (teams, groups, pins) is stored in `config.json` and is safe to share — it contains no
  secrets.
