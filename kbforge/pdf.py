"""Build a paginated PDF using the collection's declarative theme."""

import json
import re
from pathlib import Path
from importlib.util import find_spec

from .repository import image_width, load_article, pandoc
from .fonts import code_font, publication_fonts
from urllib.parse import unquote, urlsplit


def theme_asset(repo, name, suffixes):
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError("Use a filename from the branding directory.")
    path = repo.path("branding", name)
    if path.suffix.lower() not in suffixes or not path.is_file():
        raise ValueError(f"Missing or unsupported branding asset: {name}")
    return path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def pdf_theme(repo, metadata):
    """Resolve a collection theme, applying the article-specific cover if present."""
    settings = repo.config.get("publishing", {})
    assets = {}
    for key in ("cover_image", "header_image", "footer_image"):
        if settings.get(key):
            assets[key] = str(theme_asset(repo, settings[key], IMAGE_SUFFIXES))
    if metadata.get("cover_pdf"):
        assets["cover_pdf"] = str(theme_asset(repo, metadata["cover_pdf"], {".pdf"}))
    size = settings.get("paper", "A4")
    if size not in ("A4", "Letter"):
        raise ValueError("Publishing paper must be A4 or Letter.")
    depth = settings.get("toc_depth", 2)
    if type(depth) is not int or not 0 <= depth <= 6:
        raise ValueError("Publishing toc_depth must be an integer from 0 to 6.")
    return {**assets, "paper": size, "toc_depth": depth}


COVER_IMAGES = {"logo", "cover_image", "header_image", "footer_image"}
COVER_FIELDS = {
    "title",
    "id",
    "revision",
    "updated_on",
    "owner",
    "author",
    "status",
    "language",
    "organization",
}


def cover_layout(settings):
    """Validate percentage-based cover boxes independently of the PDF engine."""
    if "cover_layout" not in settings:
        return None
    layout = settings["cover_layout"]
    if not isinstance(layout, list) or not 1 <= len(layout) <= 50:
        raise ValueError("publishing.cover_layout must contain 1 to 50 elements.")
    for index, box in enumerate(layout, 1):

        def fail(message):
            return ValueError(f"Cover element {index}: {message}")

        if not isinstance(box, dict):
            raise fail("expected an object.")
        sources = box.keys() & {"image", "field", "text"}
        if len(sources) != 1:
            raise fail("specify one of image, field, or text.")
        source = next(iter(sources))
        value = box[source]
        if not isinstance(value, str) or not value.strip():
            raise fail("the image, field, or text must be a nonempty string.")
        if source == "image" and value not in COVER_IMAGES:
            raise fail("unknown image role.")
        if source == "field" and value not in COVER_FIELDS:
            raise fail("unknown metadata field.")
        allowed = {source, "x", "y", "width", "height", "align"}
        if source != "image":
            allowed |= {"size", "bold", "color"}
        if box.keys() - allowed:
            raise fail("unknown element settings.")
        coordinates = [box.get(key) for key in ("x", "y", "width", "height")]
        if any(
            type(number) not in (int, float) or not 0 <= number <= 100
            for number in coordinates
        ):
            raise fail("x, y, width and height must be percentages between 0 and 100.")
        x, y, width, height = coordinates
        if not width or not height or x + width > 100 or y + height > 100:
            raise fail("the box must have positive dimensions and fit on the page.")
        if box.get("align", "left") not in ("left", "center", "right"):
            raise fail("align must be left, center, or right.")
        size = box.get("size", 12)
        if type(size) not in (int, float) or not 4 <= size <= 144:
            raise fail("size must be between 4 and 144 points.")
        if type(box.get("bold", False)) is not bool:
            raise fail("bold must be true or false.")
        color = box.get("color", "#202020")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise fail("color must be a six-digit hex color.")
    return layout


def inline_runs(nodes, bold=False, italic=False):
    for node in nodes:
        kind, value = node["t"], node.get("c")
        if kind in ("Str", "Code", "Math"):
            yield (value if kind == "Str" else value[1]), bold, italic
        elif kind in ("Space", "SoftBreak", "LineBreak"):
            yield ("\n" if kind == "LineBreak" else " "), bold, italic
        elif kind in ("Link", "Image", "Span", "Quoted"):
            yield from inline_runs(value[1], bold, italic)
        elif kind in (
            "Emph",
            "Strong",
            "Strikeout",
            "SmallCaps",
            "Superscript",
            "Subscript",
        ):
            yield from inline_runs(
                value, bold or kind == "Strong", italic or kind == "Emph"
            )


def inline(nodes):
    return "".join(text for text, _, _ in inline_runs(nodes))


