from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PortableScriptTest(unittest.TestCase):
    def test_verifier_uses_script_directory_without_trailing_path_argument(self):
        batch = (PROJECT_ROOT / "scripts" / "VERIFY_PORTABLE.bat").read_text(
            encoding="utf-8"
        )

        self.assertIn('-File "%~dp0VERIFY_PORTABLE.ps1"', batch)
        self.assertIn("-NonInteractive", batch)
        self.assertNotIn("-ApplicationFolder", batch)

    def test_windows_build_embeds_non_admin_manifest_and_generates_release_manifests(self):
        build = (PROJECT_ROOT / "scripts" / "build_windows.ps1").read_text(
            encoding="utf-8"
        )
        windows_manifest = (
            PROJECT_ROOT / "assets" / "windows" / "TrafficCrashNotebook.manifest"
        ).read_text(encoding="utf-8")

        self.assertIn('--manifest "$ProjectRoot\\assets\\windows\\TrafficCrashNotebook.manifest"', build)
        self.assertIn("verify_windows_executable_manifest.py", build)
        self.assertIn("generate_release_manifests.py", build)
        self.assertIn("verify_release_assets.py", build)
        self.assertIn('requestedExecutionLevel level="asInvoker"', windows_manifest)
        self.assertIn('uiAccess="false"', windows_manifest)
        self.assertNotIn("requireAdministrator", windows_manifest)

    def test_tag_workflow_publishes_zip_checksum_and_both_json_manifests(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "build-windows.yml"
        ).read_text(encoding="utf-8")
        publisher = (
            PROJECT_ROOT / "scripts" / "publish_github_release.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("release/*.json", workflow)
        self.assertIn("actions/attest-build-provenance@v4", workflow)
        self.assertIn("publish_github_release.ps1", workflow)
        self.assertIn("gh release create", publisher)
        self.assertIn("update-manifest.json", publisher)
        self.assertIn("Windows-Portable.files.json", publisher)


if __name__ == "__main__":
    unittest.main()
