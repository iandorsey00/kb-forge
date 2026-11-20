"""Publish portable site snapshots to a dedicated filesystem destination."""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from secrets import token_hex
import shutil
from tempfile import TemporaryDirectory

from .backup import is_real_directory
from .publishing import export_html, site_editions
from .repository import TOKEN, read_mapping

RELEASE_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}")


def destination_for(repo, name):
    destinations = repo.config.get("publication_destinations", {})
    if not isinstance(destinations, dict) or not TOKEN.fullmatch(name):
        raise ValueError("Configure named paths in publication_destinations.")
    raw = destinations.get(name)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"No filesystem path configured for destination {name}.")
    path = (repo.root / Path(raw).expanduser()).resolve()
    if (
        path.name == "site"
        and (path.parent / "source").is_dir()
        and (release := active_release(path))
        and (path.parent / "source" / release / "kbforge.yaml").is_file()
    ):
        raise ValueError("Use --push-site with the parent collaboration directory.")
    if path.is_relative_to(repo.root) or repo.root.is_relative_to(path):
        raise ValueError(
            "Choose a publishing destination separate from the collection."
        )
    return path


def landing_page(release_id):
    url = f"releases/{release_id}/index.html"
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={url}">\n'
        f'<title>Published site</title><a href="{url}">Open published site</a></html>\n'
    )


def active_release(target):
    if not target.exists():
        return None
    releases = target / "releases"
    index = target / "index.html"
    if (
        not target.is_dir()
        or any(
            item.name not in {"index.html", "releases", ".publish.lock"}
            for item in target.iterdir()
        )
        or (releases.exists() and not is_real_directory(releases))
        or releases.is_symlink()
        or index.is_symlink()
        or (index.exists() and not index.is_file())
    ):
        raise ValueError("Use an empty or dedicated KB Forge publishing destination.")
    if not index.exists():
        if releases.exists() and any(
            not (RELEASE_ID.fullmatch(item.name) or item.name.startswith(".stage-"))
            for item in releases.iterdir()
        ):
            raise ValueError(
                "The destination contains an unrelated releases directory."
            )
        return None
    contents = index.read_text(encoding="utf-8")
    match = re.search(r"releases/([^/]+)/index\.html", contents)
    if (
        not match
        or not RELEASE_ID.fullmatch(match[1])
        or contents != landing_page(match[1])
    ):
        raise ValueError("The destination homepage is not managed by KB Forge.")
    return match[1]