def pdf_table(value):
    """Extract rows and column alignment from a Pandoc GFM pipe table."""
    _, _, columns, (_, headers), bodies, (_, footer) = value
    rows = (
        headers + [row for _, _, head, body in bodies for row in head + body] + footer
    )
    cells = [
        [" ".join(inline(block["c"]) for block in blocks) for _, _, _, _, blocks in row]
        for _, row in rows
    ]
    return {
        "kind": "table",
        "text": " ".join(cell for row in cells for cell in row),
        "rows": cells,
        "header_rows": len(headers),
        "alignments": [alignment["t"] for alignment, _ in columns],
    }


def pdf_blocks(repo, path, blocks):
    """Adapt Pandoc nodes into the blocks the paginated renderer supports."""
    for node in blocks:
        kind, value = node["t"], node.get("c")
        if kind == "Header":
            level, _, title = value
            yield {
                "kind": "heading",
                "level": level,
                "text": inline(title),
                "runs": list(inline_runs(title)),
            }
        elif kind in ("Para", "Plain"):
            pending = []
            for item in value:
                if item["t"] != "Image":
                    pending.append(item)
                    continue
                if inline(pending).strip():
                    yield {
                        "kind": "text",
                        "text": inline(pending),
                        "runs": list(inline_runs(pending)),
                    }
                pending = []
                reference = item["c"][2][0]
                parts = urlsplit(reference)
                image = (path.parent / unquote(parts.path)).resolve()
                if (
                    parts.scheme
                    or parts.netloc
                    or Path(unquote(parts.path)).is_absolute()
                    or image.parent
                    != repo.path("articles", path.parent.name, "assets").resolve()
                    or image.suffix.lower() not in IMAGE_SUFFIXES
                    or not image.is_file()
                ):
                    raise ValueError(f"Invalid local image: {reference}")
                yield {
                    "kind": "image",
                    "text": inline(item["c"][1]),
                    "image": str(image),
                    "width": image_width(item["c"][0]),
                }
            if inline(pending).strip():
                yield {
                    "kind": "text",
                    "text": inline(pending),
                    "runs": list(inline_runs(pending)),
                }
        elif kind in ("BulletList", "OrderedList"):
            start, items = (
                (None, value) if kind == "BulletList" else (value[0][0], value[1])
            )
            for index, item in enumerate(items):
                marker = "•" if start is None else f"{start + index}."
                gutter = max(14, 6 * len(marker) + 5)
                for entry in pdf_blocks(repo, path, item):
                    if (
                        "indent" not in entry
                        and marker
                        and entry["kind"] not in ("code", "table")
                    ):
                        entry["marker"] = (marker, gutter)
                        marker = ""
                    entry["indent"] = entry.get("indent", 0) + 12 + gutter
                    yield entry
        elif kind == "BlockQuote" or kind == "Div":
            quoted = kind == "BlockQuote" or bool(
                set(value[0][1]) & {"note", "tip", "important", "warning", "caution"}
            )
            for entry in pdf_blocks(
                repo, path, value if kind == "BlockQuote" else value[1]
            ):
                if quoted:
                    entry["quoted"] = True
                yield entry
        elif kind == "CodeBlock":
            yield {"kind": "code", "text": value[1]}
        elif kind == "Table":
            yield pdf_table(value)
        elif kind not in ("RawBlock", "Null", "HorizontalRule"):
            raise ValueError(
                f"The paginated PDF renderer does not support {kind}. Use browser print for this article."
            )


def pdf_available():
    """Keep HTML publishing usable when the optional PDF dependencies are absent."""
    return all(find_spec(module) is not None for module in ("reportlab", "pypdf"))


def export_pdf(repo, path):
    if not pdf_available():
        raise ValueError(
            "Install PDF support with python -m pip install -r requirements-pdf.txt."
        )
    from reportlab.platypus.doctemplate import LayoutError

    from .pdf_renderer import render_pdf

    metadata, body = load_article(path)
    theme = pdf_theme(repo, metadata)
    if repo.config["branding"].get("logo"):
        theme["logo"] = str(
            theme_asset(repo, repo.config["branding"]["logo"], IMAGE_SUFFIXES)
        )
    settings = repo.config.get("publishing", {})
    if "body_font_size" in settings:
        size = settings["body_font_size"]
        if type(size) not in (int, float) or not 8 <= size <= 18:
            raise ValueError(
                "publishing.body_font_size must be between 8 and 18 points."
            )
        theme["body_font_size"] = size
    theme["typography"] = publication_fonts(repo)
    theme["code_font"] = code_font(repo)
    if not theme.get("cover_pdf"):
        theme["cover_layout"] = cover_layout(settings)
    theme["organization"] = repo.config["branding"].get("name", "")
    blocks = list(pdf_blocks(repo, path, json.loads(pandoc(body, "json"))["blocks"]))
    try:
        return render_pdf(metadata, theme, blocks)
    except LayoutError as error:
        raise ValueError(
            "Page layout failed. Check for content too large to fit."
        ) from error
