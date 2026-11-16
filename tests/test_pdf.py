"""Regression checks for the built-in paginated PDF renderer."""

from io import BytesIO
from pathlib import Path
import unittest

from kbforge.pdf import export_pdf, pdf_available
from kbforge.repository import Repository


@unittest.skipUnless(pdf_available(), "Optional PDF dependencies are missing")
class PublishingTest(unittest.TestCase):
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
