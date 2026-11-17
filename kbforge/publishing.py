"""Render portable articles with collection branding."""

import base64
import html
import json
import mimetypes
from pathlib import Path
import subprocess
from urllib.parse import quote, unquote, urlencode, urlsplit

from .pdf import IMAGE_SUFFIXES, pdf_theme, theme_asset
from .repository import ASSET, article_author, load_article, pandoc


def esc(value):
    return html.escape(str(value), quote=True)


def article_url(path, page="article"):
    return f"/{page}?" + urlencode({"id": path.parent.name, "language": path.stem})


def image_data(path):
    """Embed a supported local image so the browser needs no separate asset request."""
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        raise ValueError("Unsupported image format.")
    with path.open("rb") as stream:
        data = stream.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Image exceeds 8 MiB.")
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def render_body(repo, path, body, link_for=article_url):
    """Rewrite local links and images at the AST level before generating HTML."""
    ast = json.loads(pandoc(body, "json"))

    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(child) for child in value]
        if not isinstance(value, dict):
            return value
        kind = value.get("t")
        if kind in ("RawBlock", "RawInline"):
            return (
                {"t": "Null"}
                if kind == "RawBlock"
                else {"t": "Str", "c": value["c"][1]}
            )
        if kind in ("Image", "Link"):
            content = value["c"]
            try:
                parts = urlsplit(content[-1][0])
                relative = unquote(parts.path)
                if Path(relative).is_absolute() and not parts.scheme:
                    raise ValueError
                if kind == "Image":
                    candidate = (path.parent / relative).resolve()
                    allowed = repo.path(
                        "articles", path.parent.name, "assets"
                    ).resolve()
                    if (
                        parts.scheme
                        or parts.netloc
                        or candidate.parent != allowed
                        or not ASSET.fullmatch(candidate.name)
                    ):
                        raise ValueError
                    content[-1][0] = image_data(candidate)
                elif parts.scheme in ("http", "https", "mailto"):
                    pass
                elif parts.scheme or parts.netloc:
                    raise ValueError
                elif relative:
                    candidate = (path.parent / relative).resolve()
                    if (
                        not candidate.is_relative_to(repo.path("articles").resolve())
                        or candidate.parent.parent != repo.path("articles").resolve()
                        or candidate.suffix != ".md"
                        or not candidate.is_file()
                    ):
                        raise ValueError
                    fragment = (
                        "#" + quote(unquote(parts.fragment)) if parts.fragment else ""
                    )
                    url = link_for(candidate)
                    if url is None:
                        raise ValueError
                    content[-1][0] = url + fragment
            except (OSError, ValueError):
                return {"t": "Span", "c": [["", [], []], rewrite(content[1])]}
        return {key: rewrite(child) for key, child in value.items()}

    ast["blocks"] = rewrite(ast["blocks"])
    try:
        return subprocess.run(
            ["pandoc", "--sandbox", "--from=json", "--to=html5", "--wrap=none"],
            input=json.dumps(ast),
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout
    except subprocess.SubprocessError as error:
        raise ValueError("Could not render the article.") from error


def branded_article(repo, path, link_for=article_url):
    import re

    metadata, body = load_article(path)
    brand = repo.config["branding"]
    color = brand.get("color", "")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#245450"
    logo = ""
    if brand.get("logo"):
        logo_path = repo.path("branding", Path(brand["logo"]).name)
        logo = f'<img class="logo" src="{esc(image_data(logo_path))}" alt="">'
    chinese = str(metadata.get("language", "")).lower().startswith("zh")
    author = article_author(metadata)
    byline = ""
    if author:
        label = "作者：" if chinese else "Author: "
        byline = f'<p class="document-control">{label}{esc(author)}</p>'
    labels = (
        ("修订版", "更新日期", "状态") if chinese else ("Revision", "Updated", "Status")
    )
    status = metadata.get("status", "")
    if chinese and isinstance(status, str):
        status = {"draft": "草稿", "published": "已发布", "retired": "已停用"}.get(
            status, status
        )
    elif isinstance(status, str) and status in ("draft", "published", "retired"):
        status = status.capitalize()
    status_separator = "：" if chinese else ": "
    related = []
    targets = metadata.get("related", [])
    if isinstance(targets, list):
        for target in targets:
            if not isinstance(target, str):
                continue
            try:
                other = repo.article_path(target, path.stem)
                if not other.is_file():
                    other = next(iter(sorted(other.parent.glob("*.md"))), other)
                other = repo.article_path(target, other.stem)
                other_metadata, _ = load_article(other)
                url = link_for(other)
                if url is None:
                    continue
                related.append(
                    f'<a href="{esc(url)}">{esc(other_metadata.get("title", target))}</a>'
                )
            except (OSError, ValueError):
                continue
    related_html = ""
    if related:
        label = "相关文章" if chinese else "Related articles"
        related_html = (
            f"<aside><strong>{label}</strong> · " + " · ".join(related) + "</aside>"
        )
    theme = pdf_theme(repo, metadata)
    settings = repo.config.get("publishing", {})
    if "html_cover_image" in settings:
        image = settings["html_cover_image"]
        if image is None:
            theme.pop("cover_image", None)
        else:
            theme["cover_image"] = str(theme_asset(repo, image, IMAGE_SUFFIXES))
    pictures = {}
    for key in ("header_image", "footer_image", "cover_image"):
        pictures[key] = (
            f'<img class="publication-art {key}" src="{esc(image_data(Path(theme[key])))}" alt="">'
            if key in theme
            else ""
        )
    return f'''<article class="publication" style="--brand:{color}" lang="{esc(metadata.get("language", ""))}">
{pictures["header_image"]}<header>{logo}<div>{esc(brand["name"])}</div>
<h1>{esc(metadata.get("title", path.parent.name))}</h1>
<p>{esc(metadata.get("description", ""))}</p>
<div class="document-control">{esc(metadata.get("id", ""))} ·
{labels[0]} {esc(metadata.get("revision", ""))} · {labels[1]} {esc(metadata.get("updated_on", ""))} ·
{labels[2]}{status_separator}{esc(status)}</div>{byline}</header>
{pictures["cover_image"]}{render_body(repo, path, body, link_for)}
{related_html}{pictures["footer_image"]}</article>'''


def export_html(repo, destination):
    """Build a static site with embedded images and relative article links."""
    import shutil

    published = {}
    for path, metadata, _, error in repo.scan():
        if error or metadata.get("status") != "published":
            continue
        if repo.article_path(path.parent.name, path.stem) != path:
            raise ValueError(f"Invalid article location: {path.name}")
        published[path.resolve()] = metadata

    def filename(path):
        return f"{path.parent.name}.{path.stem}.html"

    def link_for(path):
        resolved = path.resolve()
        return quote(filename(resolved)) if resolved in published else None

    def page(title, content, language="en"):
        return f"""<!doctype html><html lang="{esc(language)}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self' 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>{esc(title)}</title><link rel="stylesheet" href="style.css">
</head><body><main>{content}</main></body></html>"""

    if len({filename(path).casefold() for path in published}) != len(published):
        raise ValueError("Two published editions would use the same HTML filename.")
    if destination.resolve().is_relative_to(repo.root) and any(
        destination.resolve().is_relative_to(repo.path(folder).resolve())
        for folder in ("articles", "registry", "branding")
    ):
        raise ValueError(
            "Choose an output folder outside the collection's source folders."
        )
    destination.mkdir()
    try:
        (destination / "style.css").write_bytes(
            Path(__file__).with_name("style.css").read_bytes()
        )
        entries = []
        for path, metadata in published.items():
            title = metadata.get("title") or path.parent.name
            language = metadata.get("language") or path.stem
            entries.append(
                f'<li><a href="{esc(link_for(path))}">{esc(title)}</a> · {esc(language)}</li>'
            )
            content = '<p><a href="index.html">All articles</a></p>' + branded_article(
                repo, path, link_for
            )
            (destination / filename(path)).write_text(
                page(title, content, language), encoding="utf-8"
            )
        name = repo.config["branding"]["name"]
        listing = (
            "<ul>" + "".join(entries) + "</ul>"
            if entries
            else "<p>No published articles.</p>"
        )
        (destination / "index.html").write_text(
            page(name, f"<h1>{esc(name)}</h1>{listing}"), encoding="utf-8"
        )
    except (OSError, ValueError, KeyError, TypeError):
        shutil.rmtree(destination)
        raise
