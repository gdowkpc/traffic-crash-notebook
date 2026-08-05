## Traffic Crash Notebook 0.5.0

This release establishes the public GitHub distribution and verified portable-update channel.

- Adds automatic stable-release checks, enabled by default and limited to once every 24 hours.
- Adds **Help > Check for Updates** for an immediate manual check.
- Downloads the portable ZIP into the selected data folder's `Updates` subfolder only after the user approves it.
- Verifies the exact byte count, SHA-256 digest, ZIP integrity, and required portable files before keeping a download.
- Never installs, extracts, launches, or overwrites application files automatically.
- Publishes a stable update manifest and a complete per-file package manifest with every GitHub release.
- Embeds a Windows `asInvoker` application manifest, preserving non-administrator portable operation.
- Keeps investigator defaults and the update-check preference with the selected case database rather than AppData.
- Includes the Settings screen, exchange-report preview/export, hit-and-run workspace, realtime spell check, and prior packet improvements.
