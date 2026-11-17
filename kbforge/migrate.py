"""Apply explicit, repeatable migrations to article source files."""

import json
import os
import re

from .repository import atomic_text, read_mapping


def author_migration(value):
    author = " ".join(value.split())
    if not author:
        raise ValueError("Provide a nonempty author name.")

    def apply(metadata):
        existing = metadata.get("author")
        if existing is None or (isinstance(existing, str) and not existing.strip()):
            metadata["author"] = author

    return apply


MIGRATIONS = {"author": author_migration}


def migration_plan(repo, transform):
    changes = {}
    for path, _, _, error in repo.scan():
        if error or path.is_symlink() or path.parent.is_symlink():
            raise ValueError(
                f"Resolve the unreadable or linked article before migration: {path}"
            )
        original = path.read_bytes().decode("utf-8")
        preamble, opening, front_matter, closing, body = re.split(
            r"(?m)(^---[ \t]*\r?\n)", original, maxsplit=2
        )
        if preamble:
            raise ValueError(f"Expected front matter at the start of {path}.")
        metadata = read_mapping(front_matter)
        before = metadata.copy()
        transform(metadata)
        if metadata != before:
            newline = "\r\n" if opening.endswith("\r\n") else "\n"
            updated = json.dumps(metadata, ensure_ascii=False, indent=2)
            changes[path] = (
                original,
                opening + updated.replace("\n", newline) + newline + closing + body,
            )
    return changes


def migrate_articles(repo, migration, value, *, force=False):
    transform = MIGRATIONS[migration](value)
    if not force:
        return list(migration_plan(repo, transform))

    lock = repo.path("registry", "allocate.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError(
            "Another collection maintenance operation is active."
        ) from error
    try:
        os.close(descriptor)
        changes = migration_plan(repo, transform)
        written = []
        try:
            for path, (original, updated) in changes.items():
                if path.read_bytes() != original.encode("utf-8"):
                    raise ValueError(f"Article changed during migration: {path}")
                atomic_text(path, updated)
                written.append(path)
        except (OSError, ValueError, KeyboardInterrupt):
            for path in reversed(written):
                atomic_text(path, changes[path][0])
            raise
        return list(changes)
    finally:
        lock.unlink()
