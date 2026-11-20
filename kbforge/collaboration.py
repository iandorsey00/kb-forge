"""Share editable collection snapshots beside a separately served static site."""

from hashlib import file_digest
import os
from pathlib import Path
import shutil
from stat import S_ISREG
from tempfile import TemporaryDirectory

from .backup import is_real_directory
from .renumber import renumber
from .repository import Repository, TOKEN, read_mapping, write_json
from .site_release import RELEASE_ID, active_release, publish_to

CHECKOUT = ".kbforge-clone.json"
REGISTRY = "registry/ids.yaml"
LOCAL_SETTINGS = ("publication_destinations", "scheduled_backup")


def fingerprints(root):
    files = {}

    def raise_error(error):
        raise error

    for directory, subdirs, names in os.walk(root, onerror=raise_error):
        folder = Path(directory)
        for child in subdirs:
            if not is_real_directory(folder / child):
                raise ValueError(f"Linked source directory: {folder / child}")
        for name in names:
            path = folder / name
            if not S_ISREG(path.lstat().st_mode):
                raise ValueError(f"Linked or special source file: {path}")
            with path.open("rb") as stream:
                files[path.relative_to(root).as_posix()] = file_digest(
                    stream, "sha256"
                ).hexdigest()
    if len({name.casefold() for name in files}) != len(files):
        raise ValueError(
            "Source files have conflicting names on case-insensitive filesystems."
        )
    return files


def copy_files(source, destination, names):
    for name in names:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, path)


def snapshot(repo, destination):
    destination.mkdir()
    config = {
        key: value for key, value in repo.config.items() if key not in LOCAL_SETTINGS
    }
    write_json(destination / "kbforge.yaml", config)
    for role in ("articles", "branding"):
        source = repo.root / role
        if source.is_symlink() or (source.exists() and not is_real_directory(source)):
            raise ValueError(f"Invalid source directory: {source}")
        if source.is_dir():
            copy_files(source, destination / role, fingerprints(source))
    registry_folder = repo.root / "registry"
    registry = repo.root / REGISTRY
    if (
        not is_real_directory(registry_folder)
        or not S_ISREG(registry.lstat().st_mode)
        or (registry_folder / "allocate.lock").exists()
    ):
        raise ValueError(
            "Use a regular ID registry and finish any active ID operations."
        )
    (destination / "registry").mkdir()
    write_json(destination / REGISTRY, dict(sorted(registry_at(repo.root).items())))


def shared_head(location):
    if not location.exists():
        return None
    if not is_real_directory(location) or any(
        item.name not in {"site", "source", ".push.lock"} for item in location.iterdir()
    ):
        raise ValueError("Use an empty or dedicated collaboration directory.")
    for name in ("site", "source"):
        path = location / name
        if path.is_symlink() or (path.exists() and not is_real_directory(path)):
            raise ValueError(f"Invalid collaboration directory: {path}")
    return active_release(location / "site")


def source_at(location, release):
    if not isinstance(release, str) or not RELEASE_ID.fullmatch(release):
        raise ValueError("Invalid source release ID.")
    path = location / "source" / release
    if not path.is_dir() or not is_real_directory(path):
        raise ValueError(
            f"Source for release {release} is unavailable at this location."
        )
    return path


def clone_site(location, output):
    location, output = location.resolve(), output.resolve()
    if output.is_relative_to(location):
        raise ValueError(
            "Clone to a new directory outside the collaboration directory."
        )
    head = shared_head(location)
    if head is None:
        raise ValueError("Push a site before cloning it.")
    source = source_at(location, head)
    output.mkdir()
    try:
        copy_files(source, output, fingerprints(source))
        write_json(output / CHECKOUT, {"base": head})
        Repository(output)
    except BaseException:
        shutil.rmtree(output)
        raise
    return head


def registry_at(root):
    data = read_mapping((root / REGISTRY).read_text(encoding="utf-8"))
    if any(not TOKEN.fullmatch(key) for key in data) or len(
        {key.casefold() for key in data}
    ) != len(data):
        raise ValueError("The ID registry contains invalid or ambiguous IDs.")
    return data


def renumber_new_collisions(local, base_ids, remote_ids):
    local_ids = registry_at(local)
    base_names = {key.casefold() for key in base_ids}
    remote_names = {key.casefold() for key in remote_ids}
    used = {key.casefold() for key in local_ids} | remote_names
    repo = Repository(local)
    used.update(path.parent.name.casefold() for path, _, _, _ in repo.scan())
    ids = repo.config["identifiers"]
    prefix = ids["prefix"] + ids["separator"]
    number = ids["start"]
    changes = []
    for old in sorted(local_ids):
        if old.casefold() in base_names or old.casefold() not in remote_names:
            continue
        if not any(repo.path("articles", old).glob("*.md")):
            raise ValueError(
                f"Conflicting unused reservation: {old}. Resolve it before pushing."
            )
        while number < 10 ** ids["digits"]:
            new = f"{prefix}{number:0{ids['digits']}d}"
            number += 1
            if new.casefold() not in used:
                break
        else:
            raise ValueError("The configured ID range is exhausted.")
        renumber(repo, old, new, force=True, remember_previous=False)
        registry = registry_at(local)
        del registry[old]
        write_json(local / REGISTRY, registry)
        used.add(new.casefold())
        changes.append((old, new))
    return changes


