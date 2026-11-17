"""Read, write, and validate a portable Markdown collection."""

import json
import os
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
LANGUAGE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
ASSET = re.compile(r"[a-z0-9][a-z0-9-]*\.(?:png|jpg|gif|webp)")
IMAGE_TYPES = {
    "png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
    "webp": lambda data: data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}
STATUSES = ("draft", "published", "retired")
LIST_FIELDS = ("products", "categories", "regions", "countries", "tags")


def atomic_text(path, content):
    """Replace a file after its complete contents are staged on the same filesystem."""
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read_mapping(text):
    """Read the JSON-compatible subset of YAML used by the collection standard."""

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Repeated key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")

    data = json.loads(
        text, object_pairs_hook=unique_keys, parse_constant=invalid_constant
    )
    if not isinstance(data, dict):
        raise ValueError("Expected a mapping.")
    return data


def load_article(path):
    first, metadata, body = re.split(
        r"(?m)^---[ \t]*\n", path.read_text(encoding="utf-8"), maxsplit=2
    )
    if first:
        raise ValueError("Expected YAML front matter at the start of the file.")
    return read_mapping(metadata), body


def save_article(path, metadata, body):
    front_matter = json.dumps(metadata, ensure_ascii=False, indent=2)
    atomic_text(path, f"---\n{front_matter}\n---\n\n{body.strip()}\n")


