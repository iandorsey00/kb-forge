"""A loopback-only graphical workspace for one portable collection."""

import argparse
import base64
import hashlib
import json
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets
import shutil
import sys
from urllib.parse import parse_qs, quote, urlsplit

from .backup import backup_collections, backup_schedule, run_scheduled_backup
from .package import import_package
from .theme import export_theme, import_theme
from .pdf import IMAGE_SUFFIXES, export_pdf, pdf_available, pdf_filename, theme_asset
from .publishing import (
    export_html,
    export_pdfs,
    article_url,
    branded_article,
    esc,
    image_data,
    render_body,
    workspace_palette,
)
from .site_release import change_lines, copy_site, publish_site, rollback_site
from .collaboration import clone_site, push_site
from .fonts import web_fonts
from .repository import (
    ASSET,
    LIST_FIELDS,
    STATUSES,
    Repository,
    custom_value_matches,
    initialize_collection,
    image_width,
    load_article,
    save_article,
)

from .update import RELEASES_URL, update_available, update_checkout
from .renumber import renumber
from .migrate import MIGRATIONS, migrate_articles

STYLE = Path(__file__).with_name("style.css")
PLAIN_TEXT = "text/plain; charset=utf-8"
FIELDS = {
    "title": "Title",
    "description": "Description",
    "owner": "Owner",
    "products": "Products",
    "categories": "Categories",
    "regions": "Regions",
    "countries": "Countries",
    "tags": "Keywords and tags",
    "review_on": "Review date",
}


def select(name, label, values, selected="", empty="", *, form_id=""):
    options = f'<option value="">{esc(empty)}</option>' if empty else ""
    for value, title in values:
        active = " selected" if value == selected else ""
        options += f'<option value="{esc(value)}"{active}>{esc(title)}</option>'
    form = f' form="{form_id}"' if form_id else ""
    return f'<label>{esc(label)}<select name="{name}"{form}>{options}</select></label>'


def field(name, label, value="", kind="text", required=False, *, form_id=""):
    form = f' form="{form_id}"' if form_id else ""
    return (
        f'<label>{esc(label)}<input name="{name}" type="{kind}" value="{esc(value)}"{form}'
        + (" required" if required else "")
        + "></label>"
    )


