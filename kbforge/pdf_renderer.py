"""Render the portable page theme with ReportLab and pypdf."""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    XPreformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents

from .pdf import TASK_MARKERS
from .pdf_fonts import DocumentFonts
from .repository import article_author

INK = HexColor("#202020")
MUTED = HexColor("#555555")
QUOTE = HexColor("#edf1f5")


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
        self.fonts = fonts
        body_weight, heading_weight, caption_weight = (
            fonts.weights[key] for key in ("body", "heading", "caption")
        )
        self.font = fonts.primary_face(body_weight)
        self.styles = {}
        body_size = theme.get("body_font_size", 11) / self.unit
        for key, weight, font_size, leading, before, after in (
            ("title", heading_weight, 21, 26, 0, 14),
            (
                "section",
                heading_weight,
                max(12, body_size + 2.5),
                max(15, body_size + 5),
                9,
                5,
            ),
            ("step", heading_weight, body_size + 1, body_size * 1.35, 7, 4),
            ("body", body_weight, body_size, body_size * 1.38, 0, 5),
            ("caption", caption_weight, 8, 11, 3, 7),
            ("code", body_weight, 9, 12, 0, 7),
        ):
            self.styles[key] = ParagraphStyle(
                key,
                fontName=fonts.primary_face(weight),
                fontWeight=weight,
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
            paragraph = Paragraph(self.fonts.markup(text, style.fontWeight), style)
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
            style = self.styles["title"]
            title = Paragraph(
                self.fonts.markup(str(self.metadata["title"]), style.fontWeight), style
            )
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
        self.draw_label(
            canvas,
            margin,
            height * 0.064,
            ("修订版 " if self.chinese else "Revision ") + detail,
        )
        page = f"第 {doc.page} 页" if self.chinese else f"Page {doc.page}"
        self.draw_label(canvas, width - margin, height * 0.064, page, right=True)

    def draw_label(self, canvas, x, y, text, *, right=False):
        size = 8 * self.unit
        segments = [
            (font, part, pdfmetrics.stringWidth(part, font, size))
            for font, part in self.fonts.segments(text, self.fonts.weights["body"])
        ]
        if right:
            x -= sum(width for _, _, width in segments)
        for font, part, width in segments:
            canvas.setFont(font, size)
            canvas.drawString(x, y, part)
            x += width

    def afterFlowable(self, flowable):
        # Record the heading destination after pagination gives it a page number.
        entry = getattr(flowable, "toc_entry", None)
        if entry:
            level, destination, title = entry
            self.canv.bookmarkHorizontalAbsolute(
                destination, self.frame._y + flowable.height
            )
            self.notify(
                "TOCEntry",
                (
                    level,
                    self.fonts.markup(title, self.fonts.weights["body"]),
                    self.page,
                    destination,
                ),
            )


class ArticleImage(Image):
    def __init__(self, path, inset, marker, style, bullet_font):
        super().__init__(path)
        self.inset = inset
        self.marker = marker
        self.style = style
        self.bullet_font = bullet_font

    def draw(self):
        if self.marker:
            text, gutter = self.marker
            self.canv.setFillColor(INK)
            self.canv.setFont(self.bullet_font, self.style.fontSize)
            self.canv.drawString(
                self.inset - gutter, self.drawHeight - self.style.fontSize, text
            )
        self.canv.translate(self.inset, 0)
        super().draw()


def article_table(doc, block, width):
    alignments = {"AlignCenter": TA_CENTER, "AlignRight": TA_RIGHT}
    headers = block["header_rows"]
    columns = len(block["alignments"])
    styles = [
        ParagraphStyle(
            alignment,
            parent=doc.styles["body"],
            alignment=alignments.get(alignment, TA_LEFT),
            spaceAfter=0,
        )
        for alignment in block["alignments"]
    ]
    return LongTable(
        [
            [
                Paragraph(doc.fonts.markup(cell, style.fontWeight), style)
                for cell, style in zip(row, styles)
            ]
            for row in block["rows"]
        ],
        colWidths=[width / columns] * columns,
        repeatRows=headers,
        splitInRow=1,
        hAlign="LEFT",
        spaceAfter=doc.styles["body"].spaceAfter,
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, headers - 1), QUOTE),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#c7d1d8")),
        ],
    )


