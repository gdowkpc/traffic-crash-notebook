# Release process

Traffic Crash Notebook releases are produced by `.github/workflows/build-windows.yml` on a hosted Windows runner.

1. Update the application version in `pyproject.toml` and `src/traffic_crash_notebook/__init__.py`.
2. Update `docs/RELEASE_NOTES.md` and versioned documentation references.
3. Run the full source suite and a local portable build when available.
4. Commit and push the reviewed source to `main`.
5. Create and push an annotated tag matching the source version exactly, such as `v0.5.6`.
6. The tag workflow runs every test, builds the portable folder, runs the finished executable self-test, verifies the embedded non-admin Windows manifest, creates the ZIP and checksum, generates both release manifests, attests their GitHub Actions provenance, and publishes a GitHub release.
7. Verify the public `releases/latest/download/update-manifest.json`, package digest, required assets, and downloaded executable self-test before announcing the release.

The release workflow rejects a tag that does not match the source version. Existing releases are not overwritten.
