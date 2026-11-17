import base64
import json
from io import BytesIO
from pathlib import Path
import re
import shutil
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from types import SimpleNamespace

from kbforge.app import Handler
from kbforge.migrate import migrate_articles
from kbforge.package import import_package
from kbforge.publishing import export_html
from kbforge.renumber import renumber
from kbforge.repository import (
    Repository,
    initialize_collection,
    load_article,
    save_article,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "example"


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "collection"
        shutil.copytree(EXAMPLE, self.root)
        self.repo = Repository(self.root)

    def test_article_workflow_over_http(self):
        server = SimpleNamespace(server_port=8765, write_lock=threading.Lock())

        class InMemoryHandler(Handler):
            """Exercise actual HTTP parsing and routing without opening a socket."""

            def setup(self):
                self.rfile = BytesIO(self.request)
                self.wfile = BytesIO()

            def finish(self):
                self.result = self.wfile.getvalue()

            def log_message(self, format, *args):
                pass

        def request(method, path, data=b""):
            raw = (
                f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n"
                f"Content-Length: {len(data)}\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n\r\n"
            ).encode() + data
            handler = InMemoryHandler(
                self.repo, "test-token", raw, ("127.0.0.1", 12345), server
            )
            headers, body = handler.result.decode().split("\r\n\r\n", 1)
            if headers.startswith("HTTP/1.0 303"):
                location = next(
                    line[10:]
                    for line in headers.splitlines()
                    if line.startswith("Location: ")
                )
                return request("GET", location)
            self.assertTrue(headers.startswith("HTTP/1.0 200"), body)
            return body

        def get(path):
            return request("GET", path)

        def post(path, **data):
            return request(
                "POST", path, urlencode({"_token": "test-token", **data}).encode()
            )

        self.assertIn("Create draft", get("/create"))
        editor = post(
            "/create",
            title="New field procedure",
            owner="Operations",
            language="en-US",
            type="procedure",
            tags="field-test",
            review_on="2030-06-01",
        )
        self.assertIn("FIELD-000005", editor)
        query = "?id=FIELD-000005&language=en-US"
        fingerprint = re.search(r'name="fingerprint" value="([a-f0-9]+)"', editor)[1]
        rendered = post(
            "/edit" + query,
            fingerprint=fingerprint,
            title="New field procedure",
            owner="Operations",
            type="procedure",
            status="published",
            tags="field-test",
            review_on="2030-06-01",
            body="## Purpose\n\nShow a table.\n\n## Steps\n\n| A | B |\n|---|---|\n| 1 | 2 |",
        )
        self.assertIn("<table>", rendered)
        image = (
            EXAMPLE / "articles/FIELD-000001/assets/input-selector.png"
        ).read_bytes()
        data = base64.b64encode(image).decode()
        for _ in range(2):
            post(
                "/image" + query,
                filename="My Screenshot.PNG",
                image=data,
                alt="Example screen",
            )
        self.assertIn("New field procedure", get("/catalog?q=field-test"))
        self.assertNotIn("New field procedure", get("/catalog?q=unmatched"))
        published = get("/publish" + query)
        self.assertIn("Northshore Field Services", published)
        self.assertIn("data:image/png;base64,", published)
        self.assertIn("Print or save as PDF", published)
        self.assertNotIn("FIELD-000005", get("/validate"))
        path = self.repo.article_path("FIELD-000005", "en-US")
        self.assertEqual(load_article(path)[0]["revision"], 4)
        self.assertIn("![Example screen](assets/my-screenshot-2.png)", path.read_text())
        self.assertEqual(
            (path.parent / "assets/my-screenshot-2.png").read_bytes(), image
        )
        saved = path.read_bytes()
        attached = post(
            "/image" + query,
            insert="draft",
            filename="Draft.png",
            image=data,
            alt="Draft screenshot",
        )
        self.assertEqual(
            json.loads(attached)["markdown"], "![Draft screenshot](assets/draft.png)"
        )
        self.assertEqual(path.read_bytes(), saved)
        self.assertEqual((path.parent / "assets/draft.png").read_bytes(), image)
        chinese = get("/publish?id=FIELD-000001&language=zh-CN")
        self.assertIn("处理会议室显示屏无信号的问题", chinese)
        self.assertRegex(chinese, re.compile(r'lang="zh-CN".*?修订版', re.S))

    def test_registry_preserves_reserved_ids(self):
        self.assertEqual(self.repo.reserve_id(), "FIELD-000005")
        self.assertEqual(Repository(self.root).reserve_id(), "FIELD-000006")

    def test_validation_identifies_bad_metadata_and_stale_translation(self):
        path = self.repo.article_path("FIELD-000001", "en-US")
        metadata, body = load_article(path)
        save_article(path, {**metadata, "revision": 2}, body)
        messages = [message for _, _, message in self.repo.validate()]
        self.assertTrue(any("outdated" in message for message in messages))
        self.assertTrue(any("nonempty owner" in message for message in messages))
        self.assertTrue(any("missing.png" in message for message in messages))

    def test_invalid_article_paths_and_images_are_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.article_path("../branding", "en-US")
        with self.assertRaises(ValueError):
            self.repo.store_image("FIELD-000001", "image.png", b"invalid")

    def test_blank_collection_and_static_site(self):
        location = self.root.parent / "new"
        initialize_collection(location, "New collection", "SUPPORT", 5, "en-US")
        blank = Repository(location)
        self.assertEqual(list(blank.scan()), [])
        self.assertEqual(blank.validate(), [])
        self.assertEqual(blank.reserve_id(), "SUPPORT-00001")
        with self.assertRaises(FileExistsError):
            initialize_collection(location, "Replacement", "NEW", 5, "en-US")

        destination = self.root.parent / "site"
        export_html(self.repo, destination)
        index = (destination / "index.html").read_text(encoding="utf-8")
        self.assertIn("FIELD-000001.zh-CN.html", index)
        page = (destination / "FIELD-000001.en-US.html").read_text(encoding="utf-8")
        self.assertIn('href="FIELD-000002.en-US.html"', page)
        self.assertIn("data:image/png;base64,", page)
        self.assertNotIn('href="/article?', page)
        self.assertFalse((destination / "FIELD-000004.en-US.html").exists())
        with self.assertRaises(FileExistsError):
            export_html(self.repo, destination)

    def test_renumber_requires_force_and_preserves_editions(self):
        old, new = "FIELD-000001", "SUPPORT-00001"
        source = self.repo.article_path(old, "en-US")
        pointing = self.repo.article_path("FIELD-000002", "en-US")
        original = source.read_bytes()
        self.assertIn(pointing, renumber(self.repo, old, new))
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(self.repo.article_path(new, "en-US").exists())

        renumber(self.repo, old, new, force=True)
        self.assertFalse(source.parent.exists())
        for language in ("en-US", "zh-CN"):
            metadata, _ = load_article(self.repo.article_path(new, language))
            self.assertEqual(metadata["id"], new)
            self.assertEqual(metadata["previous_ids"], [old])
        self.assertTrue(
            (self.repo.article_path(new, "en-US").parent / "assets").is_dir()
        )
        metadata, body = load_article(pointing)
        self.assertEqual(metadata["related"], [new])
        self.assertIn(f"../{new}/en-US.md", body)
        with self.assertRaisesRegex(ValueError, "already in use or reserved"):
            renumber(self.repo, new, old, force=True)

    def test_import_article_package_validates_and_preserves_source(self):
        source = self.root.parent / "article-package"
        shutil.copytree(EXAMPLE / "articles/FIELD-000001", source)
        for edition in source.glob("*.md"):
            metadata, body = load_article(edition)
            save_article(edition, {**metadata, "id": "IMPORT-00001"}, body)
        imported, findings = import_package(self.repo, source)
        self.assertEqual(imported, "IMPORT-00001")
        self.assertFalse(any(item[0] == "Error" for item in findings))
        edition = self.repo.article_path(imported, "zh-CN")
        self.assertEqual(edition.read_bytes(), (source / edition.name).read_bytes())
        self.assertTrue((edition.parent / "assets/input-selector.png").exists())
        with self.assertRaisesRegex(ValueError, "already in use or reserved"):
            import_package(self.repo, source)

        before = self.repo.path("registry", "ids.yaml").read_bytes()
        for edition in source.glob("*.md"):
            metadata, body = load_article(edition)
            save_article(edition, {**metadata, "id": "IMPORT-00002"}, body)
        (source / "assets/input-selector.png").unlink()
        with self.assertRaisesRegex(ValueError, "failed validation"):
            import_package(self.repo, source)
        self.assertFalse(self.repo.path("articles", "IMPORT-00002").exists())
        self.assertEqual(self.repo.path("registry", "ids.yaml").read_bytes(), before)

    def test_author_migration_previews_and_preserves_existing_content(self):
        first = self.repo.article_path("FIELD-000001", "en-US")
        second = self.repo.article_path("FIELD-000002", "en-US")
        metadata, body = load_article(second)
        save_article(second, {**metadata, "author": "Original Author"}, body)
        existing = second.read_bytes()
        original = first.read_bytes()
        preview = migrate_articles(self.repo, "author", "New Author")
        self.assertIn(first, preview)
        self.assertNotIn(second, preview)
        self.assertEqual(first.read_bytes(), original)

        self.assertEqual(
            migrate_articles(self.repo, "author", "New Author", force=True), preview
        )
        self.assertEqual(second.read_bytes(), existing)
        self.assertEqual(
            first.read_bytes().split(b"---", 2)[2], original.split(b"---", 2)[2]
        )
        self.assertEqual(load_article(first)[0]["author"], "New Author")
        self.assertEqual(migrate_articles(self.repo, "author", "Other", force=True), [])