def make_story(doc, blocks, depth):
    flow = []
    for index, block in enumerate(blocks):
        kind, text = block["kind"], block["text"]
        indent = min(block.get("indent", 0) * doc.unit, doc.measure * 0.55)
        quoted = block.get("quoted")
        padding = 5 * doc.unit
        marker, gutter = block.get("marker", (None, 0))
        gutter *= doc.unit
        if kind == "table":
            flow.append(article_table(doc, block, doc.measure))
            continue
        if kind == "image":
            inset = indent + (12 * doc.unit if quoted else 0)
            available = doc.measure - inset - (padding if quoted else 0)
            width = block.get("width")
            body_style = doc.styles["body"]
            image = ArticleImage(
                block["image"],
                inset,
                (marker, gutter) if marker else None,
                body_style,
                doc.fonts.match(marker, body_style.fontWeight, False)
                if marker in TASK_MARKERS else body_style.fontName,
            )
            if width is None:
                scale = min(
                    available / image.imageWidth, 150 * doc.unit / image.imageHeight
                )
            else:
                scale = min(
                    available * width / 100 / image.imageWidth,
                    doc.pagesize[1] * 0.6 / image.imageHeight,
                )
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            image.hAlign = "LEFT"
            if text:
                image.keepWithNext = True
            flow.append(image)
            if text:
                caption = ParagraphStyle(
                    "image-caption", parent=doc.styles["caption"], leftIndent=inset
                )
                flow.append(
                    Paragraph(doc.fonts.markup(text, caption.fontWeight), caption)
                )
            continue
        level = block.get("level", 0)
        key = (
            ("section" if level <= 2 else "step")
            if level
            else ("code" if kind == "code" else "body")
        )
        style = doc.styles[key]
        if indent or quoted:
            inset = indent + (12 * doc.unit if quoted else 0)
            style = ParagraphStyle(
                "indented",
                parent=style,
                bulletFontName=doc.fonts.match(marker, style.fontWeight, False)
                if marker in TASK_MARKERS else style.fontName,
                bulletFontSize=style.fontSize,
                bulletIndent=inset - gutter,
                leftIndent=inset,
            )
            if quoted and kind != "code":
                style.backColor = QUOTE
                style.rightIndent = padding
                style.borderPadding = (padding / 2, padding, padding / 2, padding)
                style.spaceBefore = max(style.spaceBefore, padding)
                style.spaceAfter = max(style.spaceAfter, padding)
        if kind == "code":
            inset = 7 * doc.unit
            style = ParagraphStyle(
                "code-block",
                parent=style,
                fontName=doc.fonts.code_face(),
                leftIndent=style.leftIndent + inset,
                rightIndent=inset,
                backColor=QUOTE,
                borderColor=HexColor("#cbd5df"),
                borderWidth=0.5,
                borderPadding=(3, inset, 3, inset),
                spaceBefore=6 * doc.unit,
            )
            width = doc.measure - style.leftIndent - style.rightIndent
            lines = []
            for original in text.expandtabs(4).split("\n"):
                line, used = [], 0
                for char in original:
                    font = doc.fonts.match(char, 400, False, code=True)
                    size = pdfmetrics.stringWidth(char, font, style.fontSize)
                    if line and used + size > width:
                        lines.append("".join(line))
                        line, used = [], 0
                    line.append(char)
                    used += size
                lines.append("".join(line))
            markup = "\n".join(doc.fonts.markup(line, 400, code=True) for line in lines)
            node = XPreformatted(markup, style)
        else:
            runs = block.get("runs", [(text, False, False)])
            markup = "".join(
                doc.fonts.markup(
                    part,
                    max(700, style.fontWeight) if bold else style.fontWeight,
                    italic,
                )
                for part, bold, italic in runs
            )
            node = Paragraph(markup, style, bulletText=marker)
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
    if field == "author":
        return article_author(metadata)
    value = (
        theme.get("organization") if field == "organization" else metadata.get(field)
    )
    return "" if value is None else str(value)


def render_pdf(metadata, theme, blocks):
    chinese = str(metadata.get("language", "")).lower().startswith("zh")
    author = article_author(metadata)
    label = "作者：" if chinese else "Author: "
    byline = label + author if author else ""
    fonts = DocumentFonts(theme, str(metadata.get("language", "")))
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
    if author:
        doc.author = author
    depth = theme["toc_depth"]
    flow = make_story(doc, blocks, depth)
    story = [Spacer(1, 1), PageBreak()]
    levels = max(1, depth - 1)
    if any(block.get("level", 0) in range(1, depth + 1) for block in blocks):
        toc = TableOfContents(dotsMinLevel=0)
        toc.levelStyles = [
            ParagraphStyle(
                f"toc-{level}",
                fontName=fonts.primary_face(fonts.weights["body"]),
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
                    fonts.markup(
                        "目录" if chinese else "Table of Contents",
                        fonts.weights["heading"],
                    ),
                    doc.styles["title"],
                ),
                toc,
                PageBreak(),
            ]
        )
    # Keep imported covers intact, and let an explicit author box place the byline.
    if byline and (
        cover is not None
        or not any(
            box.get("field") == "author" for box in theme.get("cover_layout") or []
        )
    ):
        style = ParagraphStyle("byline", parent=doc.styles["body"], keepWithNext=True)
        story.append(Paragraph(fonts.markup(byline, style.fontWeight), style))
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
