"""Ensure release checks include new files and actual historical blobs."""

import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import privacy_scan


@unittest.skipUnless(shutil.which("git"), "Git is needed for history checks")
class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
            cwd=self.root, capture_output=True, text=True, check=True,
        )

    def scan(self):
        output = io.StringIO()
        with patch.object(privacy_scan, "ROOT", self.root), contextlib.redirect_stdout(output):
            status = privacy_scan.main()
        return status, output.getvalue()

    def test_untracked_files_are_scanned(self):
        (self.root / "new.md").write_text(privacy_scan.TOKEN_PREFIXES[0] + "example", encoding="utf-8")
        status, output = self.scan()
        self.assertEqual(status, 1)
        self.assertIn("new.md", output)

    def test_deleted_secret_is_found_in_history(self):
        path = self.root / "old.md"
        path.write_text(privacy_scan.TOKEN_PREFIXES[0] + "example", encoding="utf-8")
        self.git("add", "old.md")
        self.git("commit", "-qm", "Historical fixture")
        self.git("rm", "old.md")
        self.git("commit", "-qm", "Remove fixture")
        status, output = self.scan()
        self.assertEqual(status, 1)
        self.assertIn("history ", output)
        self.assertIn(":old.md", output)

    def test_clean_history_and_locally_deleted_file(self):
        path = self.root / "clean.md"
        path.write_text("Public documentation\n", encoding="utf-8")
        self.git("add", "clean.md")
        self.git("commit", "-qm", "Clean fixture")
        path.unlink()
        self.assertEqual(self.scan()[0], 0)


if __name__ == "__main__":
    unittest.main()