def pandoc(markdown, output):
    try:
        result = subprocess.run(
            [
                "pandoc",
                "--sandbox",
                "--from=gfm-yaml_metadata_block-raw_html",
                f"--to={output}",
            ],
            input=markdown,
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        raise ValueError(
            "Pandoc could not process the article. Check installation and article syntax."
        ) from error
    return result.stdout


def initialize_collection(root, name, prefix, digits, language):
    """Create a minimal collection without sample articles or reserved IDs."""
    if (
        not TOKEN.fullmatch(prefix)
        or not 1 <= digits <= 12
        or len(prefix) + digits + 1 > 80
    ):
        raise ValueError("Invalid ID prefix or digit count.")
    if not LANGUAGE.fullmatch(language) or not name.strip():
        raise ValueError("Use a nonempty collection name and a valid language tag.")
    root.mkdir()
    try:
        (root / "articles").mkdir()
        (root / "registry").mkdir()
        write_json(root / "registry" / "ids.yaml", {})
        write_json(
            root / "kbforge.yaml",
            {
                "identifiers": {
                    "prefix": prefix,
                    "separator": "-",
                    "digits": digits,
                    "start": 1,
                },
                "languages": [language],
                "branding": {"name": name.strip()},
                "templates": {"article": {"label": "Article", "sections": []}},
            },
        )
    except OSError:
        # The root was freshly created by this operation.
        import shutil

        shutil.rmtree(root)
        raise


class Repository:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = read_mapping(
            self.path("kbforge.yaml").read_text(encoding="utf-8")
        )
        ids = self.config["identifiers"]
        if (
            not TOKEN.fullmatch(ids["prefix"])
            or ids["separator"] not in ("-", "_")
            or type(ids["digits"]) is not int
            or not 1 <= ids["digits"] <= 12
            or type(ids["start"]) is not int
            or not 1 <= ids["start"] < 10 ** ids["digits"]
            or len(ids["prefix"]) + 1 + ids["digits"] > 80
        ):
            raise ValueError("Invalid identifier configuration.")
        if not self.config["languages"] or any(
            not LANGUAGE.fullmatch(language) for language in self.config["languages"]
        ):
            raise ValueError("Configure at least one valid language tag.")
        self.templates = self.config["templates"]
        for name, template in self.templates.items():
            if not TOKEN.fullmatch(name):
                raise ValueError("Invalid template name.")
            if not isinstance(template["sections"], list) or not all(
                isinstance(section, str) for section in template["sections"]
            ):
                raise ValueError("Template sections must be an array of strings.")

    def path(self, *parts):
        candidate = self.root.joinpath(*parts)
        if not candidate.resolve().is_relative_to(self.root):
            raise ValueError("Path is outside the collection.")
        return candidate

    def article_path(self, article_id, language):
        if not TOKEN.fullmatch(article_id) or not LANGUAGE.fullmatch(language):
            raise ValueError("Invalid article ID or language.")
        return self.path("articles", article_id, language + ".md")

    def scan(self):
        """Yield editions and their parse errors so one bad file cannot hide its peers."""
        for path in sorted(self.path("articles").glob("*/*.md")):
            try:
                path = self.path("articles", path.parent.name, path.name)
                metadata, body = load_article(path)
                yield path, metadata, body, ""
            except (OSError, ValueError) as error:
                yield path, {}, "", str(error)

    def reserve_id(self):
        """Reserve a permanent ID before creating any article files."""
        config = self.config["identifiers"]
        registry = self.path("registry")
        registry.mkdir(exist_ok=True)
        lock = self.path("registry", "allocate.lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise ValueError(
                "ID allocation is locked. Retry after the other operation finishes."
            ) from error
        try:
            os.close(descriptor)
            manifest = self.path("registry", "ids.yaml")
            entries = (
                read_mapping(manifest.read_text(encoding="utf-8"))
                if manifest.exists()
                else {}
            )
            used = set(entries)
            # Keep retired IDs reserved and avoid collisions with unregistered articles.
            for path, metadata, _, _ in self.scan():
                used.add(path.parent.name)
                if isinstance(metadata.get("id"), str):
                    used.add(metadata["id"])
            number = config["start"]
            head = config["prefix"] + config["separator"]
            while number < 10 ** config["digits"]:
                article_id = f"{head}{number:0{config["digits"]}d}"
                if (
                    article_id not in used
                    and not self.path("articles", article_id).exists()
                ):
                    entries[article_id] = date.today().isoformat()
                    write_json(manifest, entries)
                    return article_id
                number += 1
            raise ValueError("The configured ID range is exhausted.")
        finally:
            lock.unlink()

    def create(self, metadata, translation_of=""):
        if metadata.get("language") not in self.config["languages"]:
            raise ValueError("Select a configured language.")
        if metadata.get("type") not in self.templates:
            raise ValueError("Select a configured document type.")
        for field in ("title", "owner"):
            if not metadata.get(field, "").strip():
                raise ValueError(f"{field.capitalize()} is required.")
        if metadata.get("review_on"):
            date.fromisoformat(metadata["review_on"])
        metadata = {
            **metadata,
            "status": "draft",
            "revision": 1,
            "updated_on": date.today().isoformat(),
        }
        if translation_of:
            source_id, _, source_language = translation_of.partition("/")
            source, _ = load_article(self.article_path(source_id, source_language))
            if (
                source.get("translation_of")
                or source.get("id") != source_id
                or source.get("language") != source_language
            ):
                raise ValueError("Select a valid source edition.")
            if type(source.get("revision")) is not int or source["revision"] < 1:
                raise ValueError("The source edition needs a valid revision.")
            metadata["translation_of"] = source_language
            metadata["source_revision"] = source["revision"]
            article_id = source_id
        else:
            article_id = self.reserve_id()
        metadata["id"] = article_id
        path = self.article_path(article_id, metadata["language"])
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path("articles", article_id, "assets").mkdir(exist_ok=True)
        sections = self.templates[metadata["type"]]["sections"]
        body = "\n\n".join(f"## {section}" for section in sections)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            front_matter = json.dumps(metadata, ensure_ascii=False, indent=2)
            stream.write(f"---\n{front_matter}\n---\n\n{body}\n")
        return path

    def store_image(self, article_id, filename, data):
        stem, extension = os.path.splitext(filename)
        extension = extension.lower().lstrip(".")
        extension = "jpg" if extension == "jpeg" else extension
        if (
            not 0 < len(data) <= 8 * 1024 * 1024
            or extension not in IMAGE_TYPES
            or not IMAGE_TYPES[extension](data)
        ):
            raise ValueError("Use a PNG, JPEG, GIF, or WebP image up to 8 MiB.")
        stem = (
            re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:64].rstrip("-")
            or "image"
        )
        folder = self.path("articles", article_id, "assets")
        folder.mkdir(exist_ok=True)
        for number in range(1, 10001):
            suffix = f"-{number}" if number > 1 else ""
            name = f"{stem}{suffix}.{extension}"
            candidate = self.path("articles", article_id, "assets", name)
            try:
                with candidate.open("xb") as stream:
                    try:
                        stream.write(data)
                    except OSError:
                        candidate.unlink(missing_ok=True)
                        raise
                return f"assets/{name}"
            except FileExistsError:
                continue
        raise ValueError("Too many images with that name.")

    def validate(self):
        from collections import Counter
        from urllib.parse import unquote, urlsplit

        articles = list(self.scan())
        editions = Counter()
        by_location = {}
        sources = Counter()
        registry = self.path("registry", "ids.yaml")
        used_images = set()
        findings = []

        def report(severity, path, message):
            findings.append((severity, path.relative_to(self.root).as_posix(), message))

        try:
            reservations = read_mapping(registry.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            report(
                "Error",
                registry,
                f"Restore or repair the reserved ID registry: {error}",
            )
            reservations = {}
        for path, metadata, _, error in articles:
            # Index all editions before checking references and translation relationships.
            if error:
                report("Error", path, f"Fix the front matter: {error}")
                continue
            by_location[(path.parent.name, path.stem)] = metadata
            if "translation_of" not in metadata:
                sources[path.parent.name] += 1
            article_id, language = metadata.get("id"), metadata.get("language")
            if isinstance(article_id, str) and isinstance(language, str):
                editions[(article_id, language)] += 1

        for path, metadata, body, error in articles:
            if error:
                continue
            article_id, language = metadata.get("id"), metadata.get("language")
            if (
                not isinstance(article_id, str)
                or not TOKEN.fullmatch(article_id)
                or article_id != path.parent.name
            ):
                report(
                    "Error",
                    path,
                    "Set id to the valid permanent ID in the parent directory name.",
                )
            elif article_id not in reservations:
                report(
                    "Error",
                    path,
                    "Record the article ID in registry/ids.yaml before publishing.",
                )
            if language not in self.config["languages"] or language != path.stem:
                report(
                    "Error",
                    path,
                    "Set language to a configured tag matching the filename.",
                )
            if (
                isinstance(article_id, str)
                and isinstance(language, str)
                and editions[(article_id, language)] > 1
            ):
                report(
                    "Error",
                    path,
                    "This ID and language occur more than once. Keep one edition per language.",
                )
            if "translation_of" not in metadata and sources[path.parent.name] > 1:
                report(
                    "Error",
                    path,
                    "Choose one source edition and link each translation to it.",
                )
            for field in ("title", "owner"):
                if (
                    not isinstance(metadata.get(field), str)
                    or not metadata[field].strip()
                ):
                    report("Error", path, f"Set a nonempty {field}.")
            for field in LIST_FIELDS:
                values = metadata.get(field, [])
                if not isinstance(values, list) or not all(
                    isinstance(value, str) and value.strip() for value in values
                ):
                    report(
                        "Error", path, f"Set {field} to an array of nonempty strings."
                    )
            if metadata.get("status") not in STATUSES:
                report("Error", path, "Set status to draft, published, or retired.")
            if type(metadata.get("revision")) is not int or metadata["revision"] < 1:
                report("Error", path, "Set revision to a positive integer.")
            for field in ("updated_on", "review_on"):
                value = metadata.get(field)
                if field == "review_on" and (value is None or value == ""):
                    report("Warning", path, "Set a review date.")
                    continue
                try:
                    parsed = date.fromisoformat(value)
                    if parsed.isoformat() != value:
                        raise ValueError
                    if (
                        field == "review_on"
                        and parsed < date.today()
                        and metadata.get("status") != "retired"
                    ):
                        report(
                            "Warning",
                            path,
                            "Review is overdue. Review the article and set the next review date.",
                        )
                except (TypeError, ValueError):
                    report("Error", path, f"Use YYYY-MM-DD for {field}.")
            translation = metadata.get("translation_of")
            if "translation_of" in metadata:
                source = (
                    by_location.get((path.parent.name, translation))
                    if isinstance(translation, str)
                    else None
                )
                revision = metadata.get("source_revision")
                if (
                    not source
                    or "translation_of" in source
                    or type(source.get("revision")) is not int
                ):
                    report(
                        "Error",
                        path,
                        "Point translation_of to a source edition of this article.",
                    )
                elif (
                    type(revision) is not int or not 1 <= revision <= source["revision"]
                ):
                    report(
                        "Error",
                        path,
                        "Set source_revision to the source revision used for this translation.",
                    )
                elif revision < source["revision"]:
                    report(
                        "Warning",
                        path,
                        "Translation is outdated. Review the source changes and update source_revision.",
                    )
            related = metadata.get("related", [])
            if not isinstance(related, list):
                report("Error", path, "Set related to an array of article IDs.")
            else:
                for target in related:
                    if (
                        not isinstance(target, str)
                        or target == path.parent.name
                        or not any(folder == target for folder, _ in by_location)
                    ):
                        report(
                            "Error",
                            path,
                            f"Replace invalid related article ID: {target}",
                        )
            article_type = metadata.get("type")
            template = (
                self.templates.get(article_type)
                if isinstance(article_type, str)
                else None
            )
            if template is None:
                report("Error", path, "Set type to a configured document type.")

            try:
                ast = json.loads(pandoc(body, "json"))
            except ValueError as failure:
                report("Error", path, str(failure))
                continue
            if template is not None:
                headings = {
                    inline_text(block["c"][2])
                    for block in ast["blocks"]
                    if block["t"] == "Header" and block["c"][0] == 2
                }
                for heading in template["sections"]:
                    if heading not in headings:
                        report("Error", path, f"Add the required section: {heading}")
            for node in markdown_nodes(ast):
                kind, content = node["t"], node["c"]
                url = content[-1][0]
                try:
                    parts = urlsplit(url)
                    if parts.scheme or parts.netloc:
                        if kind == "Image":
                            report(
                                "Error",
                                path,
                                "Store images in the article's assets directory.",
                            )
                        elif parts.scheme not in ("http", "https", "mailto"):
                            report(
                                "Error",
                                path,
                                f"Use an HTTP, HTTPS, mailto, or relative link: {url}",
                            )
                        continue
                    target = unquote(parts.path)
                    if not target and kind == "Link":
                        continue
                    candidate = (path.parent / target).resolve()
                    if (
                        not candidate.is_relative_to(self.root)
                        or not candidate.is_file()
                    ):
                        report(
                            "Error",
                            path,
                            f"Fix the missing or invalid relative reference: {url}",
                        )
                        continue
                    if kind == "Image":
                        used_images.add(candidate)
                        if candidate.parent != (
                            path.parent / "assets"
                        ).resolve() or not ASSET.fullmatch(candidate.name):
                            report(
                                "Error",
                                path,
                                f"Move or rename image to match the asset convention: {url}",
                            )
                        if not content[1]:
                            report("Warning", path, f"Add alternative text for {url}.")
                except (ValueError, OSError) as failure:
                    report("Error", path, f"Invalid reference {url}: {failure}")

        for asset in self.path("articles").glob("*/assets/*"):
            if asset.is_file() and asset.resolve() not in used_images:
                report("Info", asset, "Asset is not referenced by a scanned article.")
        return findings


def markdown_nodes(value):
    if isinstance(value, dict):
        if value.get("t") in ("Link", "Image"):
            yield value
        for child in value.values():
            yield from markdown_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from markdown_nodes(child)


def inline_text(nodes):
    parts = []
    for node in nodes:
        kind = node["t"]
        if kind == "Str":
            parts.append(node["c"])
        elif kind in ("Space", "SoftBreak", "LineBreak"):
            parts.append(" ")
        elif kind in ("Emph", "Strong", "Strikeout"):
            parts.append(inline_text(node["c"]))
        elif kind == "Code":
            parts.append(node["c"][1])
    return "".join(parts)