def merge_source(base, local, remote, output):
    base_digest, local_digest, remote_digest = (
        fingerprints(path) for path in (base, local, remote)
    )
    local_ids, remote_ids, base_ids = (
        registry_at(path) for path in (local, remote, base)
    )
    conflicts = []

    def choose(key, ancestor, ours, theirs):
        if ours == ancestor:
            return theirs
        if theirs == ancestor or ours == theirs:
            return ours
        conflicts.append(key)
        return None

    selected = {local: [], remote: []}
    for name in sorted(set(base_digest) | set(local_digest) | set(remote_digest)):
        if name == REGISTRY:
            continue
        ours = local_digest.get(name)
        chosen = choose(name, base_digest.get(name), ours, remote_digest.get(name))
        if chosen is not None:
            selected[local if chosen == ours else remote].append(name)
    merged_ids = {}
    for key in sorted(set(base_ids) | set(local_ids) | set(remote_ids)):
        chosen = choose(
            f"{REGISTRY}: {key}",
            base_ids.get(key),
            local_ids.get(key),
            remote_ids.get(key),
        )
        if chosen is not None:
            merged_ids[key] = chosen
    if conflicts:
        raise ValueError(
            "Merge conflicts. Shared site was not changed:\n" + "\n".join(conflicts)
        )

    # Validate names before writing, including folder/file collisions on Windows.
    names = [name for paths in selected.values() for name in paths] + [REGISTRY]
    folded = {name.casefold() for name in names}
    folders = {}
    for name in names:
        for parent in Path(name).parents:
            if parent == Path("."):
                continue
            original = parent.as_posix()
            previous = folders.setdefault(original.casefold(), original)
            if previous != original or original.casefold() in folded:
                raise ValueError(f"Conflicting source path: {original}")
    if len(folded) != len(names):
        raise ValueError("Conflicting source paths differ only in case.")
    output.mkdir()
    for source, paths in selected.items():
        copy_files(source, output, paths)
    (output / "registry").mkdir(exist_ok=True)
    write_json(output / REGISTRY, merged_ids)
    registry_at(output)


def push_site(repo, location, *, include_pdfs=True, apply=False):
    location = location.resolve()
    if repo.root.is_relative_to(location) or location.is_relative_to(repo.root):
        raise ValueError(
            "Choose a collaboration directory outside the source collection."
        )
    checkout = repo.root / CHECKOUT
    if checkout.is_symlink():
        raise ValueError("Invalid editable clone metadata.")
    state = (
        read_mapping(checkout.read_text(encoding="utf-8")) if checkout.exists() else {}
    )
    current = shared_head(location)
    if bool(current) != bool(state):
        raise ValueError(
            "Clone from this location before pushing, or use an empty location for the first push."
        )
    if state.get("refresh_required"):
        raise ValueError(
            "Clone the updated shared site into a new folder before pushing again."
        )

    def prepare_and_publish():
        head = shared_head(location)
        if head != current:
            raise ValueError(
                "Another editor pushed while this command was starting. Retry to merge the new release."
            )
        with TemporaryDirectory(prefix="kbforge-merge-") as temporary:
            work = Path(temporary)
            local = work / "local"
            snapshot(repo, local)
            original = fingerprints(local)
            incoming = local
            renumbered = []
            if head:
                base, remote = (
                    source_at(location, state["base"]),
                    source_at(location, head),
                )
                # Validate remote trees before inspecting their registry or using them as merge inputs.
                fingerprints(base)
                fingerprints(remote)
                renumbered = renumber_new_collisions(
                    local, registry_at(base), registry_at(remote)
                )
                incoming = work / "merged"
                merge_source(base, local, remote, incoming)

            refresh = fingerprints(incoming) != original

            def save_source(release):
                sources = location / "source"
                sources.mkdir(exist_ok=True)
                with TemporaryDirectory(dir=sources, prefix=".stage-") as staging:
                    prepared = Path(staging) / "collection"
                    prepared.mkdir()
                    copy_files(incoming, prepared, fingerprints(incoming))
                    prepared.rename(sources / release)

            target, release, changes = publish_to(
                Repository(incoming),
                location / "site",
                include_pdfs=include_pdfs,
                apply=apply,
                save_source=save_source,
            )
            if release:
                write_json(checkout, {"base": release, "refresh_required": refresh})
            return target, release, changes, renumbered, refresh

    if not apply:
        return prepare_and_publish()
    location.mkdir(exist_ok=True)
    lock = location / ".push.lock"
    lock.mkdir()
    try:
        return prepare_and_publish()
    finally:
        lock.rmdir()
