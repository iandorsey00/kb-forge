"""Render portable articles with collection branding."""

import base64
import html
import json
import mimetypes
from pathlib import Path
import subprocess
from urllib.parse import quote, unquote, urlencode, urlsplit

from .pdf import pdf_theme
from .repository import ASSET, load_article, pandoc


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


def render_body(repo, path, body):
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
                    content[-1][0] = article_url(candidate) + fragment
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


def branded_article(repo, path):
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
                related.append(
                    f'<a href="{esc(article_url(other))}">{esc(other_metadata.get("title", target))}</a>'
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
{labels[2]}{status_separator}{esc(status)}</div></header>
{pictures["cover_image"]}{render_body(repo, path, body)}
{related_html}{pictures["footer_image"]}</article>'''
