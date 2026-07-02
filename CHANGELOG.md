# Changelog


## [Unreleased]
### Added
- `install.sh` and `update.sh` deployment scripts for Debian/Ubuntu/Raspberry Pi (dependency install, frontend build, and systemd service setup).

### Changed
- Renamed the project to Micboard Reworked and updated documentation to point at the `technogrady/micboard-reworked` repository.
- Modernized the frontend build for current Node.js (18+): webpack 4 → 5, node-sass → Dart Sass, removed file-loader/node-gyp.
- Rewrote the Dockerfile as a multi-stage build (node:22 for the frontend, python:3-slim for the server).
- Updated Debian installation instructions for Debian 12+ (system Node.js packages, Python virtual environment per PEP 668).
- micboard.service now runs micboard from a virtual environment.

### Not working yet
- macOS (desktop app, from source, and the Electron wrapper) is not being developed.
- Docker and the multivenue setup have not been re-verified against the rework.

### Fixed
- `config.py` relied on Tornado importing `logging.handlers`; it is now imported explicitly.


## [0.8.5] - 2019-10-10
### Added
- Device configuration page.
- Estimated battery times for devices using Shure rechargeable batteries.
- Offline device type for devices like PSM900s.
- Added color guide to help HUD.
- Custom QR code support using `local_url` config key.
- docker-compose for simplified docker deployment.

### Changed
- Migrated CSS display from flex to grid based system.
- Cleaned up node dependencies.
- Updated DCID map with additional devices.

### Fixed
- Disable caching for background images.
- Updated Dockerfile to Node 10.
- Invalid 'p10t' device type in configuration documentation.
- Resolved issue with PyInstaller that required the Mac app to be occasionally restarted.
- Cleaned up device discovery code.


## [0.8.0] - 2019-8-29
Initial public beta

[0.8.5]: https://github.com/karlcswanson/micboard/compare/v0.8.0...v0.8.5
[0.8.0]: https://github.com/karlcswanson/micboard/releases/tag/v0.8.0
