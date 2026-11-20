"""Exercise editable clones, independent edits, and competing ID allocations."""

from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from kbforge.collaboration import clone_site, push_site, shared_head, source_at
from kbforge.repository import Repository, load_article, save_article


class CollaborationTest(unittest.TestCase):
    def test_merge_conflicts_and_renumber_new_articles(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin = root / "origin"
            shutil.copytree(Path(__file__).resolve().parents[1] / "example", origin)
            remote = root / "shared"
            _, first, _, _, _ = push_site(
                Repository(origin), remote, include_pdfs=False, apply=True
            )
            clones = []
            for name in ("alice", "bob", "carol"):
                path = root / name
                self.assertEqual(clone_site(remote, path), first)
                clones.append(Repository(path))
            alice, bob, carol = clones

            def update(repo, article, text):
                path = repo.article_path(article, "en-US")
                meta, body = load_article(path)
                save_article(path, meta, body + "\n" + text + "\n")

            for repo, title in [(alice, "First draft"), (bob, "Second draft")]:
                article_id = repo.reserve_id()
                self.assertEqual(article_id, "FIELD-000005")
                article = repo.article_path(article_id, "en-US")
                article.parent.mkdir()
                save_article(
                    article,
                    {
                        "id": article_id,
                        "language": "en-US",
                        "title": title,
                        "status": "draft",
                    },
                    title,
                )
            update(alice, "FIELD-000001", "Alice's update.")
            update(
                bob,
                "FIELD-000002",
                "Bob's update with [a draft](../FIELD-000005/en-US.md).",
            )
            update(carol, "FIELD-000001", "Carol's conflicting edit.")
            _, second, _, _, refresh = push_site(
                alice, remote, include_pdfs=False, apply=True
            )
            self.assertFalse(refresh)
            with self.assertRaisesRegex(ValueError, "articles/FIELD-000001/en-US.md"):
                push_site(carol, remote, include_pdfs=False, apply=True)
            self.assertEqual(shared_head(remote), second)

            _, pending, _, renamed, refresh = push_site(bob, remote, include_pdfs=False)
            self.assertIsNone(pending)
            self.assertTrue(refresh)
            self.assertEqual(renamed, [("FIELD-000005", "FIELD-000006")])
            self.assertEqual(shared_head(remote), second)
            self.assertTrue(bob.article_path("FIELD-000005", "en-US").is_file())

            _, third, _, actual, _ = push_site(
                bob, remote, include_pdfs=False, apply=True
            )
            self.assertEqual(actual, renamed)
            merged = Repository(source_at(remote, third))
            for article_id, phrase in [
                ("FIELD-000001", "Alice's update."),
                ("FIELD-000002", "../FIELD-000006/en-US.md"),
            ]:
                self.assertIn(
                    phrase, load_article(merged.article_path(article_id, "en-US"))[1]
                )
            first_draft, _ = load_article(merged.article_path("FIELD-000005", "en-US"))
            second_draft, _ = load_article(merged.article_path("FIELD-000006", "en-US"))
            self.assertEqual(first_draft["title"], "First draft")
            self.assertEqual(second_draft["title"], "Second draft")
            self.assertNotIn("previous_ids", second_draft)
            self.assertFalse(
                (
                    remote / "site" / "releases" / third / "articles/FIELD-000006"
                ).exists()
            )
            with self.assertRaisesRegex(ValueError, "updated shared site"):
                push_site(bob, remote, include_pdfs=False)
