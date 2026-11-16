"""Verify updates against a real upstream without contacting a network service."""

from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from kbforge.update import git, update_checkout


@unittest.skipUnless(shutil.which("git"), "Git is unavailable")
class UpdateTest(unittest.TestCase):
    def test_fast_forward_and_preserve_local_edits(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            upstream = root / "upstream"
            checkout = root / "checkout"
            upstream.mkdir()
            git(upstream, "init", "-b", "main")
            source = upstream / "app.txt"
            source.write_text("initial", encoding="utf-8")
            git(upstream, "add", "app.txt")
            commit = (
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
            )
            git(upstream, *commit, "-m", "Initial")
            git(root, "clone", str(upstream), str(checkout))
            self.assertIsNone(update_checkout(checkout))

            source.write_text("updated", encoding="utf-8")
            git(upstream, *commit, "-am", "Upstream update")
            local = checkout / "app.txt"
            local.write_text("unsaved", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checkout changes"):
                update_checkout(checkout)
            self.assertEqual(local.read_text(encoding="utf-8"), "unsaved")
            git(checkout, "restore", "app.txt")
            self.assertIsNotNone(update_checkout(checkout))
            self.assertEqual(local.read_text(encoding="utf-8"), "updated")

            local.write_text("local commit", encoding="utf-8")
            git(checkout, *commit, "-am", "Local change")
            with self.assertRaisesRegex(ValueError, "outside its upstream"):
                update_checkout(checkout)
            self.assertEqual(local.read_text(encoding="utf-8"), "local commit")
