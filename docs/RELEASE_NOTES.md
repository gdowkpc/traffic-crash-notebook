## Traffic Crash Notebook 0.5.1

This maintenance release corrects Traffic Crash Exchange Report output.

- Replaces the photographed information/responsibilities page with a clean, searchable, selectable-text transcription of PPB form 770 (12/17).
- Always preserves drivers in the exchange report: explicit vehicle-driver links are used first, participant-to-vehicle links are honored, and an unambiguous legacy driver/vehicle pair is recovered automatically.
- Never substitutes a non-driver vehicle owner into the operator field.
- Prints unresolved drivers as separate involved-person records rather than omitting them.
- Adds explicit Driver, Pedestrian, and Bicyclist role checkboxes to involved-person blocks.
- Confirms that Overview DPSST and Assignment values are saved when the Exchange Report tab opens and map to the footer's DPSST and Precinct fields.
- Prevents the case number from overlapping the PAGE / OF field.

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
