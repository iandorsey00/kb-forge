"""Render portable articles with collection branding."""

import base64
import html
from hashlib import file_digest, sha256
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
from posixpath import relpath
import re
import subprocess
from urllib.parse import quote, unquote, urlencode, urlsplit

from .pdf import IMAGE_SUFFIXES, export_pdf, pdf_available, pdf_theme, theme_asset
from .fonts import font_notices, web_fonts
from .repository import (
    ASSET,
    LIST_FIELDS,
    article_author,
    image_width,
    load_article,
    pandoc,
)


def esc(value):
    return html.escape(str(value), quote=True)


def workspace_palette(workspace):
    """Use the same validated workspace colors in the app and reader site."""
    return ";".join(
        f"--workspace-{key}:{value}"
        for key in ("accent", "navigation", "background")
        if isinstance(value := workspace.get(key), str)
        and re.fullmatch(r"#[0-9a-fA-F]{6}", value)
    )


class SearchText(HTMLParser):
    """Collect the visible prose and image descriptions from a rendered article."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "img" and (alt := dict(attrs).get("alt")):
            self.parts.append(alt)


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
            # Discard author-supplied HTML attributes, including event handlers and styles.
            if (
                len(value) == 3
                and isinstance(value[0], str)
                and isinstance(value[1], list)
                and isinstance(value[2], list)
                and all(isinstance(item, str) for item in value[1])
                and all(isinstance(item, list) and len(item) == 2 for item in value[2])
            ):
                return [value[0], value[1], []]
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
            width = image_width(content[0]) if kind == "Image" else None
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
            rendered = rewrite(content)
            if width is not None:
                rendered[0][2] = [["width", f"{width}%"]]
            return {"t": kind, "c": rendered}
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


def site_editions(repo, include_pdfs, *, strict=False):
    published = {}
    assets = {}
    for path, metadata, body, error in repo.scan():
        if error and strict:
            raise ValueError(f"Cannot read {path.relative_to(repo.root)}: {error}")
        if error or metadata.get("status") != "published":
            continue
        if repo.article_path(path.parent.name, path.stem) != path:
            raise ValueError(f"Invalid article location: {path.name}")
        if path.parent not in assets:
            asset_folder = repo.path("articles", path.parent.name, "assets")
            fingerprints = []
            for asset in sorted(asset_folder.glob("*")):
                if (
                    ASSET.fullmatch(asset.name)
                    and asset.is_file()
                    and not asset.is_symlink()
                ):
                    with asset.open("rb") as stream:
                        fingerprints.append(
                            [asset.name, file_digest(stream, "sha256").hexdigest()]
                        )
            assets[path.parent] = fingerprints
        stem = f"articles/{path.parent.name}/{path.stem}"
        record = {
            "id": path.parent.name,
            "language": path.stem,
            "title": metadata.get("title") or path.parent.name,
            "revision": metadata.get("revision"),
            "html": f"{stem}.html",
            "source_sha256": sha256(
                json.dumps(
                    [metadata, body, assets[path.parent]], sort_keys=True
                ).encode("utf-8")
            ).hexdigest(),
        }
        if include_pdfs:
            record["pdf"] = f"{stem}.pdf"
        note = metadata.get("release_note")
        if isinstance(note, str) and note.strip():
            record["release_note"] = note.strip()
        published[path.resolve()] = record
    folders = {item["id"] for item in published.values()}
    if len({name.casefold() for name in folders}) != len(folders):
        raise ValueError("Published article IDs must have distinct folder names.")
    if len({item["html"].casefold() for item in published.values()}) != len(published):
        raise ValueError("Two published editions would use the same HTML path.")
    return published


def export_html(repo, destination, *, include_pdfs=True, release=None, published=None):
    """Build a portable site with relative links to articles and their PDFs."""
    import shutil

    if published is None:
        published = site_editions(repo, include_pdfs)
    brand = repo.config["branding"]
    workspace = repo.config.get("workspace", {})
    name = workspace.get("name") or brand["name"]
    accent = brand.get("color", "")
    if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = "#245450"
    logo = ""
    if logo_name := workspace.get("logo") or brand.get("logo"):
        asset = theme_asset(repo, logo_name, IMAGE_SUFFIXES)
        logo = f'<img src="{esc(image_data(asset))}" alt="">'
    site_style = f"--site-brand:{accent};{workspace_palette(workspace)}"
    home_language = repo.config["languages"][0]
    chinese = home_language.lower().startswith("zh")
    search_script = (
        Path(__file__).with_name("site_search.js").read_text(encoding="utf-8")
    )
    script_hash = base64.b64encode(
        sha256(search_script.encode("utf-8")).digest()
    ).decode("ascii")
    font_css, font_assets = web_fonts(repo, lambda name: f"fonts/{name}")
    for notice in font_notices(repo.config.get("publishing", {})):
        font_assets[notice] = theme_asset(repo, notice, {".txt"}).read_bytes()

    def link_for(path, start="."):
        resolved = path.resolve()
        return (
            quote(relpath(published[resolved]["html"], start))
            if resolved in published
            else None
        )

    def page(title, content, language, stylesheet="style.css", homepage=False):
        script_policy = f"; script-src 'sha256-{script_hash}'" if homepage else ""
        script = f"<script>{search_script}</script>" if homepage else ""
        layout = "reader-home" if homepage else "reader-article"
        fonts_link = (
            f'<link rel="stylesheet" href="{esc(stylesheet.removesuffix("style.css") + "fonts.css")}">'
            if font_css and not homepage
            else ""
        )
        return f"""<!doctype html><html lang="{esc(language)}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self' 'unsafe-inline'; img-src data:; font-src 'self'; base-uri 'none'; form-action 'none'{script_policy}">
