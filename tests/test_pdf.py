"""Regression checks for the built-in paginated PDF renderer."""

from io import BytesIO
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from kbforge.pdf import export_pdf, pdf_available
from kbforge.publishing import export_html, render_body
from kbforge.repository import Repository, load_article, save_article


@unittest.skipUnless(pdf_available(), "Optional PDF dependencies are missing")
class PublishingTest(unittest.TestCase):
    def test_task_markers_and_bundled_symbol_fallback(self):
        from pypdf import PdfReader

        with TemporaryDirectory() as directory:
            collection = Path(directory) / "collection"
            shutil.copytree(Path(__file__).resolve().parents[1] / "example", collection)
            repo = Repository(collection)
            repo.config.pop("publishing", None)
            article = repo.article_path("FIELD-000001", "en-US")
            meta, _ = load_article(article)
            save_article(article, meta, "## Checklist\n\n- [ ] To do\n- [x] Done\n\nSymbols: ☐ ☑ ☒ ✓\n")
            pdf = PdfReader(BytesIO(export_pdf(repo, article)))
            text = "".join(page.extract_text() for page in pdf.pages)
            self.assertEqual(text.count("☐"), 2)
            self.assertEqual(text.count("☒"), 2)
            self.assertNotIn("•", text)
            self.assertIn("Symbols: ☐ ☑ ☒ ✓", text)

    def test_sized_list_image_and_shaded_quote(self):
        from pypdf import PdfReader

        with TemporaryDirectory() as directory:
            collection = Path(directory) / "collection"
            shutil.copytree(Path(__file__).resolve().parents[1] / "example", collection)
            repo = Repository(collection)
            article = repo.article_path("FIELD-000001", "en-US")
            meta, _ = load_article(article)
            body = (
                "## Steps\n\n"
                "1. List text\n\n"
                "   ![Selector](assets/input-selector.png){width=40%}\n\n"
                "> Quoted text\n"
            )
            save_article(article, meta, body)
            pdf = PdfReader(BytesIO(export_pdf(repo, article)))
            page = pdf.pages[2]
            body_origin = {}

            def visit(text, cm, tm, font, size):
                if "List text" in text:
                    body_origin.update(x=cm[4] + tm[4], size=size)

            page.extract_text(visitor_text=visit)
            self.assertEqual(body_origin["size"], 11)
            operations = page.get_contents().operations
            image_index = max(
                index
                for index, (_, operator) in enumerate(operations)
                if operator == b"Do"
            )
            image_width, _, _, _, _, _ = operations[image_index - 1][0]
            self.assertLess(image_width, float(page.mediabox.width) * 0.4)
            self.assertAlmostEqual(
                operations[image_index - 3][0][4],
                body_origin["x"],
                places=3,
            )
            self.assertTrue(any(operator == b"re" for _, operator in operations))

            html = render_body(repo, article, body)
            self.assertIn('style="width:40.0%"', html)
            self.assertIn("<blockquote>", html)

            near_boundary = (
                "## Steps\n\n"
                + "Filler paragraph.\n\n" * 24
                + "## Figure heading\n\n"
                + "![Adjacent figure](assets/input-selector.png){width=60%}\n"
            )
            save_article(article, meta, near_boundary)
            pdf = PdfReader(BytesIO(export_pdf(repo, article)))
            for page in pdf.pages[2:]:
                text = page.extract_text()
                if "Figure heading" in text:
                    self.assertIn("Adjacent figure", text)
                    break
            else:
                self.fail("Expected the figure heading in the PDF body")

    def test_contents_links_land_on_their_heading_pages(self):
        from pypdf import PdfReader

        repo = Repository(Path(__file__).resolve().parents[1] / "example")
        article = repo.article_path("FIELD-000002", "en-US")
        pdf = PdfReader(BytesIO(export_pdf(repo, article)))
        self.assertIn("Table of Contents", pdf.pages[1].extract_text())
        self.assertRegex(pdf.pages[1].extract_text(), r"(?:\.\s*){3,}3\b")
        annotations = pdf.pages[1]["/Annots"]
        self.assertTrue(annotations)
        for entry in annotations:
            target = entry.get_object()["/Dest"][0].get_object()
            self.assertEqual(pdf.get_page_number(target), 2)
        self.assertIn("Steps", pdf.pages[2].extract_text())

    def test_custom_cover_reorders_fields_and_keeps_contents(self):
        from pypdf import PdfReader

        repo = Repository(Path(__file__).resolve().parents[1] / "example")
        article = repo.article_path("FIELD-000002", "en-US")
        repo.config.setdefault("publishing", {})["cover_layout"] = [
            {"field": "title", "x": 10, "y": 28, "width": 80, "height": 12},
            {"field": "id", "x": 10, "y": 12, "width": 80, "height": 5},
            {"text": "Internal copy", "x": 10, "y": 80, "width": 80, "height": 5},
        ]
        pdf = PdfReader(BytesIO(export_pdf(repo, article)))
        positions = {}

        def visit(text, cm, tm, font, size):
            for label in ("FIELD-000002", "Internal copy"):
                if label in text:
                    positions[label] = cm[5] + tm[5]

        pdf.pages[0].extract_text(visitor_text=visit)
        self.assertGreater(positions["FIELD-000002"], positions["Internal copy"])
        self.assertIn("Table of Contents", pdf.pages[1].extract_text())

        repo.config["publishing"]["cover_layout"][0]["height"] = 0.1
        with self.assertRaisesRegex(ValueError, "Cover element 1 text does not fit"):
            export_pdf(repo, article)

    def test_author_is_visible_and_written_to_pdf_properties(self):
        from pypdf import PdfReader

        with TemporaryDirectory() as directory:
            root = Path(directory)
            collection = root / "collection"
            shutil.copytree(Path(__file__).resolve().parents[1] / "example", collection)
            repo = Repository(collection)
            article = repo.article_path("FIELD-000002", "en-US")
            metadata, body = load_article(article)
            self.assertNotIn(
                "Author:",
                PdfReader(BytesIO(export_pdf(repo, article))).pages[2].extract_text(),
            )
            save_article(article, {**metadata, "author": "Alex & Casey"}, body)

            site = root / "site"
            export_html(repo, site, include_pdfs=False)
            html = (site / "articles/FIELD-000002/en-US.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("Author: Alex &amp; Casey", html)

            pdf = PdfReader(BytesIO(export_pdf(repo, article)))
            self.assertEqual(pdf.metadata.author, "Alex & Casey")
            self.assertIn("Author: Alex & Casey", pdf.pages[2].extract_text())

            repo.config.setdefault("publishing", {})["cover_layout"] = [
                {"field": "author", "x": 10, "y": 20, "width": 80, "height": 10}
            ]
            pdf = PdfReader(BytesIO(export_pdf(repo, article)))
            self.assertIn("Alex & Casey", pdf.pages[0].extract_text())
            self.assertNotIn("Author:", pdf.pages[2].extract_text())

    def test_site_downloads_only_published_editions_and_keeps_table_text(self):
        from pypdf import PdfReader

        with TemporaryDirectory() as directory:
            root = Path(directory)
            collection = root / "collection"
            shutil.copytree(Path(__file__).resolve().parents[1] / "example", collection)
            repo = Repository(collection)
            # The regression runs on machines without a CJK system font.
            for article in collection.glob("articles/*/zh-CN.md"):
                metadata, body = load_article(article)
                save_article(article, {**metadata, "status": "draft"}, body)
            site = root / "site"
            export_html(repo, site)
            self.assertEqual(
                {path.relative_to(site).as_posix() for path in site.rglob("*.pdf")},
                {"articles/FIELD-000001/en-US.pdf", "articles/FIELD-000002/en-US.pdf"},
            )
            self.assertIn(
                'href="articles/FIELD-000001/en-US.pdf" download="FIELD-000001 Restore a room display with no signal.pdf"',
                (site / "index.html").read_text(encoding="utf-8"),
            )
            self.assertIn(
                'href="en-US.pdf" download="FIELD-000001 Restore a room display with no signal.pdf"',
                (site / "articles/FIELD-000001/en-US.html").read_text(encoding="utf-8"),
            )
            pdf = PdfReader(site / "articles/FIELD-000001/en-US.pdf")
            text = "\n".join(page.extract_text() for page in pdf.pages)
            self.assertIn("Screen message", text)
            self.assertIn("Unsupported format", text)

            article = repo.article_path("FIELD-000002", "en-US")
            metadata, body = load_article(article)
            save_article(article, {**metadata, "cover_pdf": "missing.pdf"}, body)
            failed = root / "failed"
            with self.assertRaisesRegex(ValueError, r"FIELD-000002 \(en-US\)"):
                export_html(repo, failed)
            self.assertFalse(failed.exists())
