"""A loopback-only graphical workspace for one portable collection."""

import argparse
import base64
import hashlib
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets
import shutil
import sys
from urllib.parse import parse_qs, urlsplit

from .theme import export_theme, import_theme
from .pdf import IMAGE_SUFFIXES, export_pdf, pdf_available, theme_asset
from .publishing import article_url, branded_article, esc, image_data
from .repository import LIST_FIELDS, STATUSES, Repository, load_article, save_article

STYLE = Path(__file__).with_name("style.css")
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


def select(name, label, values, selected="", empty=""):
    options = f'<option value="">{esc(empty)}</option>' if empty else ""
    for value, title in values:
        active = " selected" if value == selected else ""
        options += f'<option value="{esc(value)}"{active}>{esc(title)}</option>'
    return f'<label>{esc(label)}<select name="{name}">{options}</select></label>'


def field(name, label, value="", kind="text", required=False):
    return (
        f'<label>{esc(label)}<input name="{name}" type="{kind}" value="{esc(value)}"'
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

    def send_content(self, body, status=200, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'self' 'unsafe-inline'; img-src data:; "
            "script-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def page(self, title, body, status=200):
        brand = self.repo.config.get("workspace", {})
        name = esc(brand.get("name", "KB Forge"))
        css = []
        for setting in ("accent", "navigation", "background"):
            value = brand.get(setting, "")
            if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                css.append(f"--workspace-{setting}:{value}")
        logo = ""
        if brand.get("logo"):
            try:
                src = image_data(theme_asset(self.repo, brand["logo"], IMAGE_SUFFIXES))
                logo = f'<img class="workspace-logo" src="{esc(src)}" alt="">'
            except (ValueError, OSError):
                pass
        self.send_content(
            f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | {name}</title><link rel="stylesheet" href="/style.css">
<body style="{";".join(css)}">
<nav class="site" aria-label="Workspace"><strong><a href="/">{logo}{name}</a></strong>
<a href="/catalog">Catalog</a><a href="/create">New article</a><a href="/validate">Validation</a></nav>
<main>{body}</main><script src="/app.js" defer></script></body></html>""",
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
                    max_num_fields=60,
                )
                params.update(form)
                if not secrets.compare_digest(
                    params.get("_token", [""])[0].encode(), self.token.encode()
                ):
                    self.page(
                        "Forbidden",
                        "<h1>Forbidden</h1><p>Reload the form and try again.</p>",
                        403,
                    )
                    return
            values = {key: items[0] for key, items in params.items()}
            route = {
                ("GET", "/"): self.dashboard,
                ("GET", "/catalog"): self.catalog,
                ("GET", "/create"): self.create_form,
                ("POST", "/create"): self.create,
                ("GET", "/validate"): self.validation,
                ("GET", "/article"): self.article,
                ("GET", "/edit"): self.edit_form,
                ("POST", "/edit"): self.edit,
                ("POST", "/image"): self.upload,
                ("GET", "/publish"): self.publish,
                ("GET", "/pdf"): self.pdf,
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
            self.page(
                "Request could not be completed",
                f"<h1>Request could not be completed</h1><p>{esc(error)}</p>",
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
        for path, meta in catalog_rows(self.repo):
            searchable = " ".join(
                str(meta.get(key, ""))
                for key in (
                    "id",
                    "title",
                    "description",
                    "type",
                    "language",
                    "owner",
                    "status",
                    "review_on",
                    *LIST_FIELDS,
                )
            ).casefold()
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
        rows.sort(
            key=lambda row: (
                row[0].casefold(),
                str(row[2].get("title", "")).casefold(),
                row[1],
            )
        )
        headers = ["Article", "Language", "Type", "Owner", "Status", "Review date"]
        rendered_rows = [
            [
                f'<a href="{esc(article_url(path))}">{esc(meta.get("title", path.stem))}</a><br><small>{esc(path.parent.name)}</small>',
                *[
                    esc(meta.get(key, ""))
                    for key in ("language", "type", "owner", "status", "review_on")
                ],
            ]
            for _, path, meta in rows
        ]
        if group in group_fields:
            headers.insert(0, group_fields[group])
            for row, (key, _, _) in zip(rendered_rows, rows):
                row.insert(0, esc(key))
        filters = (
            field("q", "Search metadata", values.get("q", ""))
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
        )
        self.page(
            "Article catalog",
            f"""<h1>Article catalog</h1><form><div class="grid">{filters}</div>
<button>Search</button></form>{table(headers, rendered_rows)}""",
        )

    def metadata_fields(self, metadata):
        fields = []
        for name, label in FIELDS.items():
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
                )
            )
        related = metadata.get("related", [])
        fields.append(
            field(
                "related",
                "Related article IDs (comma separated)",
                ", ".join(map(str, related)),
            )
        )
        return "".join(fields)

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
        self.page(
            "New article",
            f"""<h1>New article</h1><form class="panel" method="post">
{self.form_token()}<div class="grid">{languages}{types}{translation}{self.metadata_fields({})}</div>
<button>Create draft</button></form>""",
        )

    def create(self, values):
        metadata = self.submitted_metadata(values)
        metadata.update(
            language=values.get("language", ""), type=values.get("type", "")
        )
        path = self.repo.create(metadata, values.get("translation", ""))
        self.redirect(article_url(path, "edit"))

    def path_from(self, values):
        return self.repo.article_path(values.get("id", ""), values.get("language", ""))

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
        )

    def edit_form(self, values):
        path = self.path_from(values)
        fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
        metadata, body = load_article(path)
        status = select(
            "status",
            "Status",
            [(item, item.title()) for item in STATUSES],
            metadata.get("status"),
        )
        types = select(
            "type",
            "Document type",
            [
                (key, value.get("label", key))
                for key, value in self.repo.templates.items()
            ],
            metadata.get("type"),
        )
        translation = ""
        if metadata.get("translation_of"):
            translation = field(
                "source_revision",
                "Source revision used",
                metadata.get("source_revision", ""),
                "number",
                True,
            )
        assets = "".join(
            f"<li><code>{esc(file.relative_to(path.parent).as_posix())}</code></li>"
            for file in sorted((path.parent / "assets").glob("*"))
            if file.is_file()
        )
        self.page(
            "Edit article",
            f'''<h1>Edit article</h1><p>{esc(path.parent.name)} · {esc(path.stem)}</p>
<div class="actions"><a class="button secondary" href="{esc(article_url(path))}">View article</a></div>
<form class="panel" method="post" action="{esc(article_url(path, "edit"))}">
{self.form_token()}<input type="hidden" name="fingerprint" value="{fingerprint}">
<div class="grid">{self.metadata_fields(metadata)}{types}{status}{translation}</div>
<label>Article Markdown<textarea name="body">{esc(body.strip())}</textarea></label>
<button>Save changes</button></form>
<form class="panel" id="image-upload" method="post" action="{esc(article_url(path, "image"))}">
{self.form_token()}<h2>Add an image</h2><p>Save pending edits first. The image reference is added at the end of the article.</p>
<label>Image<input id="image-file" type="file" accept="image/png,image/jpeg,image/gif,image/webp" required></label>
{field("alt", "Describe the image for readers", required=True)}
<input type="hidden" name="filename"><input type="hidden" name="image">
<p id="upload-error" role="status"></p><button>Add image</button>
<noscript><p>Enable JavaScript to upload an image through this form.</p></noscript>
<ul>{assets}</ul></form>''',
        )

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
            if body.strip() != new_body.strip() or any(
                metadata.get(key) != value for key, value in updates.items()
            ):
                updates["revision"] = metadata["revision"] + 1
                updates["updated_on"] = date.today().isoformat()
                # Preserve organization-defined fields that the editor does not expose.
                save_article(path, {**metadata, **updates}, new_body)
        self.redirect(article_url(path))

    def upload(self, values):
        """Store the image and add its Markdown reference in one serialized edit."""
        path = self.path_from(values)
        alt = " ".join(values.get("alt", "").split())
        if not alt:
            raise ValueError("Describe the image for readers.")
        alt = alt.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        with self.server.write_lock:
            metadata, body = load_article(path)
            encoded = values.get("image", "")
            padding = "=" * (-len(encoded) % 4)
            image = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
            relative = self.repo.store_image(
                path.parent.name, values.get("filename", ""), image
            )
            try:
                metadata.update(
                    revision=metadata["revision"] + 1,
                    updated_on=date.today().isoformat(),
                )
                save_article(
                    path, metadata, body.rstrip() + f"\n\n![{alt}]({relative})"
                )
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
        self.send_content(
            export_pdf(self.repo, self.path_from(values)),
            content_type="application/pdf",
        )

    def publish(self, values):
        path = self.path_from(values)
        pdf_link = (
            f'<a class="button" href="{esc(article_url(path, "pdf"))}">Open branded PDF</a>'
            if pdf_available()
            else ""
        )
        self.page(
            "Publish article",
            f'''<div class="actions">
<a class="button secondary" href="{esc(article_url(path))}">Back to article</a>
{pdf_link}<button id="print">Print or save as PDF</button></div>
<p class="muted no-print">Choose Save as PDF in the print dialog. For best results, use a current Chromium browser and turn off its built-in headers and footers.</p>
{branded_article(self.repo, path)}''',
        )


def main():
    import threading

    parser = argparse.ArgumentParser(description="Open a portable KB Forge collection.")
    parser.add_argument(
        "collection", type=Path, help="Path to the collection directory"
    )
    parser.add_argument("--port", type=int, default=8765)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--validate", action="store_true", help="Validate the collection and exit"
    )
    actions.add_argument("--export-pdf", nargs=2, metavar=("ID", "LANGUAGE"))
    parser.add_argument("--output", type=Path, help="Output path for --export-pdf")
    actions.add_argument(
        "--export-theme", type=Path, metavar="ZIP", help="Export branding and layout"
    )
    actions.add_argument(
        "--import-theme", type=Path, metavar="ZIP", help="Apply branding and layout"
    )
    args = parser.parse_args()
    if bool(args.export_pdf) != bool(args.output):
        parser.error("--export-pdf and --output must be used together.")
    if not (args.export_theme or args.import_theme) and not shutil.which("pandoc"):
        parser.error("Pandoc is required and must be on PATH.")
    try:
        repo = Repository(args.collection)
        if args.export_theme:
            export_theme(repo, args.export_theme)
            print(args.export_theme)
            return 0
        if args.import_theme:
            import_theme(repo, args.import_theme)
            print(f"Applied theme to {repo.root}")
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
        with ThreadingHTTPServer(
            ("127.0.0.1", args.port), partial(Handler, repo, secrets.token_hex(32))
        ) as server:
            server.write_lock = threading.Lock()
            print(
                f"KB Forge is running at http://127.0.0.1:{server.server_port}",
                flush=True,
            )
            server.serve_forever()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"KB Forge: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
