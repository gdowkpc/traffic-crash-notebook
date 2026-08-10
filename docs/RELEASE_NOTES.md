## Unreleased

- Adds Non-Standard as an explicit Helmet choice and preserves it in saved participant details and packet output.
- Treats Motorcyclist as a vulnerable-road-user role in person entry, calculated VRU counts, VRU analysis, packet output, and exchange-report output.
- Standardizes full and compact packet section and subsection headings to title capitalization, including Participant and Driver Details.
- Reflows Familiarity and Driving History in the participant/driver packet as two wide cells with each value beneath its label.
- Standardizes packet field grids so each label and its value stay together in the same cell; multi-record tables retain their column headers.

## Traffic Crash Notebook 0.5.6

- Adds a participant Helmet field immediately after Air Bag Deployed with explicit Yes, No, and Not Applicable choices, safe migration of existing cases, and packet output.
- Changes the formal packet heading to "PORTLAND POLICE BUREAU - TRAFFIC INVESTIGATIONS UNIT" while retaining the TIU logo.
- Removes the printed Full Working Packet label, retains only the "Not an official report" footer disclaimer, and simplifies the handwriting area heading to Cover Notes.
- Consolidates the packet-cover Crash Date and Crash Time fields into one Crash Date / Time field using MM/DD/YYYY and AM/PM display.
- Replaces the Peer Review, MCT Sergeant Review, and Submitted to DA completion checkboxes with Not Started, Pending, and Complete workflow statuses; completion dates are available only for completed milestones.
- Migrates existing checked or dated review and DA-routing milestones to Complete and prints the selected statuses consistently on both the cover and investigative checklist.

## Traffic Crash Notebook 0.5.5

- Separates Evidence, Tasks, and Journal into dedicated workspaces and adds unlimited property receipts with owners, lodging classifications, lodging locations/dates, and automatically numbered evidence-item descriptions.
- Moves home-address entry above phone fields in the Add/Edit Person workflow for a more natural tab order.
- Makes License the first Driver Background tab, adds issued and expiration dates, simplifies restrictions entry, and renames Additional Notes to Driving History while preserving existing data.
- Changes non-driver packet output to Participant Background and suppresses driver-only Physical Conditions and Sleep/Awake rows.
- Removes Occupation and Follow-up from the packet's Witness Interviews area, removes the separate witness/contact follow-up write-in block, and gives Significance the full available row width for paragraph-length entries.
- Adds a direct Weather Underground History link above the Weather fields, opening the fixed historical-weather page in the investigator's default browser without including case data in the URL.
- Adds vehicle-specific insurance claim number and adjuster name, phone, and email fields to vehicle entry, saved case data, the Vehicles list, and both packet modes, with an additive migration for existing databases.
- Moves Packet Preview out of the data-entry tab row and into a prominent case-header button that opens a resizable preview, print, and PDF export window.
- Places the Exchange Report at the end of the main case tab bar.
- Identifies deceased people with a red DECEASED label in the packet People list Roles column, based on the saved death date or killed, fatal, or deceased status.
- Adds a separate Court Case Number beside the DA Case Number, preserves it with the case, and includes it on the packet cover and investigative checklist.
- Displays a branded TIU startup splash from the Windows bootloader while the portable application loads, then closes it only after the main window can paint.
- Closes the splash before first-run storage setup, storage-recovery prompts, startup errors, or portable self-tests so it never obscures a required dialog or automated verification.

## Traffic Crash Notebook 0.5.4

- Adds an embedded Case Packet Preview for both the Full Working Packet and Compact Packet, with refresh, PDF export, and direct printing through the standard Windows printer dialog.
- Uses in-memory, generation-specific packet previews so refresh remains reliable even when Windows temporarily retains a handle to the previously displayed PDF.
- Adds a required location address to every new or edited video-source record and includes the address in the case packet.
- Uses "Uploaded to Axon" throughout the video-source workflow and packet, with an automatic schema migration that preserves upload statuses stored by earlier releases under the legacy field name.
- Replaces the remaining user-facing DIMS scene-evidence labels with Axon while preserving and automatically translating legacy saved values.
- Removes the Key Questions / Unresolved Issues field from case entry, the packet cover, and Quick Review; the automatic database migration removes the retired stored field.
- Renames the user-facing "Roadway / Tag" label to "Roadway" in case entry and packet output while retaining unlimited separate roadway records.
- Reformats each People identity cell in the packet with Sex / Race on the first line and a separately labeled DOB on the second line without adding another table row.
- Reorders Participant Details so Gender / Race and DOB are included and Height / Weight appears before Transport; adds license Endorsements to driver entry, storage, and Driver Background output.
- Moves the structured Physical Conditions selections into a full-width Driver Background table row instead of rendering them as loose continuation text.
- Adds a per-vehicle NHTSA Recalls Checked checklist item to vehicle entry and both full and compact packet output while retaining the detailed recall-results field.
- Adds explicit per-vehicle Towed status and Towed to destination fields, preserves existing tow-information records during migration, and shows the result in the Vehicles list and both packet modes.
- Tightens the Weather subtab into a compact two-column layout, identifies expected entry units, and automatically adds missing F, mph, percent, inHg, and inch units in Full and Compact packet output without changing saved source values.
- Binds every Exchange Report preview to its source case, hides a prior case's preview immediately when cases change, and blocks export or printing if generation of the selected case's verified preview fails.
- Saves overview, packet, road, weather, and hit-and-run edits whenever investigators move between main tabs or subtabs, retains the existing short debounce, and adds a 30-second dirty-record safety retry.
- Warns before discarding unsaved add/edit dialog changes and verifies each vehicle is readable from the database after Save; a failed vehicle save reopens the populated vehicle window instead of silently losing the entry.
- Generates Exchange Report exports atomically from the currently selected case rather than copying the embedded preview, so a preview-renderer failure cannot export an older case or prevent creation of a valid current-case PDF.

## Traffic Crash Notebook 0.5.3

This testing release improves case organization and removes duplicated or generalized fields.

- Adds a high-contrast TIU application icon to the running window, Windows taskbar, and packaged executable.
- Adds direct printing from the embedded Exchange Report preview through the standard Windows printer dialog, including all pages, current page, and selected page ranges.
- Prevents WinError 32 during preview refresh by loading the displayed PDF from memory and using generation-specific temporary files.
- Includes every saved passenger and witness in the Exchange Report without creating a second data-entry path.
- Moves contacts under People and requires each contact to belong to one person.
- Moves release status, release date, and release information to each individual vehicle.
- Simplifies VRU night visibility to Light Meter Used and Light Board Used and removes the Perception / Response section from active entry and packet output.
- Separates Weather and Surface into distinct subtabs and supports unlimited surface records with add, edit, and remove actions.
- Migrates legacy single-surface values into the new multi-surface records without duplicating existing entries.
- Renames the investigator-facing Chronology workflow to Journal throughout data entry and packet output while preserving existing saved entries.
- Adds a dedicated packet cover page populated from shared case, investigator, calculated count, review, and DA-routing data without duplicate entry.
- Updates packet output, portable self-test coverage, and database schema migration checks for the revised workflows.

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
