# sync/adapters

One module per transport, each implementing `available()`, `push(outbox)`, `pull()` and `status()`, plus the hub extensions `pull_inboxes()` and `publish()` (ADR-005). Planned: `git` (default), `gdrive` (any desktop-synced folder: Google Drive, OneDrive, Dropbox), `usb` (drop-box folder on removable media), `syncthing` (LAN, M6) and `local` (tests and the hub's own captures). Third-party adapters register via the `cvprism.adapters` entry point.
