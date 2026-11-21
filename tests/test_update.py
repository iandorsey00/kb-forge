"""Verify updates against a real upstream without contacting a network service."""

from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from kbforge.update import git, update_available, update_checkout


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
            (upstream / ".gitignore").write_text(
                "/private-collection/\n", encoding="utf-8"
            )
            git(upstream, "add", "app.txt", ".gitignore")
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
            self.assertFalse(update_available(checkout))

            source.write_text("updated", encoding="utf-8")
            git(upstream, *commit, "-am", "Upstream update")
            local = checkout / "app.txt"
            previous = git(checkout, "rev-parse", "HEAD")
            self.assertTrue(update_available(checkout))
            self.assertEqual(git(checkout, "rev-parse", "HEAD"), previous)
            self.assertEqual(local.read_text(encoding="utf-8"), "initial")
            local.write_text("unsaved", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checkout changes"):
                update_checkout(checkout)
            self.assertEqual(local.read_text(encoding="utf-8"), "unsaved")
            git(checkout, "restore", "app.txt")
            article = checkout / "collection" / "en-US.md"
            article.parent.mkdir()
            article.write_text("work article", encoding="utf-8")
            self.assertIsNotNone(update_checkout(checkout))
            self.assertFalse(update_available(checkout))
            self.assertEqual(local.read_text(encoding="utf-8"), "updated")
            self.assertEqual(article.read_text(encoding="utf-8"), "work article")

            local.write_text("local commit", encoding="utf-8")
            git(checkout, *commit, "-am", "Local change")
            self.assertFalse(update_available(checkout))
            with self.assertRaisesRegex(ValueError, "outside its upstream"):
                update_checkout(checkout)
            self.assertEqual(local.read_text(encoding="utf-8"), "local commit")

            git(checkout, "reset", "--hard", "HEAD^")
            upstream_article = upstream / "collection" / "en-US.md"
            upstream_article.parent.mkdir()
            upstream_article.write_text("upstream article", encoding="utf-8")
            git(upstream, "add", "collection")
            git(upstream, *commit, "-m", "Add conflicting path")
            with self.assertRaisesRegex(ValueError, "would be overwritten"):
                update_checkout(checkout)
            self.assertEqual(article.read_text(encoding="utf-8"), "work article")

            article.rename(checkout / "moved-article.md")
            private = checkout / "private-collection"
            private.mkdir()
            ignored_article = private / "en-US.md"
            ignored_article.write_text("ignored article", encoding="utf-8")
            private_upstream = upstream / "private-collection"
            private_upstream.mkdir()
            (private_upstream / "en-US.md").write_text(
                "upstream file", encoding="utf-8"
            )
            git(upstream, "add", "-f", "private-collection/en-US.md")
            git(upstream, *commit, "-m", "Add conflicting ignored path")
            with self.assertRaisesRegex(ValueError, "would be overwritten"):
                update_checkout(checkout)
            self.assertEqual(
                ignored_article.read_text(encoding="utf-8"), "ignored article"
            )
