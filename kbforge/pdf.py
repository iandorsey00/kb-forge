"""Build a paginated PDF using the collection's declarative theme."""

import json
from pathlib import Path
from importlib.util import find_spec

from .repository import load_article, pandoc
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


def inline(nodes):
    parts = []
    for node in nodes:
        kind, value = node["t"], node.get("c")
        if kind in ("Str", "Code", "Math"):
            parts.append(value if kind == "Str" else value[1])
        elif kind in ("Space", "SoftBreak", "LineBreak"):
            parts.append("\n" if kind == "LineBreak" else " ")
        elif kind in ("Link", "Image", "Span", "Quoted"):
            parts.append(inline(value[1]))
        elif kind in (
            "Emph",
            "Strong",
            "Strikeout",
            "SmallCaps",
            "Superscript",
            "Subscript",
        ):
            parts.append(inline(value))
    return "".join(parts)


def pdf_blocks(repo, path, blocks):
    for node in blocks:
        kind, value = node["t"], node.get("c")
        if kind == "Header":
            level, _, title = value
            yield {"kind": "heading", "level": level, "text": inline(title)}
        elif kind in ("Para", "Plain"):
            pending = []
            for item in value:
                if item["t"] != "Image":
                    pending.append(item)
                    continue
                if inline(pending).strip():
                    yield {"kind": "text", "text": inline(pending)}
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
                }
            if inline(pending).strip():
                yield {"kind": "text", "text": inline(pending)}
        elif kind in ("BulletList", "OrderedList"):
            start, items = (
                (None, value) if kind == "BulletList" else (value[0][0], value[1])
            )
            for index, item in enumerate(items):
                prefix = "•  " if start is None else f"{start + index}.  "
                for entry in pdf_blocks(repo, path, item):
                    if entry["kind"] == "text" and prefix:
                        entry["text"] = prefix + entry["text"]
                        prefix = ""
                    yield entry
        elif kind in ("BlockQuote", "Div"):
            yield from pdf_blocks(
                repo, path, value if kind == "BlockQuote" else value[1]
            )
        elif kind == "CodeBlock":
            yield {"kind": "code", "text": value[1]}
        elif kind not in ("RawBlock", "Null", "HorizontalRule"):
            raise ValueError(
                f"The paginated PDF renderer does not support {kind}. Use browser print for this article."
            )


def pdf_available():
    return all(find_spec(module) is not None for module in ("reportlab", "pypdf"))


def export_pdf(repo, path):
    if not pdf_available():
        raise ValueError(
            "Install PDF support with python -m pip install -r requirements-pdf.txt."
        )
    from .pdf_renderer import render_pdf

    metadata, body = load_article(path)
    theme = pdf_theme(repo, metadata)
    if repo.config["branding"].get("logo"):
        theme["logo"] = str(
            theme_asset(repo, repo.config["branding"]["logo"], IMAGE_SUFFIXES)
        )
    settings = repo.config.get("publishing", {})
    if settings.get("font"):
        theme["font"] = str(theme_asset(repo, settings["font"], {".ttf", ".ttc"}))
    blocks = list(pdf_blocks(repo, path, json.loads(pandoc(body, "json"))["blocks"]))
    return render_pdf(metadata, theme, blocks)
