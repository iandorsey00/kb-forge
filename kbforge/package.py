"""Import a folder containing all editions of one article."""

from datetime import date
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from .repository import ASSET, IMAGE_TYPES, load_article, read_mapping, write_json


def import_package(repo, source):
    """Import into an unused ID while retaining the source folder."""
    source = Path(source)
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Select an article package directory.")
    articles = repo.path("articles")
    articles.mkdir(exist_ok=True)
    registry = repo.path("registry", "ids.yaml")
    lock = repo.path("registry", "allocate.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError("Another ID operation is active.") from error
    try:
        os.close(fd)
        # Copy and inspect a snapshot before putting it in the collection.
        with TemporaryDirectory(dir=repo.root, prefix=".import-") as temporary:
            staged = Path(temporary) / "package"
            staged.mkdir()
            article_id = copy_package(repo, source, staged)
            destination = repo.path("articles", article_id)
            reservations = read_mapping(registry.read_text(encoding="utf-8"))
            occupied = set(reservations) | {path.name for path in articles.iterdir()}
            occupied.update(
                metadata["id"]
                for _, metadata, _, error in repo.scan()
                if not error and isinstance(metadata.get("id"), str)
            )
            if article_id.casefold() in {item.casefold() for item in occupied}:
                raise ValueError(
                    f"Article ID is already in use or reserved: {article_id}"
                )
            pending = {**reservations, article_id: date.today().isoformat()}
            staged.rename(destination)
            try:
                findings = repo.validate(
                    only_id=article_id, reservations_override=pending
                )
                errors = [
                    f"{path}: {message}"
                    for severity, path, message in findings
                    if severity == "Error"
                ]
                if errors:
                    raise ValueError(
                        "Article package failed validation:\n" + "\n".join(errors)
                    )
                write_json(registry, pending)
            except (OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
                # If the registry was written before an interrupt, leave the installed article.
                current = read_mapping(registry.read_text(encoding="utf-8"))
                if article_id not in current:
                    destination.rename(staged)
                raise
            return article_id, findings
    finally:
        lock.unlink()


def copy_package(repo, source, staged):
    article_id = None
    for item in sorted(source.iterdir()):
        if item.is_symlink():
            raise ValueError(
                f"Symbolic links are not allowed in a package: {item.name}"
            )
        if item.name == "assets" and item.is_dir():
            target = staged / "assets"
            target.mkdir()
            for asset in sorted(item.iterdir()):
                if (
                    asset.is_symlink()
                    or not asset.is_file()
                    or not ASSET.fullmatch(asset.name)
                ):
                    raise ValueError(f"Invalid package image: {asset.name}")
                with asset.open("rb") as stream:
                    data = stream.read(8 * 1024 * 1024 + 1)
                extension = asset.suffix[1:]
                if len(data) > 8 * 1024 * 1024 or not IMAGE_TYPES[extension](data):
                    raise ValueError(f"Invalid image or exceeds 8 MiB: {asset.name}")
                (target / asset.name).write_bytes(data)
            continue
        if (
            not item.is_file()
            or item.suffix != ".md"
            or item.stem not in repo.config["languages"]
        ):
            raise ValueError(
                f"Expected a configured <language>.md edition or assets/: {item.name}"
            )
        target = staged / item.name
        shutil.copyfile(item, target)
        metadata, _ = load_article(target)
        edition_id = metadata.get("id")
        if not isinstance(edition_id, str):
            raise ValueError(f"Set an article ID in {item.name}.")
        repo.article_path(edition_id, item.stem)
        if article_id is not None and edition_id != article_id:
            raise ValueError(
                "All editions in a package must share the same article ID."
            )
        article_id = edition_id
    if article_id is None:
        raise ValueError("The package contains no Markdown editions.")
    return article_id
