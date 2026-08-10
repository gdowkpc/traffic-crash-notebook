# Traffic Crash Notebook

[![Source Tests](https://github.com/gdowkpc/traffic-crash-notebook/actions/workflows/tests.yml/badge.svg)](https://github.com/gdowkpc/traffic-crash-notebook/actions/workflows/tests.yml)
[![Windows Portable Build](https://github.com/gdowkpc/traffic-crash-notebook/actions/workflows/build-windows.yml/badge.svg)](https://github.com/gdowkpc/traffic-crash-notebook/actions/workflows/build-windows.yml)

[Download the latest verified Windows portable release](https://github.com/gdowkpc/traffic-crash-notebook/releases/latest)

Traffic Crash Notebook is a personal, local Windows application for organizing traffic-crash investigative working notes. It is not an official report-writing or evidence-management system.

This repository is publicly visible for release transparency and collaboration but
does not currently grant an open-source license. Public visibility alone does not
grant permission to reuse the source or bundled assets. Agency names, forms, marks,
and other third-party material remain the property of their respective owners; no
agency endorsement is implied.

## Included in version 0.5.7

- Create and reopen unlimited cases.
- Read the selected case clearly with high-contrast text whether the case selector has keyboard focus or not.
- Use a guided first-run Data Storage Setup to select an investigator's assigned K: drive, another approved folder, or local storage; safely copy existing cases and verify the selected folder before use.
- Open Settings from the case header to review or change the data location and save the investigator's name, numeric DPSST, and assignment as defaults for new cases.
- Automatically check the official public GitHub release manifest at most once every 24 hours, or check immediately from **Help > Check for Updates**; approved downloads are size- and SHA-256-verified before being kept.
- Record the case overview, assigned officer, numeric DPSST, assignment, crash summary, and general notes; display crash times with AM/PM.
- Enter a person once and assign multiple roles such as driver, passenger, pedestrian, bicyclist, motorcyclist, witness, or victim.
- Create unlimited vehicles and link existing people as drivers or owners.
- Preview, print through the standard Windows printer dialog, and export a Traffic Crash Exchange Report from existing case records without duplicate data entry. It preserves linked and unambiguous legacy drivers; includes every saved passenger, witness, pedestrian, bicyclist, and motorcyclist; maps DPSST and Assignment into the footer; creates continuation pages as needed; and appends a searchable text information/responsibilities page last.
- Maintain an automatically sorted investigative Journal for dated actions, decisions, requests, findings, and follow-up.
- Maintain a separate Evidence workspace with unlimited property receipts, property owners, lodging classifications and locations, lodging dates, and automatically numbered descriptive items under each receipt.
- Track open, waiting, completed, and unnecessary investigative tasks in a dedicated Tasks workspace.
- Automatically save overview changes.
- Underline misspelled words in narrative and notes fields using a bundled offline English dictionary, with right-click corrections and a personal dictionary.
- Preview, print through the standard Windows printer dialog, and export a comprehensive Full Working Packet with a dedicated routing cover page and ruled handwriting areas or a Compact Packet that suppresses unused material; a separate Quick Review export remains available.
- Print case identity on every page with final "Page X of Y" numbering and a top-edge punch-safe layout for two-hole attorney folders.
- Create a consistent SQLite database backup while the application is running.
- Record unlimited roadways with their own speed, posting, curve, characteristics, and traffic-control details, plus a compact weather form with a direct Weather Underground History link, station, reading time, automatic display units, celestial lighting/twilight details, visibility, and scene-analysis conditions.
- Maintain participant injury, transport, restraint, air-bag, helmet, ejection/extraction, autopsy, next-of-kin, and medical/evidence notes.
- Maintain driver trip, impairment, sleep, work, familiarity, driving history, and license information including number, state, class, status, issued/expiration dates, endorsements, and restrictions; packet output suppresses driver-only physical-condition and sleep/awake data for non-drivers.
- Record vehicle weights, brakes, safety equipment, lighting, tire contribution, individual tire measurements, a per-vehicle NHTSA recall-check confirmation, towing status and destination, release status/date/details, and insurance claim number plus adjuster name, phone, and email.
- Record structured equipped/operable states, switch positions, body/glass/restraint observations, identity checks, and unlimited tire positions.
- Complete the original packet's 44-item motorcycle inspection with ratings, measurements, comments, and inspection metadata.
- Track the investigative checklist, crash-diagram completion, Axon sharing, peer/sergeant/DA routing milestones with Not Started, Pending, or Complete status and completion dates, unlimited charges/dispositions, crash-team response details, and unlimited video sources with location addresses and Axon upload status.
- Add, edit, and remove multiple roadway-surface records from a dedicated Surface subtab, with roadway/location, composition, condition, friction/drag factor, and notes.
- Store separate cell, home, and work numbers plus city, state, occupation, and business address data for people and contacts, with ZIP codes on person addresses.
- Display the Traffic Investigations Unit logo in the application and generated PDF.
- Maintain structured witness interview summaries, credibility notes, significance, and follow-up.
- Link unlimited family, next-of-kin, medical, attorney, insurance, employer, and other contacts directly to one person.
- Organize pedestrian, bicyclist, and motorcyclist visibility workups, motion/throw information, and whether a light meter or light board was used.
- Verify a finished portable build without opening the GUI or touching the normal case database.

## Running from source

Python 3.11 or newer is required on the development computer.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_app.py
```

## Building the portable Windows version

On a Windows development computer with Python 3.11 or newer, double-click:

```text
BUILD_WINDOWS.bat
```

The script creates an isolated virtual environment, runs the automated tests,
builds the executable, runs the finished executable's portable self-test, and
creates:

```text
release\TrafficCrashNotebook-0.5.7-Windows-Portable.zip
```

The included GitHub Actions workflow performs the same build on a hosted Windows
runner. Open **Actions > Build Windows Portable Application > Run workflow** to
create a retained workflow artifact. Pushing a matching `vMAJOR.MINOR.PATCH` tag
also publishes the verified ZIP, checksum, stable update manifest, and complete
per-file package manifest as a public GitHub release.

Extract and copy the entire `TrafficCrashNotebook` folder to a writable location
on the work computer. Run the executable directly; Python, an installer, and
administrator rights are not required on the target computer.

The completed folder includes `VERIFY_PORTABLE.bat`. This optional check creates
only fictional temporary data and confirms that the bundled database, PDF,
spell-check dictionary, and logo work. It does not open the
normal case database.

## Case data and storage setup

On first launch, **Data Storage Setup** asks the investigator to choose the
permanent case-data folder. If a mapped K: drive is available, the wizard offers
`K:\Traffic Crash Notebook` directly. It also supports another approved folder
or local storage, tests file and SQLite operations before accepting the folder,
and can copy an existing database without deleting the original recovery copy.

The selected folder contains:

```text
traffic_crash_notebook.sqlite3
personal_dictionary.txt
Reports\
Backups\
```

The small, replaceable location pointer is stored locally at
`%LOCALAPPDATA%\TrafficCrashNotebook\storage_config.json`; it contains no cases.
Case records and the investigator defaults are stored in the selected database,
so they remain together when a computer is replaced. On the replacement computer,
select the existing folder during first-run setup. Use the visible **Settings**
button or **Settings > Application Settings** to review the location and defaults.
Changing the data location requires an application restart.

## Verified portable updates

Automatic update checks are enabled by default and may be changed from the header
**Settings** screen. A check sends no case information; it only requests the public
stable-release manifest from `gdowkpc/traffic-crash-notebook` on GitHub. Silent
checks occur at most once every 24 hours. **Help > Check for Updates** runs an
immediate manual check.

When the investigator approves a download, the ZIP is saved under the selected
data folder's `Updates` subfolder. The application requires the official GitHub
release URL, exact manifest byte count, SHA-256 match, valid ZIP structure, and
required portable files. A failed or cancelled download is deleted. The application
does not install, extract, launch, or overwrite files automatically. Close the old
version, extract the complete new folder to a writable location, and run it without
administrator rights. The separately selected case database is not replaced.

Each release includes `update-manifest.json` plus a versioned `.files.json` manifest
containing the SHA-256 and size of every file inside the portable ZIP. GitHub Actions
also publishes build-provenance attestations for the ZIP, checksum, and manifests;
advanced users may verify them with `gh attestation verify` against this repository.

If the configured network drive is unavailable, the application blocks startup
and offers Retry, Choose Different Location, or Exit. It does not silently open
an empty database elsewhere. A network-hosted SQLite database must be used by
only one computer at a time. Set `TCN_DATA_DIR` before launch only for an
administrator-controlled override.

PDF exports default to the selected folder's `Reports` subfolder. Use **Back Up**
to create a point-in-time database copy in its `Backups` subfolder or another
approved location. Reports and backups contain investigative working information
and should be handled according to agency policy.

## Spell checking

Spell check runs automatically in real time for narrative, summary, address,
and notes fields. A red underline marks a possible misspelling. Right-click the
word to apply a suggested correction, ignore it for the current session, or save
it to the personal dictionary. The feature is fully offline and never sends
entered text to a network service.

## Printing modes

- **Case Packet Preview** is opened from the case header in its own resizable window. It displays either the Full Working Packet or Compact Packet and supports refresh, PDF export, and direct printing of all pages, the current page, or a selected page range.
- **Full Working Packet** preserves the complete section order and adds ruled areas for handwritten updates after printing. It is the intended attorney-folder copy. Print one-sided when practical so every ruled area remains easy to use.
- **Compact Packet** includes the complete entered record but omits unused sections and dedicated handwriting areas.
- **Export Quick Review** creates a concise briefing copy rather than the complete packet.
- **Exchange Report preview / export** creates a searchable, template-style information-exchange form from existing case data. It preserves drivers, dynamically packs existing vehicles plus pedestrian, bicyclist, and motorcyclist participants, adds numbered continuation pages as needed, and appends a selectable-text information/responsibilities page last.

All four PDFs use US Letter pages. The packet PDFs keep primary content below
the top-hole area, and every export carries case identity and page numbering.

## Development tests

The database tests use only Python's standard library. PDF tests also require `pypdf` from `requirements-dev.txt`.

```powershell
$env:PYTHONPATH = "src"
py -3 -m unittest discover -s tests -v
```

## Scope note

The packet export is a modern, searchable rendering of the original packet's
semantic information. It is not an Adobe LiveCycle/XFA dependency or a facsimile
of an official report form.
