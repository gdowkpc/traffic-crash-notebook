# CrashX Idaho Falls field-test guide

CrashX Idaho Falls is an evaluation build of an information-exchange utility
tailored for review by the Idaho Falls Police Department (IFPD). It does not
create or submit an official Idaho Vehicle Collision Report (IVCR), determine
fault, or represent approval or adoption by IFPD or another agency.

## Start safely

1. Copy the single-file beta to a writable folder on a Windows x64 computer.
2. Run the packaged self-test before opening the normal window.
3. Use fictional names, addresses, license numbers, VINs, policy numbers, and
   phone numbers for the first test. Do not send real personal information with
   feedback.
4. Confirm that agency policy permits testing before using department equipment,
   a camera, or real crash information.

## Core test

Create a fictional two-vehicle crash with:

- an agency case number, date, time, location, badge number, and assignment;
- one driver who is also the registered owner;
- one driver whose registered owner is a different person;
- an out-of-state driver or vehicle;
- insurance company and policy number for both vehicles;
- plate, year, make, model, color, VIN, and tow information;
- one passenger and one witness; and
- one person added by scanning a fictional/test AAMVA PDF417 barcode, if an
  approved camera is available.

Save the PDF and check:

- every person is attached to the correct vehicle;
- the separate owner's name and address are visible;
- driver-license, registration/VIN, insurance, and towing values are complete;
- no text is clipped when viewed at 100 percent or printed on US Letter paper;
- the Idaho responsibilities page is legible and clearly says the PDF is not an
  official IVCR and has not been approved or adopted by IFPD;
- the final page lists 911, non-emergency dispatch at 208-529-1200, IFPD Records
  at 208-612-8600, the Information Desk at 208-612-8616, and 775 Northgate Mile;
- the printed and clickable crash-report address is
  `https://www.idahofallsidaho.gov/768/Records`;
- no north-arrow indicator appears in the crash-location field;
- the PDF text can be selected and searched; and
- closing the app and reopening it shows a blank form.

## Stress and failure tests

- Add five vehicles and at least ten additional people. Confirm that numbered
  continuation pages are created and nobody is omitted.
- Try assigning two drivers or two registered owners to one vehicle. Confirm the
  app refuses the second assignment.
- Cancel a vehicle edit, a person edit, a license scan, and the Save PDF dialog.
  Confirm no partial record or unwanted PDF remains.
- Select Clear all and decline once, then approve it. Confirm the entered data is
  discarded only after approval.
- Save to a long path and to a filename without `.pdf`. Confirm a readable PDF is
  produced with the expected extension.

## Officer review questions

1. Are the required Idaho exchange fields present and labeled the way officers
   expect in the field?
2. Do `Badge number` and `Assignment` appear in the correct locations and print
   accurately?
3. Are the IFPD contact labels, phone numbers, address, and accident-report
   instructions on the final page correct for an involved-party copy?
4. Does agency policy allow every printed item, especially driver-license
   numbers, phone numbers, addresses, and VINs, to be given to all involved
   parties?
5. Should email addresses, injury/transport details, towing release details, or
   insurance claim numbers be added?
6. Is the Idaho responsibilities page accurate, useful, and appropriate for an
   involved-party copy?
7. Does the form need agency branding or records-unit approval before any real
   use?

Report feedback using fictional examples or redacted screenshots. Include the
exact field label, what was expected, what occurred, the Windows version, and
whether the problem appeared on screen, in the saved PDF, or on paper.

## Privacy and scope

Entered data stays in application memory until Clear all or exit. The saved PDF
is not encrypted and remains wherever the user chooses to save it. Camera frames
and the raw license-barcode payload are not intentionally written to disk. The
Idaho reference text and IFPD public contact information were reviewed on August
6, 2026, and should receive agency or legal review before operational adoption.
