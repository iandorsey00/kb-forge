"""Verify real font instances and portable font assets using licensed fixtures."""

from io import BytesIO
import json
from pathlib import Path
from shutil import copyfile, copytree
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from kbforge.fonts import font_info, read_face
from kbforge.pdf import export_pdf, pdf_available
from kbforge.publishing import export_html
from kbforge.repository import Repository, load_article, save_article
from kbforge.theme import export_theme, import_theme


@unittest.skipUnless(pdf_available(), "Optional PDF dependencies are missing")
class FontTest(unittest.TestCase):
    def test_variable_pdf_web_and_theme(self):
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        from pypdf import PdfReader

        from kbforge.fonts import publication_fonts
        from kbforge.pdf_fonts import DocumentFonts, instance_coordinates

        with TemporaryDirectory() as directory:
            root = Path(directory)
            example = Path(__file__).resolve().parents[1] / "example"
            copytree(example, root / "collection")
            repo = Repository(root / "collection")
            repo.config["workspace"] = {"name": "Support Workspace"}
            publishing = repo.config.setdefault("publishing", {})
            publishing.update(
                fonts={
                    "regular": "InterVariable.ttf",
                    "italic": "InterVariable-Italic.ttf",
                },
                font_weights={"heading": 600, "caption": 500},
                font_fallbacks={"zh-CN": "FixtureCJK.ttf"},
                code_font="SourceCodePro-Regular.ttf",
                font_licenses=["Inter-OFL.txt", "SourceCodePro-OFL.txt"],
            )
            # A one-character TrueType fixture keeps this check independent of system fonts.
            builder = FontBuilder(1000, isTTF=True)
            builder.setupGlyphOrder([".notdef", "han"])
            builder.setupCharacterMap({ord("汉"): "han"})
            box = TTGlyphPen(None)
            box.moveTo((100, 100))
            box.lineTo((700, 100))
            box.lineTo((700, 700))
            box.closePath()
            builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "han": box.glyph()})
            builder.setupHorizontalMetrics({".notdef": (800, 0), "han": (800, 100)})
            builder.setupHorizontalHeader(ascent=800, descent=-200)
            builder.setupNameTable(
                {
                    "familyName": "FixtureCJK",
                    "styleName": "Regular",
                    "psName": "FixtureCJK",
                }
            )
            builder.setupOS2(
                sTypoAscender=800,
                sTypoDescender=-200,
                usWinAscent=800,
                usWinDescent=200,
            )
            builder.setupPost()
            builder.save(repo.root / "branding" / "FixtureCJK.ttf")

            data = (repo.root / "branding" / "InterVariable.ttf").read_bytes()
            axes = font_info(data).axes
            self.assertEqual((axes["wght"][0], axes["wght"][2]), (100, 900))
            self.assertEqual(instance_coordinates(axes, 1, False)["wght"], 100)
            self.assertEqual(instance_coordinates(axes, 1000, False)["wght"], 900)
            self.assertEqual(
                instance_coordinates(axes, 500, False)["opsz"], axes["opsz"][1]
            )
            self.assertEqual(
                instance_coordinates({"slnt": (-8, 0, 0)}, 400, True)["slnt"], -8
            )
            self.assertEqual(
                instance_coordinates({"ital": (0, 0, 1)}, 400, True)["ital"], 1
            )

            article = repo.article_path("FIELD-000001", "en-US")
            metadata, body = load_article(article)
            save_article(
                article,
                metadata,
                body + "\n\nRegular **bold** *italic* ***both*** 汉.\n"
                "\n```text\n  Run this command\n```\n",
            )
            with patch("kbforge.pdf_fonts.default_cjk_paths", return_value=()):
                reader = PdfReader(BytesIO(export_pdf(repo, article)))
            text = "".join(page.extract_text() for page in reader.pages)
            self.assertIn("Regular bold italic both 汉.", text)
            embedded = {}
            for page in reader.pages:
                for resource in page["/Resources"].get("/Font", {}).values():
                    face = resource.get_object()
                    descriptor = face.get("/FontDescriptor")
                    if descriptor and "/FontFile2" in descriptor.get_object():
                        embedded[face["/BaseFont"]] = face
            self.assertGreaterEqual(
                sum("InterVariable-" in name for name in embedded), 3
            )
            self.assertEqual(
                sum("InterVariableItalic-" in name for name in embedded), 2
            )
            self.assertTrue(any("FixtureCJK" in name for name in embedded))
            self.assertTrue(any("SourceCodePro" in name for name in embedded))
            self.assertIn("  Run this command", text)

            fonts = DocumentFonts({"typography": publication_fonts(repo)}, "en-US")
            self.assertEqual(
                fonts.primary_face(700),
                DocumentFonts(
                    {"typography": publication_fonts(repo)}, "en-US"
                ).primary_face(700),
            )
            self.assertNotEqual(fonts.primary_face(500), fonts.primary_face(600))
            with self.assertRaisesRegex(ValueError, r"U\+1F4A1"):
                fonts.match("💡", 400, False)
            bad = root / "bad.ttf"
            bad.write_bytes(b"not a font")
            with self.assertRaisesRegex(ValueError, "Cannot use font bad.ttf"):
                read_face(bad)

            site = root / "site"
            export_html(repo, site, include_pdfs=False)
            self.assertIn(
                "<h1>Support Workspace</h1>",
                (site / "index.html").read_text(encoding="utf-8"),
            )
            css = (site / "fonts.css").read_text(encoding="utf-8")
            self.assertIn("font-style:italic;font-weight:100 900", css)
            self.assertIn('font-family:"KBForgeCode"', css)
            self.assertIn("--document-weight:600", css)
            self.assertIn("strong{font-weight:max(700", css)
            manifest = json.loads((site / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("fonts/Inter-OFL.txt", manifest["font_assets"])
            self.assertIn("fonts/SourceCodePro-OFL.txt", manifest["font_assets"])
            self.assertEqual(len(list((site / "fonts").glob("*.ttf"))), 4)
            self.assertIn(
                "../../fonts.css",
                (site / "articles/FIELD-000001/en-US.html").read_text(encoding="utf-8"),
            )

            theme = root / "theme.zip"
            export_theme(repo, theme)
            copytree(example, root / "destination")
            destination = Repository(root / "destination")
            import_theme(destination, theme)
            restored = Repository(root / "destination")
            self.assertEqual(
                restored.config["publishing"]["fonts"], publishing["fonts"]
            )
            self.assertTrue((restored.root / "branding/FixtureCJK.ttf").is_file())
            self.assertEqual(
                restored.config["publishing"]["code_font"], publishing["code_font"]
            )

    def test_static_legacy_and_environment(self):
        import reportlab
        from kbforge.fonts import publication_fonts
        from kbforge.pdf_fonts import DocumentFonts

        with TemporaryDirectory() as directory:
            root = Path(directory)
            copytree(
                Path(__file__).resolve().parents[1] / "example", root / "collection"
            )
            repo = Repository(root / "collection")
            sources = Path(reportlab.__file__).parent / "fonts"
            files = {
                "regular": "Vera.ttf",
                "bold": "VeraBd.ttf",
                "italic": "VeraIt.ttf",
                "bold_italic": "VeraBI.ttf",
            }
            for file in files.values():
                copyfile(sources / file, repo.root / "branding" / file)

            config = repo.config.setdefault("publishing", {})
            config.update(font="VeraBd.ttf", fonts=files)
            with patch.dict(
                "os.environ",
                {"KBFORGE_PDF_FONT": str(repo.root / "branding/VeraIt.ttf")},
            ):
                fonts = DocumentFonts({"typography": publication_fonts(repo)}, "en-US")
                self.assertEqual(
                    len(
                        {
                            fonts.primary_face(weight, italic)
                            for weight in (400, 700)
                            for italic in (False, True)
                        }
                    ),
                    4,
                )
                del config["fonts"]
                legacy = DocumentFonts({"typography": publication_fonts(repo)}, "en-US")
                self.assertEqual(legacy.primary_face(400), legacy.primary_face(700))
                self.assertIn("Bold", legacy.primary_face(400))
                del config["font"]
                self.assertIn(
                    "Oblique",
                    DocumentFonts(
                        {"typography": publication_fonts(repo)}, "en-US"
                    ).primary_face(400),
                )
