"""Archive complete collection folders without changing their contents."""

import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
from stat import S_ISDIR, S_ISREG
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

# Windows junctions can report directory mode even though they redirect the walk.
WINDOWS_MOUNT_POINT = 0xA0000003


def is_real_directory(path):
    info = path.lstat()
    return (
        S_ISDIR(info.st_mode)
        and getattr(info, "st_reparse_tag", None) != WINDOWS_MOUNT_POINT
    )


def backup_collections(source, destination, *, all_collections=False):
    source = source.absolute()
    if not source.is_dir() or not is_real_directory(source):
        raise ValueError("Select a collection directory or a parent of collections.")
    source = source.resolve()
    roots = (
        sorted(
            child
            for child in source.iterdir()
            if child.is_dir() and (child / "kbforge.yaml").is_file()
        )
        if all_collections
        else [source]
    )
    if not roots:
        raise ValueError(
            "No collections with kbforge.yaml found directly under the parent."
        )
    if any(
        not is_real_directory(root) or not (root / "kbforge.yaml").is_file()
        for root in roots
    ):
        raise ValueError("Each collection must be a real directory with kbforge.yaml.")
    if len({root.name.casefold() for root in roots}) != len(roots):
        raise ValueError(
            "Collection names must be distinct on case-insensitive systems."
        )
    destination = destination.resolve()
    if any(
        parent.samefile(root)
        for parent in destination.parents
        if parent.is_dir()
        for root in roots
    ):
        raise ValueError("Save the backup ZIP outside the collections being backed up.")

    def fail(error):
        raise error

    # Exclusive creation protects older backups and makes cleanup safe on a failed run.
    with destination.open("x+b") as stream:
        try:
            with ZipFile(
                stream, "w", compression=ZIP_DEFLATED, strict_timestamps=False
            ) as archive:
                for root in roots:
                    for folder, dirs, files in os.walk(root, onerror=fail):
                        directory = Path(folder)
                        for name in dirs:
                            if not is_real_directory(directory / name):
                                raise ValueError(
                                    f"Cannot back up a linked directory: {directory / name}"
                                )
                        archive.write(
                            directory, directory.relative_to(root.parent).as_posix()
                        )
                        for name in sorted(files):
                            path = directory / name
                            if not S_ISREG(path.lstat().st_mode):
                                raise ValueError(
                                    f"Cannot back up a symlink or special file: {path}"
                                )
                            archive.write(
                                path, path.relative_to(root.parent).as_posix()
                            )
                        dirs.sort()
            try:
                with ZipFile(stream) as archive:
                    if damaged := archive.testzip():
                        raise ValueError(f"Backup verification failed for {damaged}.")
            except BadZipFile as error:
                raise ValueError(
                    "The generated backup ZIP could not be verified."
                ) from error
        except BaseException:
            stream.close()
            destination.unlink()
            raise
    return len(roots)


def backup_schedule(repo):
    """Read an optional per-collection schedule and resolve its archive directory."""
    if "scheduled_backup" not in repo.config:
        return None
    config = repo.config["scheduled_backup"]
    if not isinstance(config, dict):
        raise ValueError("scheduled_backup must specify directory and interval_hours.")
    directory = config.get("directory")
    hours = config.get("interval_hours")
    if (
        not isinstance(directory, str)
        or not directory.strip()
        or type(hours) is not int
        or hours < 1
    ):
        raise ValueError(
            "Set scheduled_backup.directory and a positive integer interval_hours."
        )
    target = (repo.root / Path(directory).expanduser()).resolve()
    if target.is_relative_to(repo.root):
        raise ValueError("Save scheduled backups outside the collection.")
    return target, hours


def run_scheduled_backup(repo, schedule, *, now=None):
    target, hours = schedule
    now = now or datetime.now(timezone.utc)
    # A source-specific prefix lets schedules share the same archive directory.
    identity = sha256(os.fsencode(os.path.normcase(repo.root))).hexdigest()[:16]
    prefix = f"kbforge-{identity}-"
    stamp_format = "%Y%m%dT%H%M%SZ"
    target.mkdir(exist_ok=True)
    lock = target / f".{prefix}lock"
    lock.mkdir()
    try:
        stamps = []
        for path in target.glob(f"{prefix}*.zip"):
            match = re.fullmatch(re.escape(prefix) + r"(\d{8}T\d{6}Z)\.zip", path.name)
            if match and path.is_file() and not path.is_symlink():
                stamps.append(
                    datetime.strptime(match[1], stamp_format).replace(
                        tzinfo=timezone.utc
                    )
                )
        if stamps and (now - max(stamps)).total_seconds() < hours * 3600:
            return None
        output = target / f"{prefix}{now.strftime(stamp_format)}.zip"
        with TemporaryDirectory(dir=target, prefix=".backup-") as temporary:
            staged = Path(temporary) / output.name
            backup_collections(repo.root, staged)
            staged.rename(output)
        return output
    finally:
        lock.rmdir()
