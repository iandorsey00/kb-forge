"""Exercise publishing, rollback, and cloning with disposable collections."""

from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from kbforge.repository import Repository, load_article, save_article
from kbforge.site_release import (
    active_release,
    copy_site,
    load_release,
    publish_site,
    rollback_site,
)


class SiteReleaseTest(unittest.TestCase):
    def test_release_preview_publish_clone_rollback_and_failed_build(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection"
            shutil.copytree(Path(__file__).resolve().parents[1] / "example", collection)
            repo = Repository(collection)
            repo.config["publication_destinations"] = {"preview": "../published"}
            target, release, changes = publish_site(repo, "preview", include_pdfs=False)
            self.assertIsNone(release)
            self.assertFalse(target.exists())
            self.assertEqual([kind for kind, _ in changes], ["new"] * 4)
            _, first, _ = publish_site(repo, "preview", include_pdfs=False, apply=True)
            self.assertEqual(active_release(target), first)
            first_root, first_manifest = load_release(target, first)
            self.assertIn(
                "What’s new", (first_root / "index.html").read_text(encoding="utf-8")
            )
            self.assertEqual(len(first_manifest["editions"]), 4)

            article = repo.article_path("FIELD-000002", "en-US")
            metadata, body = load_article(article)
            save_article(
                article,
                {**metadata, "revision": 2, "release_note": "Updated <steps>"},
                body,
            )
            removed = repo.article_path("FIELD-000003", "zh-CN")
            metadata, body = load_article(removed)
            save_article(removed, {**metadata, "status": "retired"}, body)
            _, _, changes = publish_site(repo, "preview", include_pdfs=False)
            self.assertEqual([kind for kind, _ in changes], ["updated", "removed"])
            self.assertEqual(active_release(target), first)

            with patch(
                "kbforge.site_release.export_html",
                side_effect=ValueError("render failed"),
            ):
                with self.assertRaisesRegex(ValueError, "render failed"):
                    publish_site(repo, "preview", include_pdfs=False, apply=True)
            self.assertEqual(active_release(target), first)
            self.assertEqual(list((target / "releases").iterdir()), [first_root])

            _, second, _ = publish_site(repo, "preview", include_pdfs=False, apply=True)
            second_root, second_manifest = load_release(target, second)
            self.assertEqual(second_manifest["previous_release"], first)
            self.assertEqual(second_manifest["recent_changes"][0]["kind"], "updated")
            index = (second_root / "index.html").read_text(encoding="utf-8")
            self.assertIn("Updated &lt;steps&gt;", index)
            self.assertNotIn("FIELD-000003", index)
            self.assertTrue((first_root / "articles/FIELD-000003/zh-CN.html").is_file())

            clone = root / "offline"
            self.assertEqual(copy_site(repo, "preview", clone), second)
            self.assertEqual((clone / "index.html").read_text(encoding="utf-8"), index)
            self.assertEqual(rollback_site(repo, "preview"), (target, second, first))
            self.assertEqual(active_release(target), second)
            rollback_site(repo, "preview", apply=True)
            self.assertEqual(active_release(target), first)
            rollback_site(repo, "preview", release_id=second, apply=True)
            self.assertEqual(active_release(target), second)

    def test_existing_unmanaged_homepage_is_preserved(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection"
            shutil.copytree(Path(__file__).resolve().parents[1] / "example", collection)
            repo = Repository(collection)
            target = root / "published"
            target.mkdir()
            homepage = target / "index.html"
            homepage.write_text("existing content", encoding="utf-8")
            repo.config["publication_destinations"] = {"preview": "../published"}
            with self.assertRaisesRegex(ValueError, "homepage is not managed"):
                publish_site(repo, "preview", include_pdfs=False, apply=True)
            self.assertEqual(homepage.read_text(encoding="utf-8"), "existing content")
