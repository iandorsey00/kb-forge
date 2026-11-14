"""Transfer collection appearance settings and their referenced assets."""

import json
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from .pdf import IMAGE_SUFFIXES, theme_asset
from .repository import read_mapping, write_json

SECTIONS = ("workspace", "branding", "publishing")
ASSETS = {
    "workspace": {"logo": IMAGE_SUFFIXES},
    "branding": {"logo": IMAGE_SUFFIXES},
    "publishing": {
        "cover_image": IMAGE_SUFFIXES,
        "header_image": IMAGE_SUFFIXES,
        "footer_image": IMAGE_SUFFIXES,
        "font": {".ttf", ".ttc"},
    },
}
MAX_BYTES = 64 * 1024 * 1024


def asset_names(settings):
    names = set()
    for section, fields in ASSETS.items():
        values = settings.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"Theme setting {section} must be an object.")
        for field, suffixes in fields.items():
            name = values.get(field)
            if name is None or name == "":
                continue
            if (
                not isinstance(name, str)
                or "/" in name
                or "\\" in name
                or ":" in name
                or name.endswith((" ", "."))
                or not any(name.lower().endswith(suffix) for suffix in suffixes)
            ):
                raise ValueError(f"Invalid theme asset filename for {section}.{field}.")
            names.add(name)
    return names


def export_theme(repo, destination):
    settings = {key: repo.config[key] for key in SECTIONS if key in repo.config}
    names = asset_names(settings)
    manifest = json.dumps(
        {"version": 1, "settings": settings}, ensure_ascii=False, indent=2
    )
    paths = [
        theme_asset(repo, name, IMAGE_SUFFIXES | {".ttf", ".ttc"})
        for name in sorted(names)
    ]
    if sum(path.stat().st_size for path in paths) + len(manifest.encode()) > MAX_BYTES:
        raise ValueError("Theme exceeds the 64 MiB limit.")
    with ZipFile(destination, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr("theme.json", manifest)
        for path in paths:
            archive.write(path, f"branding/{path.name}")


def import_theme(repo, source):
    try:
        with ZipFile(source) as archive:
            members = archive.namelist()
            if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
                raise ValueError("Theme exceeds the 64 MiB limit.")
            if "theme.json" not in members or len(members) != len(set(members)):
                raise ValueError(
                    "Expected a theme.json manifest and unique archive members."
                )
            bundle = read_mapping(archive.read("theme.json").decode("utf-8"))
            settings = bundle.get("settings")
            if bundle.get("version") != 1 or not isinstance(settings, dict):
                raise ValueError("Unsupported theme bundle.")
            if "branding" not in settings or settings.keys() - set(SECTIONS):
                raise ValueError(
                    "Expected collection branding and optional workspace and publishing settings."
                )
            names = asset_names(settings)
            if set(members) != {"theme.json", *(f"branding/{name}" for name in names)}:
                raise ValueError(
                    "Theme ZIP must contain exactly the assets listed in its settings."
                )
            assets = {name: archive.read(f"branding/{name}") for name in sorted(names)}
    except (BadZipFile, RuntimeError) as error:
        raise ValueError("Could not read theme ZIP.") from error

    repo.path("branding").mkdir(exist_ok=True)
    created = []
    config_path = repo.path("kbforge.yaml")
    for name, data in assets.items():
        target = repo.path("branding", name)
        if target.exists() and target.read_bytes() != data:
            raise ValueError(
                f"Conflicting branding asset: {name}. Use a new collection or rename the existing asset."
            )
    config = {key: value for key, value in repo.config.items() if key not in SECTIONS}
    config.update(settings)
    try:
        for name, data in assets.items():
            target = repo.path("branding", name)
            if not target.exists():
                with target.open("xb") as stream:
                    created.append(target)
                    stream.write(data)
        write_json(config_path, config)
    except OSError:
        for target in created:
            target.unlink(missing_ok=True)
        raise
