# Verified update manifests

Every stable GitHub release contains two JSON documents:

- `update-manifest.json` is the small, stable entrypoint used by the application. It identifies the current version, official release URLs, build ID, package size, SHA-256, database schema, release notes, and full-manifest descriptor.
- `TrafficCrashNotebook-VERSION-Windows-Portable.files.json` is the complete package manifest. It records the uncompressed size, compressed size, and SHA-256 of every file in the portable ZIP.

The stable application endpoint is:

```text
https://github.com/gdowkpc/traffic-crash-notebook/releases/latest/download/update-manifest.json
```

The client accepts HTTPS responses only from GitHub release hosts and requires the package URL to originate in this repository. A package is kept only when its downloaded byte count and SHA-256 exactly match the manifest, the ZIP passes integrity testing, and the executable plus required portable support files are present.

The GitHub Actions release job also creates GitHub artifact attestations for the ZIP, checksum, and JSON manifests. These provide independently verifiable workflow provenance in addition to the application's runtime hash checks.

Automatic checks are asynchronous, send no case information, and occur at most once every 24 hours when enabled. Download and installation are intentionally separate: download is user-approved; extraction and replacement remain manual so the running portable folder is never modified in place.

JSON Schemas for both documents are stored beside this file.