def table(headers, rows):
    if not rows:
        return '<p class="muted">No results.</p>'
    head = "".join(f"<th>{esc(label)}</th>" for label in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def catalog_rows(repo):
    return [(path, meta) for path, meta, _, error in repo.scan() if not error]


class Handler(BaseHTTPRequestHandler):
    def __init__(self, repo, token, *args):
        self.repo = repo
        self.token = token
        super().__init__(*args)

    def send_content(self, body, status=200, content_type="text/html; charset=utf-8", *, disposition=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'self' 'unsafe-inline'; img-src data:; font-src 'self'; "
            "script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def page(self, title, body, status=200, *, publication=False, editor=False):
        brand = self.repo.config.get("workspace", {})
        name = esc(brand.get("name", "KB Forge"))
        css = workspace_palette(brand)
        logo = ""
        if brand.get("logo"):
            try:
                src = image_data(theme_asset(self.repo, brand["logo"], IMAGE_SUFFIXES))
                logo = f'<img class="workspace-logo" src="{esc(src)}" alt="">'
            except (ValueError, OSError):
                pass
        fonts = '<link rel="stylesheet" href="/fonts.css">' if publication or editor else ""
        update_label = self.update_label()
        available = ' class="update-available"' if update_label == "Update app…" else ""
        layout = ' class="editor-page"' if editor else ""
        self.send_content(
            f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | {name}</title><link rel="stylesheet" href="/style.css">{fonts}
<body style="{esc(css)}">
<nav class="site" aria-label="Workspace"><strong><a href="/">{logo}{name}</a></strong>
<a href="/catalog">Catalog</a><a href="/create">New article</a><a href="/validate">Validation</a>
<a href="/updates" id="updates-link" aria-live="polite"{available}>{update_label}</a>
<form class="workspace-search" action="/catalog" role="search">
<input type="search" name="q" aria-label="Search articles" placeholder="Search articles">
<button>Search</button></form></nav>
<main{layout}>{body}</main><script src="/app.js" defer></script></body></html>""",
            status,
        )

    def form_token(self):
        return f'<input type="hidden" name="_token" value="{self.token}">'

    def dispatch(self, method):
        # Check the Host header as well as binding to loopback to reject DNS rebinding.
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(400, "Use the local address printed at startup.")
            return
        target = urlsplit(self.path)
        values = {}
        try:
            params = parse_qs(target.query, max_num_fields=60)
            if method == "POST":
                # Keep form mutations tied to this server process and bound upload size.
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 12 * 1024 * 1024:
                    raise ValueError("The form is empty or exceeds the upload limit.")
                if (
                    self.headers.get_content_type()
                    != "application/x-www-form-urlencoded"
                ):
                    raise ValueError("Unsupported form format.")
                form = parse_qs(
                    self.rfile.read(size).decode("utf-8"),
                    keep_blank_values=True,
                    max_num_fields=60 + (
                        len(self.repo.custom_fields)
                        if target.path in ("/create", "/edit")
                        else 0
                    ),
                )
                params.update(form)
                if not secrets.compare_digest(
                    params.get("_token", [""])[0].encode(), self.token.encode()
                ):
                    if self.headers.get("Accept") == "text/plain":
                        self.send_content("Reload the editor and try again.", 403, PLAIN_TEXT)
                        return
                    self.page(
                        "Forbidden",
                        "<h1>Forbidden</h1><p>Reload the form and try again.</p>",
                        403,
                    )
                    return
            if getattr(self.server, "restart_required", False) and target.path not in (
                "/updates",
                "/style.css",
                "/app.js",
                "/update-status",
            ):
                self.page(
                    "Restart required",
                    "<h1>Restart required</h1><p>Restart KB Forge to load the installed update.</p>",
                    503,
                )
                return
            values = {key: items[0] for key, items in params.items()}
            route = {
                ("GET", "/"): self.dashboard,
                ("GET", "/catalog"): self.catalog,
                ("GET", "/create"): self.create_form,
                ("POST", "/create"): self.create,
                ("GET", "/validate"): self.validation,
                ("GET", "/updates"): self.updates,
                ("GET", "/update-status"): lambda _: self.send_content(
                    self.update_label(), content_type="text/plain; charset=utf-8"
                ),
                ("POST", "/updates"): self.apply_update,
                ("GET", "/article"): self.article,
                ("GET", "/edit"): self.edit_form,
                ("POST", "/edit"): self.edit,
                ("POST", "/preview"): self.preview,
                ("POST", "/image"): self.upload,
                ("GET", "/publish"): self.publish,
                ("GET", "/pdf"): self.pdf,
                ("GET", "/fonts.css"): self.font_css,
                ("GET", "/font"): self.font_file,
                ("GET", "/style.css"): lambda _: self.send_content(
                    STYLE.read_bytes(), content_type="text/css"
                ),
                ("GET", "/app.js"): lambda _: self.send_content(
                    STYLE.with_name("app.js").read_bytes(),
                    content_type="text/javascript",
                ),
            }.get((method, target.path))
            if route is None:
                self.page("Page unavailable", "<h1>Page unavailable</h1>", 404)
            else:
                route(values)
        except FileExistsError:
            self.page(
                "Edition exists",
                "<h1>Edition already exists</h1><p>Open it from the catalog to edit it.</p>",
                409,
            )
        except (ValueError, OSError, KeyError, TypeError) as error:
            if method == "POST" and self.headers.get("Accept") == "text/plain":
                self.send_content(str(error), 400, PLAIN_TEXT)
                return
            back = ""
            if target.path in ("/article", "/edit", "/publish", "/pdf") and values:
                try:
                    edit_url = esc(article_url(self.path_from(values), "edit"))
                    back = f'<p><a href="{edit_url}">Return to the editor</a></p>'
                except ValueError:
                    pass
            self.page(
                "Request could not be completed",
                f"<h1>Request could not be completed</h1><p>{esc(error)}</p>{back}",
                400,
            )

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def updates(self, _):
        if getattr(self.server, "restart_required", False):
            self.page(
                "Restart required",
                "<h1>Restart required</h1><p>Stop KB Forge with Ctrl+C and run your launch command again.</p>",
            )
            return
        notice = (
            "<p>An update is available.</p>"
            if self.update_label() == "Update app…"
            else ""
        )
        self.page(
            "Updates",
            f"<h1>Update KB Forge</h1>{notice}"
            "<p>Fetch and install the latest commit from this checkout’s configured upstream branch. "
            "Save any open article edits before updating.</p>"
            f'<p>Using a ZIP download? Get the <a href="{RELEASES_URL}">new release</a> '
            "in a separate folder and open your existing collection by path.</p>"
            f'<form method="post" action="/updates">{self.form_token()}'
            '<button type="submit">Check and install update</button></form>',
        )

    def update_label(self):
        if getattr(self.server, "restart_required", False):
            return "Restart app"
        if getattr(self.server, "update_available", False):
            return "Update app…"
        return "Updates"

    def apply_update(self, _):
        with self.server.update_lock, self.server.write_lock:
            if getattr(self.server, "restart_required", False):
                self.page(
                    "Restart required",
                    "<h1>Restart required</h1><p>Restart KB Forge to load the installed update.</p>",
                )
                return
            result = update_checkout()
            self.server.update_available = False
            if result:
                self.server.restart_required = True
        if result:
            before, after = result
            self.page(
                "Update installed",
                f"<h1>Update installed</h1><p>Updated from {esc(before)} to {esc(after)}.</p>"
                "<p>Stop KB Forge with Ctrl+C and run your launch command again to load the update.</p>",
            )
        else:
            self.page(
                "Up to date",
                "<h1>Up to date</h1><p>This checkout matches its upstream branch.</p>",
            )

    def dashboard(self, _):
        rows = catalog_rows(self.repo)
        findings = self.repo.validate()
        stats = (
            (len({path.parent.name for path, _ in rows}), "Articles"),
            (len(rows), "Language editions"),
            (sum(level == "Error" for level, _, _ in findings), "Validation errors"),
            (
                sum(text.startswith("Review is overdue") for _, _, text in findings),
                "Overdue reviews",
            ),
        )
        cards = "".join(
            f'<div class="card"><strong>{value}</strong>{label}</div>'
            for value, label in stats
        )
        coverage = ", ".join(
            f"{language} ({sum(meta.get('language') == language for _, meta in rows)})"
            for language in self.repo.config["languages"]
        )
        self.page(
            "Workspace",
            f"""<h1>Documentation workspace</h1>
<p class="muted">{esc(self.repo.config["branding"]["name"])} · {esc(self.repo.root)}</p>
<div class="grid">{cards}</div><p>Language coverage · {esc(coverage)}</p>
<div class="actions"><a class="button" href="/create">New article</a>
<a class="button secondary" href="/catalog">Browse articles</a></div>""",
        )

    def catalog(self, values):
        rows = []
        group = values.get("group", "")
        group_fields = {
            "type": "Type",
            "language": "Language",
            "owner": "Owner",
            "status": "Status",
            "products": "Products",
            "categories": "Categories",
            "regions": "Regions",
            "countries": "Countries",
            "review_on": "Review date",
        }
        query = values.get("q", "").casefold().split()
        for path, meta, body, error in self.repo.scan():
            if error:
                continue
            searchable = " ".join(
                str(meta.get(key, ""))
                for key in (
                    "id",
                    "title",
                    "description",
                    "type",
                    "language",
                    "owner",
                    "author",
                    "status",
                    "review_on",
                    *LIST_FIELDS,
                )
            )
            searchable = f"{searchable} {path.parent.name} {body}".casefold()
            if not all(term in searchable for term in query):
                continue
            if any(
                values.get(key) and values[key] != meta.get(key)
                for key in ("language", "status")
            ):
                continue
            group_value = meta.get(group, "") if group in group_fields else ""
            if isinstance(group_value, list):
                group_value = ", ".join(map(str, group_value))
            rows.append((str(group_value), path, meta))
        sort_options = {
            "title": "Title (A–Z)",
            "number": "Article number (ascending)",
            "number-desc": "Article number (descending)",
            "updated": "Recently updated",
            "review": "Next review date",
        }
        sort = values.get("sort", "title")
        if sort not in sort_options:
            sort = "title"

        def sort_key(row):
            _, path, meta = row
            if sort.startswith("number"):
                parts = re.split(r"([0-9]+)", path.parent.name.casefold())
                return tuple(int(part) if index % 2 else part for index, part in enumerate(parts))
            if sort == "review":
                return str(meta.get("review_on") or "9999-12-31")
            if sort == "updated":
                return str(meta.get("updated_on") or "")
            return str(meta.get("title", "")).casefold()

        rows.sort(key=lambda row: row[1])
        rows.sort(key=sort_key, reverse=sort in ("number-desc", "updated"))
        rows.sort(key=lambda row: row[0].casefold())
        headers = ["Article", "Language", "Type", "Owner", "Status", "Review date", "Updated"]
        rendered_rows = [
            [
                f'<a href="{esc(article_url(path))}">{esc(meta.get("title", path.stem))}</a><br><small>{esc(path.parent.name)}</small>',
                *[
                    esc(meta.get(key, ""))
                    for key in ("language", "type", "owner", "status", "review_on", "updated_on")
                ],
            ]
            for _, path, meta in rows
        ]
        if group in group_fields:
            headers.insert(0, group_fields[group])
            for row, (key, _, _) in zip(rendered_rows, rows):
                row.insert(0, esc(key))
        filters = (
            field(
                "q", "Search articles and metadata", values.get("q", ""), kind="search"
            )
            + select(
                "language",
                "Language",
                [(lang, lang) for lang in self.repo.config["languages"]],
                values.get("language"),
                "All languages",
            )
            + select(
                "status",
                "Status",
                [(status, status.title()) for status in STATUSES],
                values.get("status"),
                "All statuses",
            )
            + select("group", "Group by", group_fields.items(), group, "None")
            + select("sort", "Sort by", sort_options.items(), sort)
        )
        self.page(
            "Article catalog",
            f"""<h1>Article catalog</h1><form><div class="grid">{filters}</div>
<button>Search</button></form>{table(headers, rendered_rows)}""",
        )

    def standard_metadata_fields(self, metadata, names, *, form_id=""):
        fields = []
        for name in names:
            label = FIELDS[name]
            value = metadata.get(name, "")
            if name in LIST_FIELDS:
                label += " (comma separated)"
                if isinstance(value, list):
                    value = ", ".join(map(str, value))
            fields.append(
                field(
                    name,
                    label,
                    value,
                    "date" if name == "review_on" else "text",
                    name in ("title", "owner"),
                    form_id=form_id,
                )
            )
        return "".join(fields)

    def related_field(self, metadata, *, form_id=""):
        return field(
            "related",
            "Related article IDs (comma separated)",
            ", ".join(map(str, metadata.get("related", []))),
            form_id=form_id,
        )

    def custom_metadata_fields(self, metadata, *, creating=False, form_id=""):
        fields = []
        for name, definition in self.repo.custom_fields.items():
            label = definition.get("label", name)
            value = (
                definition.get("default", "") if creating else metadata.get(name, "")
            )
            form_name = f"custom.{name}"
            if definition["type"] == "boolean":
                options = [("true", "True"), ("false", "False")]
                if type(value) is bool:
                    selected = "true" if value else "false"
                elif not creating and name in metadata:
                    selected = "invalid"
                    options.append(("invalid", f"Invalid value ({value})"))
                else:
                    selected = ""
                fields.append(
                    select(form_name, label, options, selected, "Not set", form_id=form_id)
                )
            else:
                fields.append(field(form_name, label, value, form_id=form_id))
        return "".join(fields)

    def submitted_custom_metadata(self, values):
        metadata = {}
        for name, definition in self.repo.custom_fields.items():
            form_name = f"custom.{name}"
            if form_name not in values:
                continue
            value = values[form_name].strip()
            kind = definition["type"]
            if not value:
                metadata[name] = None
            elif kind == "boolean" and value in ("true", "false"):
                metadata[name] = value == "true"
            elif kind == "integer":
                try:
                    if not re.fullmatch(r"[+-]?[0-9]+", value):
                        raise ValueError
                    metadata[name] = int(value, 10)
                except ValueError:
                    raise ValueError(f"{name}: enter a whole number.") from None
            elif kind == "string":
                original = values[form_name]
                if not custom_value_matches(kind, original):
                    raise ValueError(f"{name}: enter a single line of text.")
                metadata[name] = original
            else:
                raise ValueError(f"{name}: select True, False, or Not set.")
        return metadata

    def submitted_metadata(self, values):
        metadata = {key: values.get(key, "").strip() for key in FIELDS}
        for key in (*LIST_FIELDS, "related"):
            metadata[key] = list(
                dict.fromkeys(
                    item.strip()
                    for item in values.get(key, "").split(",")
                    if item.strip()
                )
            )
        if not metadata["title"] or not metadata["owner"]:
            raise ValueError("Title and owner are required.")
        if (
            metadata["review_on"]
            and date.fromisoformat(metadata["review_on"]).isoformat()
            != metadata["review_on"]
        ):
            raise ValueError("Use YYYY-MM-DD for the review date.")
        return metadata

    def create_form(self, _):
        languages = select(
            "language",
            "Language",
            [(lang, lang) for lang in self.repo.config["languages"]],
        )
        types = select(
            "type",
            "Template",
            [
                (key, template.get("label", key))
                for key, template in self.repo.templates.items()
            ],
        )
        sources = [
            (
                f"{path.parent.name}/{path.stem}",
                f"{meta.get('title', path.stem)} ({path.parent.name}, {path.stem})",
            )
            for path, meta in catalog_rows(self.repo)
            if "translation_of" not in meta
        ]
        translation = select(
            "translation", "Source edition", sources, empty="New article"
        )
        details = self.standard_metadata_fields({}, ("title", "owner"))
        optional = self.standard_metadata_fields(
            {}, ("description", "review_on", *LIST_FIELDS)
        ) + self.related_field({})
        custom = self.custom_metadata_fields({}, creating=True)
        custom_section = (
            f'<details class="create-section"><summary>Custom metadata</summary>'
            f'<div class="create-fields">{custom}</div></details>'
            if custom else ""
        )
        self.page(
            "New article",
            f"""<div class="create-page">
<nav class="editor-breadcrumb" aria-label="Breadcrumb"><a href="/catalog">Catalog</a>
<span aria-hidden="true">/</span> New article</nav>
<header class="create-heading"><h1>New article</h1>
<p class="muted">Set up a draft, then write the article in the editor.</p></header>
<form class="create-card" method="post" action="/create">
{self.form_token()}
<section class="create-section" aria-labelledby="create-details">
<h2 id="create-details">Article details</h2>
<p class="muted">Title and owner are required.</p>
<div class="create-fields create-basics">{details}</div></section>
<section class="create-section" aria-labelledby="create-edition">
<h2 id="create-edition">Edition</h2>
<div class="create-fields">{languages}{types}
<div class="create-source">{translation}<p class="muted">Choose a source edition only when creating a translation.</p></div>
</div></section>
<details class="create-section"><summary>Additional details</summary>
<div class="create-fields">{optional}</div></details>
{custom_section}
<footer class="create-actions"><a class="button secondary" href="/catalog">Cancel</a>
<button type="submit">Create draft</button></footer></form></div>""",
        )

    def create(self, values):
        metadata = self.submitted_metadata(values)
        metadata.update(self.submitted_custom_metadata(values))
        metadata.update(
            language=values.get("language", ""), type=values.get("type", "")
        )
        path = self.repo.create(metadata, values.get("translation", ""))
        self.redirect(article_url(path, "edit"))

    def path_from(self, values):
        return self.repo.article_path(values.get("id", ""), values.get("language", ""))

    def font_css(self, _):
        css, _ = web_fonts(self.repo, lambda name: f"/font?name={name}")
        self.send_content(css, content_type="text/css; charset=utf-8")

    def font_file(self, values):
        _, assets = web_fonts(self.repo, lambda name: name)
        data = assets.get(values.get("name", ""))
        if data is None:
            self.send_error(404)
        else:
            self.send_content(data, content_type="font/ttf")

    def article(self, values):
        path = self.path_from(values)
        editions = [
            f'<a class="button secondary" href="{esc(article_url(other))}">{esc(other.stem)}</a>'
            for other in sorted(path.parent.glob("*.md"))
            if other != path
        ]
        self.page(
            "Article",
            f'''<div class="actions">
<a class="button secondary" href="{esc(article_url(path, "edit"))}">Edit</a>
<a class="button" href="{esc(article_url(path, "publish"))}">Publish</a>{"".join(editions)}</div>
{branded_article(self.repo, path)}''',
            publication=True,
        )

    def edit_form(self, values):
        path = self.path_from(values)
        fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
        metadata, body = load_article(path)
        form_id = "article-editor"
        status = select(
            "status",
            "Status",
            [(item, item.title()) for item in STATUSES],
            metadata.get("status"),
            form_id=form_id,
        )
        types = select(
            "type",
            "Document type",
            [
                (key, value.get("label", key))
                for key, value in self.repo.templates.items()
            ],
            metadata.get("type"),
            form_id=form_id,
        )
        translation = ""
        if metadata.get("translation_of"):
            translation = field(
                "source_revision",
                "Source revision used",
                metadata.get("source_revision", ""),
                "number",
                True,
                form_id=form_id,
            )
        assets = "".join(
            f'<li data-asset="{esc(file.name)}"><code>{esc(file.name)}</code></li>'
            for file in sorted(self.repo.path("articles", path.parent.name, "assets").glob("*"))
            if ASSET.fullmatch(file.name) and file.is_file() and not file.is_symlink()
        )
        basics = self.standard_metadata_fields(
            metadata, ("title", "description", "owner", "review_on"), form_id=form_id
        )
        classification = self.standard_metadata_fields(metadata, LIST_FIELDS, form_id=form_id)
        custom = self.custom_metadata_fields(metadata, form_id=form_id)
        custom_section = (
            f'<details class="editor-card"><summary>Custom metadata</summary>'
            f'<div class="editor-fields">{custom}</div></details>'
            if custom
            else ""
        )
        self.page(
            "Edit article",
            f'''<div class="editor-breadcrumb"><a href="/catalog">Catalog</a><span aria-hidden="true">/</span> Edit article</div>
<header class="editor-heading">
<div><h1>{esc(metadata.get("title") or path.parent.name)}</h1>
<p><span class="editor-id">{esc(path.parent.name)}</span><span>{esc(path.stem)}</span>
<span>Revision {esc(metadata.get("revision", ""))}</span></p></div>
<div class="editor-actions">
<span id="editor-save-state" role="status"></span>
<a class="button secondary" href="{esc(article_url(path))}" target="_blank" rel="noopener">View article<span class="visually-hidden"> (opens in a new tab)</span></a>
<button id="editor-save" type="submit" form="{form_id}">Save changes</button>
</div></header>
<p id="editor-save-error" role="alert" hidden></p>
<div class="editor-layout">
<form id="{form_id}" method="post" action="{esc(article_url(path, "edit"))}"
data-preview="{esc(article_url(path, "preview"))}">
{self.form_token()}<input type="hidden" name="fingerprint" value="{fingerprint}">
<section class="editor-card editor-composer" aria-labelledby="editor-content-title">
<div class="editor-card-header">
<h2 id="editor-content-title">Content</h2>
<div class="editor-modes" id="editor-modes" role="group" aria-label="Editor view" hidden>
<button type="button" data-mode="write" aria-pressed="true">Write</button>
<button type="button" data-mode="split" aria-pressed="false">Split</button>
<button type="button" data-mode="preview" aria-pressed="false">Preview</button>
</div></div>
<div class="editor-tools">
<div id="markdown-tools" role="group" aria-label="Markdown formatting" hidden>
<button type="button" data-format="heading">Heading</button>
<button type="button" data-format="bold"><strong>Bold</strong></button>
<button type="button" data-format="italic"><em>Italic</em></button>
<button type="button" data-format="list">List</button>
<button type="button" data-format="link">Link</button>
</div>
<a href="#image-drawer" id="open-image-drawer">Images</a>
</div>
<div class="editor-panes" data-mode="write">
<div class="editor-source">
<label for="article-markdown">Markdown</label>
<textarea id="article-markdown" name="body" spellcheck="true">{esc(body.strip())}</textarea>
</div>
<section class="editor-preview" aria-labelledby="editor-preview-title" hidden>
<h3 id="editor-preview-title">Preview</h3>
<div id="editor-preview-status" role="status"></div>
<div id="editor-preview-content" class="publication" lang="{esc(path.stem)}"></div>
</section></div>
<footer class="editor-status" id="editor-line-count" hidden></footer>
</section></form>
<aside class="editor-sidebar" aria-label="Article settings and images">
<details class="editor-card editor-details" open><summary>Article details</summary>
<div class="editor-fields">{basics}{types}{status}{translation}</div></details>
<details class="editor-card"><summary>Classification</summary>
<div class="editor-fields">{classification}{self.related_field(metadata, form_id=form_id)}</div></details>
{custom_section}
<details class="editor-card" id="image-drawer"><summary>Images</summary>
<form class="editor-images" id="image-upload" method="post" action="{esc(article_url(path, "image"))}">
{self.form_token()}
<label class="editor-image-picker">Choose images
<input id="image-file" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple></label>
<p class="editor-help">You can also drop files here or paste an image into the Markdown editor.</p>
<div id="image-queue"></div>
<div class="grid">
<label>Image width<input name="width" pattern="(?:[1-9][0-9]{{0,3}}|10000)(?:px)?|(?:[1-9][0-9]?|100)%" title="Use 1% to 100% or 1px to 10000px." placeholder="200px or 60%"></label>
<label>Indentation for list images (spaces)<input name="indent" type="number" min="0" max="24" placeholder="Automatic"></label>
</div>
<button type="submit" class="button secondary">Insert images</button>
<p id="upload-error" role="status"></p>
<noscript><p>Enable JavaScript to attach images through this form.</p></noscript>
<div class="editor-assets"><h3>Attached files</h3>
<p id="image-empty" class="editor-help"{' hidden' if assets else ''}>No images attached yet.</p>
<ul id="image-library">{assets}</ul></div></form></details>
</aside></div>''',
            editor=True,
        )

    def preview(self, values):
        path = self.path_from(values)
        if not path.is_file():
            raise ValueError("Open an existing article to preview its Markdown.")
        self.send_content(render_body(self.repo, path, values.get("body", "")))

    def edit(self, values):
        """Reject stale editor tabs so a save cannot silently overwrite a newer edit."""
        path = self.path_from(values)
        with self.server.write_lock:
            if hashlib.sha256(path.read_bytes()).hexdigest() != values.get(
                "fingerprint"
            ):
                raise ValueError(
                    "The file changed since you opened it. Copy your draft, then reload the editor."
                )
            metadata, body = load_article(path)
            updates = self.submitted_metadata(values)
            if (
                values.get("status") not in STATUSES
                or values.get("type") not in self.repo.templates
            ):
                raise ValueError("Select a valid status and document type.")
            updates.update(status=values["status"], type=values["type"])
            if metadata.get("translation_of"):
                revision = int(values.get("source_revision", ""))
                source, _ = load_article(
                    self.repo.article_path(path.parent.name, metadata["translation_of"])
                )
                if not 1 <= revision <= source["revision"]:
                    raise ValueError(
                        "Choose a source revision from 1 through the current source revision."
                    )
                updates["source_revision"] = revision
            new_body = values.get("body", "")
            changed = body.strip() != new_body.strip() or any(
                metadata.get(key) != value for key, value in updates.items()
            )
            for name, value in self.submitted_custom_metadata(values).items():
                if value is None:
                    if name in metadata:
                        changed = True
                        del metadata[name]
                elif (
                    metadata.get(name) != value
                    or type(metadata.get(name)) is not type(value)
                ):
                    changed = True
                    metadata[name] = value
            if changed:
                updates["revision"] = metadata["revision"] + 1
                updates["updated_on"] = date.today().isoformat()
                save_article(path, {**metadata, **updates}, new_body)
        location = article_url(path)
        if self.headers.get("Accept") == "text/plain":
            self.send_content(location, content_type=PLAIN_TEXT)
        else:
            self.redirect(location)

    def upload(self, values):
        """Store an image and return its reference or append it in legacy mode."""
        path = self.path_from(values)
        alt = " ".join(values.get("alt", "").split())
        if not alt:
            raise ValueError("Describe the image for readers.")
        alt = alt.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        width = values.get("width", "").strip()
        attributes = ""
        if width:
            # Older clients send a bare number for percentages.
            if re.fullmatch(r"[0-9]+", width):
                width += "%"
            attributes = f'{{width={image_width(["", [], [["width", width]]])}}}'
        with self.server.write_lock:
            metadata, body = load_article(path)
            encoded = values.get("image", "")
            padding = "=" * (-len(encoded) % 4)
            image = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
            relative = self.repo.store_image(
                path.parent.name, values.get("filename", ""), image
            )
            markdown = f"![{alt}]({relative}){attributes}"
            if values.get("insert") == "draft":
                self.send_content(
                    json.dumps({"markdown": markdown, "name": Path(relative).name}),
                    content_type="application/json",
                )
                return
            try:
                metadata.update(
                    revision=metadata["revision"] + 1,
                    updated_on=date.today().isoformat(),
                )
                save_article(path, metadata, body.rstrip() + f"\n\n{markdown}")
            except (OSError, KeyError, TypeError):
                (path.parent / relative).unlink(missing_ok=True)
                raise
        self.redirect(article_url(path, "edit"))

    def validation(self, _):
        rows = [[esc(value) for value in finding] for finding in self.repo.validate()]
        content = (
            table(["Severity", "File", "Suggested correction"], rows)
            if rows
            else "<p>No findings.</p>"
        )
        self.page("Validation", f"<h1>Validation</h1>{content}")

    def pdf(self, values):
        path = self.path_from(values)
        article = load_article(path)
        filename = pdf_filename(path.parent.name, article[0].get("title"))
        mode = "attachment" if values.get("download") == "1" else "inline"
        self.send_content(
            export_pdf(self.repo, path, article=article),
            content_type="application/pdf",
            disposition=f"{mode}; filename=\"{path.parent.name}.pdf\"; filename*=UTF-8''{quote(filename, safe='')}",
        )

    def publish(self, values):
        path = self.path_from(values)
        url = esc(article_url(path, "pdf"))
        pdf_link = (
            f'<a class="button" href="{url}" target="_blank" rel="noopener">Open branded PDF <span aria-hidden="true">↗</span><span class="visually-hidden"> (opens in a new tab)</span></a>'
            f'<a class="button secondary" href="{url}&amp;download=1">Download PDF</a>'
            if pdf_available()
            else ""
        )
        dependency_help = (
            "" if pdf_link else
            '<p class="muted">Install PDF support with <code>python -m pip install -r requirements-pdf.txt</code>, then restart KB Forge.</p>'
        )
        self.page(
            "Publish article",
            f'''<div class="actions">
<a class="button secondary" href="{esc(article_url(path))}">Back to article</a>
{pdf_link}</div>
{dependency_help}
{branded_article(self.repo, path)}''',
            publication=True,
        )


def main():
    import threading

    parser = argparse.ArgumentParser(description="Open a portable KB Forge collection.")
    parser.add_argument(
        "collection", nargs="?", type=Path, help="Path to the collection directory"
    )
    parser.add_argument("--port", type=int, default=8765)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--validate", action="store_true", help="Validate the collection and exit"
    )
    actions.add_argument("--export-pdf", nargs=2, metavar=("ID", "LANGUAGE"))
    actions.add_argument(
        "--export-pdfs",
        action="store_true",
        help="Export every published edition as a branded PDF in one folder",
    )
    actions.add_argument(
        "--init", action="store_true", help="Create a blank collection"
    )
    actions.add_argument(
        "--export-site",
        action="store_true",
        help="Export published articles as a static site with branded PDFs",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Omit PDFs when exporting or publishing a site",
    )
    actions.add_argument(
        "--publish-site",
        metavar="NAME",
        help="Preview publishing to a named destination",
    )
    actions.add_argument(
        "--rollback-site",
        metavar="NAME",
        help="Preview restoring a previous site release",
    )
    actions.add_argument(
        "--clone-site",
        metavar="DIRECTORY",
        type=Path,
        help="Clone an editable collection from a shared publishing location",
    )
    actions.add_argument(
        "--push-site",
        metavar="DIRECTORY",
        type=Path,
        help="Preview merging changes into a shared publishing location",
    )
    actions.add_argument(
        "--copy-site",
        metavar="NAME",
        help="Copy a destination's live site to a new folder",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply a site publish or rollback"
    )
    parser.add_argument(
        "--release", metavar="ID", help="Choose a specific release for --rollback-site"
    )
    parser.add_argument("--name", help="Collection name for --init")
    parser.add_argument("--prefix", default="KB", help="ID prefix for --init")
    parser.add_argument("--digits", type=int, default=5, help="ID digits for --init")
    parser.add_argument("--language", default="en-US", help="Language for --init")
    parser.add_argument(
        "--output", type=Path, help="Output file or folder for export or backup"
    )
    actions.add_argument(
        "--export-theme", type=Path, metavar="ZIP", help="Export branding and layout"
    )
    actions.add_argument(
        "--import-theme", type=Path, metavar="ZIP", help="Apply branding and layout"
    )
    actions.add_argument(
        "--renumber",
        nargs=2,
        metavar=("OLD_ID", "NEW_ID"),
        help="Preview an article ID migration",
    )
    parser.add_argument(
        "--force", action="store_true", help="Apply a previewed article migration"
    )
    actions.add_argument(
        "--import-package",
        type=Path,
        metavar="DIRECTORY",
        help="Import an article package",
    )
    actions.add_argument(
        "--migrate",
        metavar="NAME",
        choices=sorted(MIGRATIONS),
        help="Preview an article standards migration",
    )
    actions.add_argument(
        "--update", action="store_true", help="Update this Git checkout"
    )
    actions.add_argument(
        "--backup-collection", action="store_true", help="Archive the entire collection"
    )
    actions.add_argument(
        "--backup-all-collections",
        action="store_true",
        help="Archive all collections directly inside the given parent directory",
    )
    actions.add_argument(
        "--run-scheduled-backup",
        action="store_true",
        help="Run the collection's scheduled backup if due",
    )
    parser.add_argument("--author", help="Author value for the author migration")
    args = parser.parse_args()
    if args.html_only and not (args.export_site or args.publish_site or args.push_site):
        parser.error(
            "--html-only requires --export-site, --publish-site, or --push-site."
        )
    if args.apply and not (args.publish_site or args.rollback_site or args.push_site):
        parser.error(
            "--apply requires --publish-site, --rollback-site, or --push-site."
        )
    if args.release and not args.rollback_site:
        parser.error("--release requires --rollback-site.")
    if args.force and not (args.renumber or args.migrate):
        parser.error("--force requires --renumber or --migrate.")
    if (args.author is not None) != (args.migrate == "author"):
        parser.error("--migrate author requires --author, and vice versa.")
    backup = args.backup_collection or args.backup_all_collections
    if bool(
        args.export_pdf
        or args.export_pdfs
        or args.export_site
        or args.clone_site
        or args.copy_site
        or backup
    ) != bool(args.output):
        parser.error(
            "--output is required for export, site cloning, and manual backups."
        )
    if args.update or args.clone_site:
        if args.collection is not None:
            parser.error("--update and --clone-site take no collection path.")
    elif args.collection is None:
        parser.error(
            "Provide a collection directory (or a parent for --backup-all-collections)."
        )
    if not (
        args.update
        or backup
        or args.init
        or args.export_theme
        or args.import_theme
        or args.renumber
        or args.migrate
        or args.rollback_site
        or args.clone_site
        or args.copy_site
        or args.run_scheduled_backup
        or (args.publish_site and not args.apply)
        or (args.push_site and not args.apply)
    ) and not shutil.which("pandoc"):
        parser.error("Pandoc is required and must be on PATH.")
    try:
        if args.clone_site:
            release = clone_site(args.clone_site, args.output)
            print(f"Cloned editable source at {release}. Open collection {args.output}")
            return 0
        if args.update:
            result = update_checkout()
            if result:
                before, after = result
                print(
                    f"Updated KB Forge from {before} to {after}. Restart any running instance."
                )
            else:
                print("This checkout matches its configured upstream branch.")
            return 0
        if backup:
            count = backup_collections(
                args.collection,
                args.output,
                all_collections=args.backup_all_collections,
            )
            label = "collection" if count == 1 else "collections"
            print(f"Backed up {count} {label} to {args.output}")
            return 0
        if args.init:
            initialize_collection(
                args.collection,
                args.name if args.name is not None else args.collection.resolve().name,
                args.prefix,
                args.digits,
                args.language,
            )
            print(f"Created {args.collection}")
            return 0
        repo = Repository(args.collection)
        if args.push_site:
            target, release, changes, renumbered, refresh = push_site(
                repo, args.push_site, include_pdfs=not args.html_only, apply=args.apply
            )
            for old, new in renumbered:
                print(f"Incoming article ID {old} → {new}")
            for line in change_lines(changes):
                print(line)
            if release:
                print(f"Published {release}. Open {target / 'index.html'}")
                if refresh:
                    print(
                        "Clone the merged source into a fresh folder before your next push."
                    )
            else:
                print("Preview only. Add --apply to merge and publish.")
            return 0
        if args.run_scheduled_backup:
            schedule = backup_schedule(repo)
            if schedule is None:
                raise ValueError(
                    "Configure scheduled_backup before running the schedule."
                )
            output = run_scheduled_backup(repo, schedule)
            print(output if output else "No scheduled backup is due.")
            return 0
        if args.publish_site:
            target, release, changes = publish_site(
                repo,
                args.publish_site,
                include_pdfs=not args.html_only,
                apply=args.apply,
            )
            print(f"Destination: {target}")
            for line in change_lines(changes):
                print(line)
            if release:
                print(f"Published {release}. Open {target / 'index.html'}")
            else:
                if not changes:
                    print("No article-edition changes.")
                print("Preview only. Add --apply to build and publish.")
            return 0
        if args.rollback_site:
            target, current, chosen = rollback_site(
                repo, args.rollback_site, release_id=args.release, apply=args.apply
            )
            print(f"{target}: {current} → {chosen}")
            print(
                "Active release updated."
                if args.apply
                else "Preview only. Add --apply to switch."
            )
            return 0
        if args.copy_site:
            release = copy_site(repo, args.copy_site, args.output)
            print(f"Copied {release}. Open {args.output / 'index.html'}")
            return 0
        if args.migrate:
            paths = migrate_articles(repo, args.migrate, args.author, force=args.force)
            for path in paths:
                print(path.relative_to(repo.root))
            if args.force:
                print(f"Migrated {len(paths)} article editions.")
            else:
                print(
                    f"Preview only: {len(paths)} article editions would change. Rerun with --force to apply."
                )
            return 0
        if args.import_package:
            article_id, findings = import_package(repo, args.import_package)
            for severity, path, message in findings:
                print(f"{severity}\t{path}\t{message}")
            print(f"Imported {article_id}")
            return 0
        if args.renumber:
            old, new = args.renumber
            changed = renumber(repo, old, new, force=args.force)
            for path in changed:
                print(path.relative_to(repo.root))
            if args.force:
                print(
                    f"Renumbered {old} to {new}. Validate the collection and refresh its exports."
                )
            else:
                print(
                    f"Preview only: {old} → {new}. Stop KB Forge, back up the collection, then rerun with --force to apply."
                )
            return 0
        if args.export_site:
            export_html(repo, args.output, include_pdfs=not args.html_only)
            print(args.output / "index.html")
            return 0
        if args.export_theme:
            export_theme(repo, args.export_theme)
            print(args.export_theme)
            return 0
        if args.import_theme:
            import_theme(repo, args.import_theme)
            print(f"Applied theme to {repo.root}")
            return 0
        if args.export_pdfs:
            count = export_pdfs(repo, args.output)
            unit = "PDF" if count == 1 else "PDFs"
            print(f"Exported {count} {unit} to {args.output}")
            return 0
        if args.export_pdf:
            import os
            import tempfile

            data = export_pdf(repo, repo.article_path(*args.export_pdf))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=args.output.parent, delete=False
            ) as stream:
                temp = Path(stream.name)
            try:
                temp.write_bytes(data)
                os.replace(temp, args.output)
            finally:
                temp.unlink(missing_ok=True)
            print(args.output)
            return 0
        if args.validate:
            findings = repo.validate()
            for severity, path, message in findings:
                print(f"{severity}\t{path}\t{message}")
            return int(any(severity == "Error" for severity, _, _ in findings))
        schedule = backup_schedule(repo)
        try:
            server = ThreadingHTTPServer(
                ("127.0.0.1", args.port), partial(Handler, repo, secrets.token_hex(32))
            )
        except OSError as error:
            raise ValueError(
                f"Could not start the workspace at 127.0.0.1:{args.port}: {error}. "
                "If another program is using the port, choose another with --port."
            ) from error
        with server:
            server.write_lock = threading.Lock()
            server.update_lock = threading.Lock()
            stop = threading.Event()

            def update_worker():
                while not stop.is_set():
                    with server.update_lock:
                        if getattr(server, "restart_required", False):
                            return
                        server.update_available = update_available()
                    stop.wait(15 * 60)

            def backup_worker():
                while not stop.is_set():
                    try:
                        with server.write_lock:
                            output = run_scheduled_backup(repo, schedule)
                        if output:
                            print(f"Scheduled backup: {output}", flush=True)
                    except (ValueError, OSError) as error:
                        print(
                            f"KB Forge scheduled backup: {error}",
                            file=sys.stderr,
                            flush=True,
                        )
                    stop.wait(60)

            worker = threading.Thread(target=backup_worker) if schedule else None
            print(
                f"KB Forge is running at http://127.0.0.1:{server.server_port}",
                flush=True,
            )
            if worker:
                worker.start()
            threading.Thread(target=update_worker, daemon=True).start()
            try:
                server.serve_forever()
            finally:
                stop.set()
                if worker:
                    worker.join()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"KB Forge: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