<title>{esc(title)}</title><link rel="stylesheet" href="{esc(stylesheet)}">{fonts_link}
</head><body class="reader-site" style="{esc(site_style)}"><main class="{layout}">{content}</main>{script}</body></html>"""

    if published and include_pdfs and not pdf_available():
        raise ValueError(
            "Install PDF support with python -m pip install -r requirements-pdf.txt "
            "or use --html-only."
        )
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
        assets = []
        if font_css:
            (destination / "fonts.css").write_text(font_css, encoding="utf-8")
            assets.append("fonts.css")
        if font_assets:
            (destination / "fonts").mkdir()
            for asset, data in font_assets.items():
                (destination / "fonts" / asset).write_bytes(data)
                assets.append(f"fonts/{asset}")
        entries = []
        index_links = {}
        for path, edition in published.items():
            title = edition["title"]
            language = edition["language"]
            output = destination / edition["html"]
            output.parent.mkdir(parents=True, exist_ok=True)
            article_folder = output.parent.relative_to(destination).as_posix()
            index_download = article_download = ""
            if include_pdfs:
                pdf_path = output.with_suffix(".pdf")
                try:
                    pdf_path.write_bytes(export_pdf(repo, path))
                except (OSError, ValueError, KeyError, TypeError) as error:
                    raise ValueError(
                        f"Could not export PDF for {path.parent.name} ({path.stem}): {error}"
                    ) from error
                label = (
                    "下载 PDF" if path.stem.lower().startswith("zh") else "Download PDF"
                )
                index_pdf = quote(pdf_path.relative_to(destination).as_posix())
                index_download = f'<a class="reader-pdf" href="{esc(index_pdf)}" download>{label}</a>'
                article_download = f'<a class="reader-pdf" href="{esc(quote(pdf_path.name))}" download>{label}</a>'
            article_html = branded_article(
                repo, path, lambda other: link_for(other, article_folder)
            )
            visible = SearchText()
            visible.feed(article_html)
            metadata, _ = load_article(path)
            search_text = " ".join(
                [*visible.parts, edition["id"], language]
                + [str(metadata.get(key, "")) for key in LIST_FIELDS]
            )
            description = metadata.get("description")
            summary = f"<p>{esc(description)}</p>" if description else ""
            link = f'<a href="{esc(link_for(path))}">{esc(title)}</a>'
            index_links[edition["html"]] = link
            entries.append(
                f'<li data-search="{esc(search_text)}"><div><h3>{link}</h3>'
                f'<span class="reader-meta">{esc(edition["id"])} · {esc(language)}</span>'
                f"{summary}</div>{index_download}</li>"
            )
            back = "所有文章" if language.lower().startswith("zh") else "All articles"
            content = (
                f'<nav class="actions" aria-label="{esc(back)}">'
                f'<a class="reader-site-home" href="../../index.html" aria-label="{esc(back + " · " + str(name))}">'
                f"{logo}<span>{esc(name)}</span></a>{article_download}</nav>{article_html}"
            )
            output.write_text(
                page(title, content, language, "../../style.css"), encoding="utf-8"
            )
        no_articles = "暂无已发布的文章。" if chinese else "No published articles."
        listing = (
            '<ul class="reader-list">' + "".join(entries) + "</ul>"
            if entries
            else f"<p>{no_articles}</p>"
        )
        bulletin = []
        for change in (release or {}).get("recent_changes", []):
            day = esc(change["date"])
            labels = ("新增", "更新") if chinese else ("New", "Updated")
            label = labels[0] if change["kind"] == "new" else labels[1]
            link = index_links[change["html"]]
            note = f"<p>{esc(change['note'])}</p>" if change.get("note") else ""
            bulletin.append(
                f'<li><span class="reader-meta"><time datetime="{day}">{day}</time> · {label}</span>{link}{note}</li>'
            )
        updates = "最新动态" if chinese else "What’s new"
        whats_new = (
            f'<aside class="reader-updates"><h2>{updates}</h2><ul>'
            + "".join(bulletin)
            + "</ul></aside>"
            if bulletin
            else ""
        )
        search_label, placeholder, result_count, empty, heading = (
            (
                "搜索文章",
                "按标题、编号或正文搜索",
                "找到 {count} 个结果",
                "没有匹配的文章。",
                "文章",
            )
            if chinese
            else (
                "Search articles",
                "Search by title, ID, or text",
                "Matching articles ({count})",
                "No matching articles.",
                "Articles",
            )
        )
        search = f'''<form id="reader-search" class="reader-search" role="search" hidden>
<label for="reader-query">{search_label}</label>
<input id="reader-query" type="search" placeholder="{placeholder}">
<p role="status" data-count="{result_count}" data-empty="{empty}"></p></form>'''
        content = (
            f'<header class="reader-hero">{logo}<h1>{esc(name)}</h1>{search if entries else ""}</header>'
            f'<div class="reader-layout"><section><h2>{heading}</h2>{listing}</section>{whats_new}</div>'
        )
        (destination / "index.html").write_text(
            page(name, content, home_language, homepage=bool(entries)), encoding="utf-8"
        )
        manifest = {
            "version": 1,
            "editions": list(published.values()),
            **(release or {}),
        }
        if assets:
            manifest["font_assets"] = assets
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        shutil.rmtree(destination)
        raise
