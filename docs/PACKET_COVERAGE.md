# Traffic Crash Packet coverage specification

## Objective

Traffic Crash Notebook must replace the working workflow represented by the
19-page flattened Traffic Crash Packet while improving it with reusable data,
unlimited related records, local electronic storage, and four PDF outputs:

1. a complete case-book packet suitable for printing;
2. a compact packet that suppresses unused sections;
3. a concise working-notes review PDF; and
4. a traffic-crash information exchange report with automatic continuation pages.

The application must not require Adobe LiveCycle, Python, an installer,
administrator rights, or a network connection on the target computer.

## Source references

- `TrafficCrashPacket.pdf`: dynamic Adobe LiveCycle XFA source; SHA-256
  `c2da8b8abd5389043c67c51990d087a63d691b33abc2d4a3452afd1fd0855344`.
- `TrafficCrashPacket_flat.pdf`: 19-page visual reference; SHA-256
  `25152029833828308a73b8999fc0cdc01df926fa8932ea319d7917f7ec170f5a`.
- The XFA template contains 943 presentation fields, including 377 check
  controls, 488 text fields, 47 date/time fields, 16 choice fields, 14 numeric
  fields, 50 exclusion groups, and 37 JavaScript actions.

The target is semantic coverage of every packet datum and workflow. It is not
a dependency on the obsolete XFA runtime or a blind one-to-one copy of its 943
presentation controls.

## Page-by-page coverage

| Page(s) | Packet section | Required semantic data | v0.5.5 implementation |
|---|---|---|---|
| 1 | Packet cover | Case number, crash date/time/location/status, assigned investigator, DPSST, assignment, calculated people/vehicle/injury/fatal/VRU/Journal/task totals, peer and MCT sergeant review, DA submission, assigned DDA, DA case number, court case number, summary, and writable routing notes | Complete as a dedicated first page in the full and compact packet PDFs |
| 2 | Investigative checklist | Evidence collection, vehicle work, crash-diagram completion, Axon sharing, dated peer review, sergeant review, and DA submission milestones, assigned DDA, DA case number, court case number, unlimited charge/disposition rows | Complete |
| 3-4 | Investigative journal | Unlimited dated/timed journal entries with category, summary, and detail | Complete |
| 5 | Crash information | Date/day/time, city/county, road and intersection, coordinates, road jurisdiction, calculated participant/vehicle/fatal/VRU counts, team notification and response times, scene personnel, evidence/media methods, unlimited video sources with location address and Axon upload status | Complete; counts are calculated from shared records |
| 6 | Road and weather | Compact weather entry with station and reading time plus automatic F, mph, percent, inHg, and inch display units; a dedicated Surface subtab with unlimited add/edit/remove records for roadway/location, composition, condition, friction/drag factor, and notes; ambient lighting, sunrise/sunset, morning/evening civil twilight, moonrise/moonset/phase, streetlight status and notes, visual obstructions, area classifications, unlimited roadway records with per-roadway speed posting, curve values, characteristics and traffic controls, initial point of collision, skid/drag notes | Complete |
| 7 | VRU visibility | Clothing, roadway position/motion, projection classifications, sightlines, driver/VRU impairment and sleep, impact location, travel speeds/directions, throw distances, and light-meter/light-board use | Complete |
| 8 | Background information | Participant/type link, trip, physical conditions, impairment/testing, sleep/work history, familiarity, driving history, license restrictions/explanation, endorsements, and license data | Complete |
| 9 | Participant data | Gender, race, DOB, vehicle/position/type, injury status, height/weight, transport, medical records, restraint/airbag/ejection/extraction, autopsy/death/NOK, coded injuries, hospital, structured evidence collection, laboratory details | Complete |
| 10 | Contacts | Participant identity, street/city/state/ZIP address, occupation, and business address plus unlimited participant, family, insurer, adjuster, attorney, employer, medical, and other contacts with separate phone types | Complete |
| 11 | Vehicle information 1 | Identity/owner, mileage, transmission/gear/steering, weights, brakes, per-vehicle NHTSA recall-check confirmation plus recall results, NICB/VIN checks, detailed lighting/electrical states, switches, lens/wiper/horn/device observations, glass/mirrors/windows/restraints/airbags/body condition, EDR, insurance, explicit towing status and destination, per-vehicle release status/date/information, notes | Complete |
| 12 | Vehicle information 2 | Tire contribution and explanation, unlimited tires including inner duals, make/design/size/pressure/tread, per-position condition, damage description | Complete |
| 14-15 | Motorcycle information and inspection | Motorcycle identifiers, frame/engine and inspection metadata, 44 rated inspection items, item-specific measurements, detailed comments, officer/DPSST/location/date | Complete |
| 19 | At-scene witness list | Unlimited witnesses, identity/address/city/state/ZIP, separate cell/home/work phones, interviewed status, significance, and interview detail | Complete |

## Cross-record rules

- A person is entered once and may have any number of roles.
- Vehicles reference existing people as drivers and owners.
- Participant, driver, witness, and VRU records reference shared
  people and vehicles rather than duplicate names. Each contact record belongs
  directly to one person.
- Counts on crash information and PDF output are calculated from saved records.
- Case number and other shared case values populate every applicable PDF page.
- People, vehicles, witnesses, contacts, journal entries, charges, video
  sources, and tires are not limited by paper row
  counts.
- The exchange report reuses shared person, driver-license, vehicle, and
  insurance records. It prints three vehicles and four passengers/witnesses per
  page and adds as many numbered continuation pages as required.
- Deleting a shared record must either be blocked with a clear dependency
  message or safely clear nullable links without losing unrelated data.

## Product acceptance gates

- Every semantic item above has an editable UI and persistent SQLite storage.
- All shared values round-trip without duplicate entry.
- Existing schema-version-3 databases migrate additively with no data loss.
- All four PDF outputs render without clipped text, overlap, or missing sections.
- Add/edit/remove workflows pass automated GUI tests at a 900x560 logical
  window and remain usable with Windows display scaling.
- A clean portable Windows build passes its executable self-test and the
  double-click `VERIFY_PORTABLE.bat` path.
- The target computer receives only the completed portable ZIP and requires no
  installer or administrator access.

The full packet PDF is a modern, searchable rendering of the packet's semantic
content. It intentionally does not require or reproduce the obsolete Adobe XFA
runtime, and it is not represented as an official-report facsimile.
