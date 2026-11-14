"""Render the portable page theme with ReportLab and pypdf."""

from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
from threading import Lock
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    XPreformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents

FONT_LOCK = Lock()
INK = HexColor("#202020")
MUTED = HexColor("#555555")


def document_fonts(theme, text):
    configured = theme.get("font") or os.environ.get("KBFORGE_PDF_FONT")
    if not configured and not re.search(r"[\u2e80-\u9fff]", text):
        return "Helvetica", "Helvetica-Bold"
    candidates = (
        (Path(configured),)
        if configured
        else (
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc",
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        )
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise ValueError(
            "For Chinese PDF text, set publishing.font or KBFORGE_PDF_FONT to a CJK TrueType font."
        )
    try:
        font_data = path.read_bytes()
        name = "KBForge-" + sha256(font_data).hexdigest()[:24]
        with FONT_LOCK:
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(
                    TTFont(name, BytesIO(font_data), asciiReadable=True)
                )
        font = pdfmetrics.getFont(name)
    except Exception as error:
        raise ValueError(f"Cannot load the PDF TrueType font: {path.name}") from error
    missing = {
        char
        for char in text
        if ord(char) > 127 and ord(char) not in font.face.charToGlyph
    }
    if missing:
        raise ValueError(
            f"The PDF font lacks glyphs for: {''.join(sorted(missing)[:12])}"
        )
    return name, name


class Publication(BaseDocTemplate):
    def __init__(self, stream, size, metadata, theme, fonts, chinese):
        super().__init__(
            stream, pagesize=size, title=str(metadata["title"]), allowSplitting=1
        )
        self.metadata = metadata
        self.theme = theme
        self.chinese = chinese
        width, height = size
        self.margin = width * 0.1
        self.measure = width - 2 * self.margin
        self.unit = width / 419.5
        self.font, bold = fonts
        self.styles = {}
        for key, f, font_size, leading, before, after in (
            ("title", bold, 21, 26, 0, 14),
            ("section", bold, 15, 18, 9, 5),
            ("step", bold, 11, 14, 7, 4),
            ("body", self.font, 10.5, 14, 0, 5),
            ("caption", self.font, 8, 11, 3, 7),
            ("code", self.font, 9, 12, 0, 7),
        ):
            self.styles[key] = ParagraphStyle(
                key,
                fontName=f,
                fontSize=font_size * self.unit,
                leading=leading * self.unit,
                spaceBefore=before * self.unit,
                spaceAfter=after * self.unit,
                textColor=MUTED if key == "caption" else INK,
                wordWrap="CJK" if chinese else None,
                keepWithNext=key in ("section", "step"),
            )
        frame = Frame(
            self.margin,
            height * 0.101,
            self.measure,
            height * 0.791,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate("document", [frame], onPage=self.draw_page))

    def artwork(self, canvas, key, x, top, width, max_height):
        if key not in self.theme:
            return 0
        image = ImageReader(self.theme[key])
        w, h = image.getSize()
        scale = min(width / w, max_height / h)
        canvas.drawImage(image, x, top - h * scale, w * scale, h * scale, mask="auto")
        return h * scale

    def draw_page(self, canvas, doc):
        width, height = self.pagesize
        if doc.page == 1 and self.theme.get("cover_pdf"):
            return
        margin, unit = self.margin, self.unit
        self.artwork(canvas, "header_image", 0, height, width, height * 0.055)
        if "footer_image" in self.theme:
            image = ImageReader(self.theme["footer_image"])
            w, h = image.getSize()
            self.artwork(
                canvas,
                "footer_image",
                0,
                min(height * 0.09, width * h / w),
                width,
                height * 0.09,
            )
        self.artwork(canvas, "logo", margin, height * 0.947, 64 * unit, 14 * unit)
        detail = f"{self.metadata.get('revision', '')}  |  {self.metadata.get('updated_on', '')}"
        canvas.setFillColor(MUTED)
        canvas.setFont(self.font, 8 * unit)
        article_id = str(self.metadata["id"])
        if doc.page == 1:
            title = Paragraph(escape(str(self.metadata["title"])), self.styles["title"])
            _, title_height = title.wrap(self.measure, height)
            top = height * 0.86 - title_height
            title.drawOn(canvas, margin, top)
            art_height = self.artwork(
                canvas,
                "cover_image",
                margin,
                top - 14 * unit,
                self.measure,
                height * 0.43,
            )
            canvas.drawString(
                margin, top - art_height - 32 * unit, article_id + "  |  " + detail
            )
            return
        canvas.drawRightString(width - margin, height * 0.933, article_id)
        canvas.setStrokeColor(HexColor("#b7b7b7"))
        canvas.setLineWidth(0.45)
        for position in (height * 0.914, height * 0.084):
            canvas.line(margin, position, width - margin, position)
        canvas.drawString(
            margin,
            height * 0.064,
            ("修订版 " if self.chinese else "Revision ") + detail,
        )
        page = f"第 {doc.page} 页" if self.chinese else f"Page {doc.page}"
        canvas.drawRightString(width - margin, height * 0.064, page)

    def afterFlowable(self, flowable):
        entry = getattr(flowable, "toc_entry", None)
        if entry:
            level, destination, title = entry
            self.canv.bookmarkHorizontalAbsolute(
                destination, self.frame._y + flowable.height
            )
            self.notify("TOCEntry", (level, escape(title), self.page, destination))


def make_story(doc, blocks, depth):
    flow = []
    for index, block in enumerate(blocks):
        kind, text = block["kind"], block["text"]
        if kind == "image":
            image = Image(block["image"])
            scale = min(
                doc.measure / image.imageWidth, 150 * doc.unit / image.imageHeight
            )
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            image.hAlign = "LEFT"
            group = [image, Paragraph(escape(text), doc.styles["caption"])]
            if (
                flow
                and isinstance(flow[-1], Paragraph)
                and flow[-1].style is doc.styles["body"]
            ):
                group.insert(0, flow.pop())
            flow.append(KeepTogether(group))
            continue
        level = block.get("level", 0)
        key = (
            ("section" if level <= 2 else "step")
            if level
            else ("code" if kind == "code" else "body")
        )
        node = (XPreformatted if kind == "code" else Paragraph)(
            escape(text), doc.styles[key]
        )
        if 0 < level <= depth:
            node.toc_entry = (max(0, level - 2), f"section-{index}", text)
        flow.append(node)
    return flow


def render_pdf(metadata, theme, blocks):
    chinese = str(metadata.get("language", "")).lower().startswith("zh")
    text = str(metadata["title"]) + "".join(block["text"] for block in blocks)
    fonts = document_fonts(theme, text + ("目录修订版第页" if chinese else ""))
    cover = None
    size = LETTER if theme["paper"] == "Letter" else A4
    if theme.get("cover_pdf"):
        try:
            cover = PdfReader(theme["cover_pdf"]).pages[0]
            box = cover.mediabox
            if cover.rotation or tuple(box.lower_left) != (0, 0):
                raise ValueError(
                    "The original cover must be unrotated with a zero-origin media box."
                )
            size = (float(box.width), float(box.height))
        except (PdfReadError, IndexError) as error:
            raise ValueError("The original cover is not a readable PDF.") from error

    stream = BytesIO()
    doc = Publication(stream, size, metadata, theme, fonts, chinese)
    depth = theme["toc_depth"]
    flow = make_story(doc, blocks, depth)
    story = [Spacer(1, 1), PageBreak()]
    levels = max(1, depth - 1)
    if any(block.get("level", 0) in range(1, depth + 1) for block in blocks):
        toc = TableOfContents(dotsMinLevel=0)
        toc.levelStyles = [
            ParagraphStyle(
                f"toc-{level}",
                fontName=fonts[0],
                fontSize=11 * doc.unit,
                leading=16 * doc.unit,
                leftIndent=level * 9 * doc.unit,
                rightIndent=28 * doc.unit,
                spaceAfter=5 * doc.unit,
                wordWrap="CJK" if chinese else None,
            )
            for level in range(levels)
        ]
        story.extend(
            [
                Paragraph(
                    "目录" if chinese else "Table of Contents", doc.styles["title"]
                ),
                toc,
                PageBreak(),
            ]
        )
    story.extend(flow or [Spacer(1, 1)])
    doc.multiBuild(story)
    if cover is None:
        return stream.getvalue()
    writer = PdfWriter(clone_from=BytesIO(stream.getvalue()))
    writer.pages[0].merge_page(cover)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()