def load_release(target, release_id):
    if not isinstance(release_id, str) or not RELEASE_ID.fullmatch(release_id):
        raise ValueError("Invalid site release ID.")
    folder = target / "releases" / release_id
    manifest = folder / "manifest.json"
    if not is_real_directory(folder) or manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Invalid site release directory.")
    data = read_mapping(manifest.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("release_id") != release_id:
        raise ValueError(f"Invalid site manifest for {release_id}.")
    return folder, data


def changes_between(editions, previous):
    current = {edition["html"]: edition for edition in editions}
    old = {edition["html"]: edition for edition in previous}
    changes = []
    for path, edition in current.items():
        if path not in old:
            changes.append(("new", edition))
        elif old[path]["source_sha256"] != edition["source_sha256"]:
            changes.append(("updated", edition))
    changes.extend(
        ("removed", edition) for path, edition in old.items() if path not in current
    )
    return changes


def change_lines(changes):
    return [
        f"{kind.title()}: {edition['id']} ({edition['language']}) · {edition['title']}"
        for kind, edition in changes
    ]


def switch_release(target, staging, release_id):
    pointer = staging / "index.html"
    pointer.write_text(landing_page(release_id), encoding="utf-8", newline="\n")
    os.replace(pointer, target / "index.html")


def publish_site(repo, name, *, include_pdfs=True, apply=False):
    target = destination_for(repo, name)
    return publish_to(repo, target, include_pdfs=include_pdfs, apply=apply)


def publish_to(repo, target, *, include_pdfs=True, apply=False, save_source=None):
    current = active_release(target)
    previous = load_release(target, current)[1] if current else {}
    editions = site_editions(repo, include_pdfs, strict=True)
    changes = changes_between(editions.values(), previous.get("editions", []))
    if not apply:
        return target, None, changes

    target.mkdir(exist_ok=True)
    lock = target / ".publish.lock"
    lock.mkdir()
    try:
        if active_release(target) != current:
            raise ValueError(
                "The active release changed. Preview again before publishing."
            )
        releases = target / "releases"
        releases.mkdir(exist_ok=True)
        now = datetime.now(timezone.utc)
        release_id = now.strftime("%Y%m%dT%H%M%SZ-") + token_hex(4)
        day = now.date().isoformat()
        recent = []
        for kind, edition in changes:
            if kind != "removed":
                recent.append(
                    {
                        "kind": kind,
                        "html": edition["html"],
                        "date": day,
                        "note": edition.get("release_note", ""),
                    }
                )
        # Leave at most one announcement per still-published edition.
        changed_paths = {edition["html"] for _, edition in changes}
        live_paths = {edition["html"] for edition in editions.values()}
        recent.extend(
            event
            for event in previous.get("recent_changes", [])
            if event["html"] in live_paths - changed_paths
        )
        metadata = {
            "release_id": release_id,
            "previous_release": current,
            "published_at": now.isoformat(timespec="seconds"),
            "recent_changes": recent[:10],
        }
        with TemporaryDirectory(dir=releases, prefix=".stage-") as temporary:
            staging = Path(temporary)
            site = staging / "site"
            export_html(
                repo,
                site,
                include_pdfs=include_pdfs,
                release=metadata,
                published=editions,
            )
            if site_editions(repo, include_pdfs, strict=True) != editions:
                raise ValueError(
                    "Article sources changed during export. Publish again after editing."
                )
            site.rename(releases / release_id)
            if save_source:
                save_source(release_id)
            switch_release(target, staging, release_id)
    finally:
        lock.rmdir()
    return target, release_id, changes


def rollback_site(repo, name, *, release_id=None, apply=False):
    target = destination_for(repo, name)
    current = active_release(target)
    if current is None:
        raise ValueError("There is no active release at this destination.")
    _, previous = load_release(target, current)
    chosen = release_id if release_id is not None else previous.get("previous_release")
    if chosen is None:
        raise ValueError("There is no previous release at this destination.")
    folder, _ = load_release(target, chosen)
    if not (folder / "index.html").is_file() or (folder / "index.html").is_symlink():
        raise ValueError(f"Release {chosen} has no readable homepage.")
    if apply and chosen != current:
        lock = target / ".publish.lock"
        lock.mkdir()
        try:
            if active_release(target) != current:
                raise ValueError(
                    "The active release changed. Preview again before rolling back."
                )
            with TemporaryDirectory(
                dir=target / "releases", prefix=".stage-"
            ) as temporary:
                switch_release(target, Path(temporary), chosen)
        finally:
            lock.rmdir()
    return target, current, chosen


def copy_site(repo, name, output):
    target = destination_for(repo, name)
    current = active_release(target)
    if current is None:
        raise ValueError("There is no active release at this destination.")
    if any(output.resolve().is_relative_to(root) for root in (target, repo.root)):
        raise ValueError(
            "Clone into a new directory outside the destination and collection."
        )
    folder, manifest = load_release(target, current)
    files = ["index.html", "style.css", "manifest.json"]
    for edition in manifest["editions"]:
        article_id, language = edition["id"], edition["language"]
        repo.article_path(article_id, language)
        stem = f"articles/{article_id}/{language}"
        files.append(f"{stem}.html")
        if "pdf" in edition:
            files.append(f"{stem}.pdf")
    output.mkdir()
    try:
        for name in files:
            source = folder / name
            if not source.is_file() or source.resolve() != source:
                raise ValueError(f"Invalid published file: {name}")
            copy = output / name
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copy)
    except BaseException:
        shutil.rmtree(output)
        raise
    return current
