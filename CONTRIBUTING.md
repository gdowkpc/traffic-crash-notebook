# Contributing

Use fictional data in all tests, examples, screenshots, and issue reports. Never commit a case database, exported report, backup, personal information, credentials, or agency-restricted material.

Before proposing a change:

1. Install `requirements-dev.txt` in a local virtual environment.
2. Set `PYTHONPATH=src`, `QT_QPA_PLATFORM=offscreen`, and `TCN_DISABLE_UPDATE_CHECK=1` for automated UI tests.
3. Run `python -m unittest discover -s tests -v`.
4. For release-affecting changes, run the Windows portable build and confirm the finished executable's self-test reports `PASS`.

Keep database migrations additive and preserve existing case data. Update downloads must remain non-admin, opt-in, hash-verified, and separate from the case-data folder's active database.
