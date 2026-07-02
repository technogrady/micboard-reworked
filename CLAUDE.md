# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Micboard is a visual monitoring dashboard for network-enabled Shure wireless devices (UHF-R, QLX-D, ULX-D, Axient Digital mics; PSM 1000 IEMs). A Python backend polls devices over the network and serves a browser-based frontend showing battery, audio, and RF levels in real time.

## Commands

```bash
npm install                        # JS deps (also needed for webpack build; Node 18+)
pip3 install -r py/requirements.txt  # Python deps (just tornado); on Debian 12+ use a venv (PEP 668)

npm run build                      # webpack 5: bundles js/ + css/ into static/
npm run server                     # run the backend (python py/micboard.py)
npx eslint js/                     # lint frontend JS (airbnb-base config, no npm script)

npm run app                        # launch Electron wrapper (expects packaged py binary; see docs/electron.md)
npm run binary                     # pyinstaller build of the python server
npm run pack && npm run dist       # Electron distribution build
```

There is no test suite. The frontend must be rebuilt with `npm run build` after any change under `js/` or `css/` — the server serves the bundled output from `static/`, not the source files.

Server runs on port 8058 by default (override with `-p`, `MICBOARD_PORT`, or `port` in config). Demo mode without hardware: open the UI with `#demo=true` (the `d` key toggles it).

## Architecture

Two halves communicate only via HTTP/WebSocket JSON:

- **Python backend (`py/`)** — Tornado web server plus device-polling threads.
- **Vanilla JS frontend (`js/`, `css/`)** — bundled by webpack into `static/` (entries: `app`, `about`, `venue`, `web` in `webpack.config.js`). jQuery/Bootstrap, no framework. `VERSION` is injected at build time from `package.json` via webpack DefinePlugin.

### Backend threading model

`py/micboard.py` starts five daemon-style threads that share module-level mutable state (no locks — lists are appended/cleared across threads):

1. `shure.SocketService` — a single `select()` loop over all device sockets (TCP port 2202 for most types, UDP for `uhfr`). Reads raw data, splits into messages, and enqueues them on `shure.DeviceMessageQueue`. Handles reconnect via watchdog timestamps on each device.
2. `shure.ProcessRXMessageQueue` — drains the queue and parses messages into device/channel state.
3. `shure.WirelessQueryQueue` — every 10s enqueues query command strings onto each connected device's `writeQueue`.
4. `tornado_server.twisted` — the Tornado app; a 50ms `PeriodicCallback` (`SocketHandler.ws_dump`) drains three global update lists (`channel.chart_update_list`, `channel.data_update_list`, `config.group_update_list`) and broadcasts them to all WebSocket clients.
5. `discover.discover` — listens for Shure multicast discovery packets (239.255.254.253:8427) and resolves models via DCID mappings in `dcid.json`.

### Device abstraction

- `networkdevice.ShureNetworkDevice` — one per receiver IP; owns the socket, a `writeQueue`, and a list of channels. Its `fileno()` lets `select()` treat it as a socket.
- `channel.ChannelDevice` — base class; subclassed by `mic.WirelessMic` and `iem.IEM`.
- `device_config.BASE_CONST` — the per-device-type protocol table (command string templates for query/getAll/metering, field-name mappings, TCP vs UDP, DCID model names). To support a new device type, add an entry here; type strings (`uhfr`, `qlxd`, `ulxd`, `axtd`, `p10t`) are matched in `config.py`, `shure.py`, `networkdevice.py`, and mirrored in `js/app.js` (`MIC_MODELS`/`IEM_MODELS`).

### Configuration

- `config.config_tree` is the global config, loaded from `config.json` — looked up first in the app dir, then the per-OS user config dir (`~/Library/Application Support/micboard` on macOS, `~/.local/share/micboard` on Linux); `democonfig.json` is copied there on first run. Writes (`update_slot`, `update_group`, `reconfig`) persist back to the same file.
- The central concept is the **slot**: every channel of every receiver is assigned a unique slot number; groups are named collections of slots. The frontend indexes `micboard.transmitters` by slot.
- `config.reconfig()` tears down all device connections and rebuilds everything from a new slot list (invoked via POST `/api/config`).

### HTTP/WS API (tornado_server.py)

- `/data.json` — full state dump (all receivers, config, discovered devices, background file lists). This is also the extension point documented in `docs/api.md`.
- `/ws` — WebSocket pushing `chart-update` (fast metering samples), `data-update` (channel state), and `group-update` messages.
- `/api/slot`, `/api/group`, `/api/config` — POST endpoints that mutate config.
- The root `/` renders `demo.html`, which is the real UI template (not just a demo page).

### Frontend flow

`js/app.js` boots on document ready: reads URL hash parameters, fetches `/data.json` for the initial render, then `js/data.js` opens the WebSocket for live updates plus a 1s `/data.json` poll as fallback/reconnect detection. Rendering lives in `channelview.js` (slot cards), `chart-smoothie.js` (smoothie.js streaming charts), `display.js` (TV/background modes), `dnd.js` (drag-and-drop group editor), `config.js` (device config editor), `extended.js` (name overrides), `kbd.js` (keyboard shortcuts — the primary UI control; see docs/configuration.md).
