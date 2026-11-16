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
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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
    """Select fonts with the needed glyphs and register embedded fonts once per process."""
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

    def draw_custom_cover(self, canvas, layout):
        """Draw boxes measured from the page's top-left corner."""
        page_width, page_height = self.pagesize
        for index, box in enumerate(layout, 1):
            x, width = (box[key] * page_width / 100 for key in ("x", "width"))
            y, height = (box[key] * page_height / 100 for key in ("y", "height"))
            top = page_height - y
            align = box.get("align", "left")
            if "image" in box:
                asset = self.theme.get(box["image"])
                if not asset:
                    continue
                image = ImageReader(asset)
                image_width, image_height = image.getSize()
                scale = min(width / image_width, height / image_height)
                fitted_width = image_width * scale
                offset = {
                    "left": 0,
                    "center": (width - fitted_width) / 2,
                    "right": width - fitted_width,
                }[align]
                canvas.drawImage(
                    image,
                    x + offset,
                    top - image_height * scale,
                    fitted_width,
                    image_height * scale,
                    mask="auto",
                )
                continue
            text = cover_text(self.metadata, self.theme, box)
            if not text:
                continue
            size = box.get("size", 12)
            parent = self.styles["title" if box.get("bold") else "body"]
            style = ParagraphStyle(
                "cover element",
                parent=parent,
                fontSize=size,
                leading=size * 1.2,
                textColor=HexColor(box.get("color", "#202020")),
                alignment={"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}[
                    align
                ],
            )
            paragraph = Paragraph(escape(text).replace("\n", "<br/>"), style)
            _, text_height = paragraph.wrap(width, height)
            if text_height > height + 0.01:
                raise ValueError(
                    f"Cover element {index} text does not fit. Increase its height or reduce its font size."
                )
            paragraph.drawOn(canvas, x, top - text_height)

    def draw_page(self, canvas, doc):
        width, height = self.pagesize
        if doc.page == 1 and self.theme.get("cover_pdf"):
            return
        if doc.page == 1 and self.theme.get("cover_layout"):
            self.draw_custom_cover(canvas, self.theme["cover_layout"])
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
        # Record the heading destination after pagination gives it a page number.
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
        style = doc.styles[key]
        list_depth = block.get("list_depth", 0)
        marker = block.get("marker")
        if list_depth:
            # Draw the marker in the gutter and align wrapped lines with the item text.
            indent = 12 * min(list_depth, 5) * doc.unit
            marker_width = pdfmetrics.stringWidth(
                marker or "•", style.fontName, style.fontSize
            )
            style = ParagraphStyle(
                "list-item",
                parent=style,
                bulletFontName=style.fontName,
                bulletFontSize=style.fontSize,
                bulletIndent=indent,
                leftIndent=indent + max(14 * doc.unit, marker_width + 5 * doc.unit),
            )
        if kind == "code":
            node = XPreformatted(escape(text), style)
        else:
            node = Paragraph(escape(text), style, bulletText=marker)
        if 0 < level <= depth:
            node.toc_entry = (max(0, level - 2), f"section-{index}", text)
        flow.append(node)
    return flow


def cover_text(metadata, theme, box):
    if "image" in box:
        return ""
    if "text" in box:
        return box["text"]
    field = box["field"]
    value = (
        theme.get("organization") if field == "organization" else metadata.get(field)
    )
    return "" if value is None else str(value)


def render_pdf(metadata, theme, blocks):
    chinese = str(metadata.get("language", "")).lower().startswith("zh")
    text = str(metadata["title"]) + "".join(block["text"] for block in blocks)
    text += "".join(
        cover_text(metadata, theme, box) for box in theme.get("cover_layout") or []
    )
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
    # Reflow until the contents entries and page numbers agree.
    doc.multiBuild(story)
    if cover is None:
        return stream.getvalue()
    writer = PdfWriter(clone_from=BytesIO(stream.getvalue()))
    writer.pages[0].merge_page(cover)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()
