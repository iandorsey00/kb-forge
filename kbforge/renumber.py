"""Move a document ID deliberately while preserving old ID reservations."""

from datetime import date
import os
import re

from .repository import TOKEN, atomic_text, read_mapping, save_article, write_json


def plan_renumber(repo, old, new):
    if (
        any(not TOKEN.fullmatch(value) for value in (old, new))
        or old.casefold() == new.casefold()
    ):
        raise ValueError("Specify two distinct, valid document IDs.")
    source = repo.path("articles", old)
    destination = repo.path("articles", new)
    registry = repo.path("registry", "ids.yaml")
    reserved = read_mapping(registry.read_text(encoding="utf-8"))
    if any(key.casefold() == new.casefold() for key in reserved) or any(
        item.name.casefold() == new.casefold() for item in source.parent.iterdir()
    ):
        raise ValueError(f"Destination ID is already in use or reserved: {new}")
    if not source.is_dir() or source.is_symlink():
        raise ValueError(
            f"Article directory does not exist or is a symbolic link: {old}"
        )
    if old not in reserved:
        raise ValueError(f"Register the source ID before renumbering: {old}")

    # Match conventional inline Markdown destinations and reference definitions.
    # Leave URLs, prose, and fenced or inline code alone.
    links = re.compile(
        r"(?P<code>^[ \t]*([\x60~]{3,})[^\n]*\n[\s\S]*?(?:^[ \t]*\2[\x60~]*[ \t]*(?:\n|$)|\Z)|"
        r"(`+)[^\n]*?\3(?!`))|"
        r"(?P<destination>\]\([ \t]*<?|^[ \t]*\[[^\]\n]+\]:[ \t]*<?)"
        r"(?:\./)?\.\./" + re.escape(old) + r"(?=/)",
        re.MULTILINE,
    )
    changes = {}
    editions = 0
    for path, metadata, body, error in repo.scan():
        if error or path.is_symlink() or path.parent.is_symlink():
            raise ValueError(
                f"Resolve the unreadable or linked article before renumbering: {path}"
            )
        if path.parent == source:
            if metadata.get("id") != old:
                raise ValueError(
                    f"Fix the source article ID before renumbering: {path}"
                )
            previous = metadata.get("previous_ids", [])
            if not isinstance(previous, list) or not all(
                isinstance(value, str) for value in previous
            ):
                raise ValueError(f"Invalid previous_ids in {path}")
            metadata = {
                **metadata,
                "id": new,
                "previous_ids": list(dict.fromkeys([*previous, old])),
            }
            editions += 1
        elif metadata.get("id") in (old, new):
            raise ValueError(
                f"Resolve conflicting article metadata before renumbering: {path}"
            )
        related = metadata.get("related")
        if isinstance(related, list) and old in related:
            metadata = {
                **metadata,
                "related": [new if value == old else value for value in related],
            }
        else:
            related = None
        updated = links.sub(
            lambda match: (
                match[0] if match["code"] else match["destination"] + "../" + new
            ),
            body,
        )
        if path.parent == source or related is not None or updated != body:
            changes[path] = metadata, updated
    if not editions:
        raise ValueError(f"No Markdown editions found for {old}.")
    return source, destination, registry, reserved, changes


def renumber(repo, old, new, *, force=False):
    if not force:
        return list(plan_renumber(repo, old, new)[-1])

    lock = repo.path("registry", "allocate.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError("Another ID operation is active.") from error
    try:
        os.close(descriptor)
        source, destination, registry, reserved, changes = plan_renumber(repo, old, new)
        originals = {path: path.read_text(encoding="utf-8") for path in changes}
        originals[registry] = registry.read_text(encoding="utf-8")
        written = []
        moved = False
        try:
            source.rename(destination)
            moved = True
            for path, (metadata, body) in changes.items():
                target = destination / path.name if path.parent == source else path
                save_article(target, metadata, body)
                written.append(path)
            write_json(registry, {**reserved, new: date.today().isoformat()})
        except (OSError, ValueError, KeyboardInterrupt):
            if moved:
                destination.rename(source)
            for path in written:
                atomic_text(path, originals[path])
            if registry.read_text(encoding="utf-8") != originals[registry]:
                atomic_text(registry, originals[registry])
            raise
        return list(changes)
    finally:
        lock.unlink()
