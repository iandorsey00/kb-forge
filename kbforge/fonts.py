"""Validate publication typography and describe local faces for the PDF and web renderers."""

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from .repository import LANGUAGE

FONT_SUFFIXES = {".ttf", ".ttc"}
FACE_WEIGHTS = {"regular": 400, "bold": 700, "italic": 400, "bold_italic": 700}
DEFAULT_WEIGHTS = {"body": 400, "heading": 700, "caption": 400}


def font_filename(value):
    if (
        not isinstance(value, str)
        or any(char in value for char in "/\\:")
        or any(ord(char) < 32 for char in value)
        or value != value.strip()
        or Path(value).suffix.lower() not in FONT_SUFFIXES
    ):
        raise ValueError("Use a .ttf or .ttc filename from the branding directory.")
    return value


def font_notices(settings):
    notices = settings.get("font_licenses", [])
    if not isinstance(notices, list) or any(
        not isinstance(name, str)
        or not name.lower().endswith(".txt")
        or any(char in name for char in "/\\:")
        or any(ord(char) < 32 for char in name)
        or name != name.strip()
        for name in notices
    ):
        raise ValueError("publishing.font_licenses must list .txt files from branding.")
    return notices


def code_font(repo):
    from .pdf import theme_asset

    name = repo.config.get("publishing", {}).get("code_font")
    if name is None:
        return None
    return theme_asset(repo, font_filename(name), {".ttf"})


def font_settings(settings):
    """Keep portable settings separate from machine-local paths and renderer state."""

    def family(value):
        if isinstance(value, str):
            value = {"regular": value}
        if (
            not isinstance(value, dict)
            or "regular" not in value
            or value.keys() - FACE_WEIGHTS.keys()
        ):
            raise ValueError(
                "A font family needs regular and may specify bold, italic, and bold_italic."
            )
        return {role: font_filename(name) for role, name in value.items()}

    primary = {}
    if "fonts" in settings:
        if not isinstance(settings["fonts"], dict):
            raise ValueError("publishing.fonts must be an object.")
        primary = family(settings["fonts"])
    elif settings.get("font"):
        primary = family(settings["font"])
    raw = settings.get("font_fallbacks", {})
    if (
        not isinstance(raw, dict)
        or any(key.lower() != "default" and not LANGUAGE.fullmatch(key) for key in raw)
        or len({key.lower() for key in raw}) != len(raw)
    ):
        raise ValueError(
            "publishing.font_fallbacks needs unique language tags or default."
        )
    fallback = {key.lower(): family(value) for key, value in raw.items()}
    weights = settings.get("font_weights", {})
    if (
        not isinstance(weights, dict)
        or weights.keys() - DEFAULT_WEIGHTS.keys()
        or any(
            type(weight) is not int or not 1 <= weight <= 1000
            for weight in weights.values()
        )
    ):
        raise ValueError(
            "publishing.font_weights accepts body, heading, and caption weights from 1 to 1000."
        )
    return primary, fallback, DEFAULT_WEIGHTS | weights


def publication_fonts(repo):
    from .pdf import theme_asset

    primary, fallback, weights = font_settings(repo.config.get("publishing", {}))

    def resolve(family):
        return {
            role: theme_asset(repo, name, FONT_SUFFIXES)
            for role, name in family.items()
        }

    return (
        resolve(primary),
        {tag: resolve(family) for tag, family in fallback.items()},
        weights,
    )


def default_cjk_paths():
    import os

    return (
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc",
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    )


def open_font(data):
    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise ValueError(
            "Install fontTools with python -m pip install -r requirements-pdf.txt."
        ) from error
    options = {"fontNumber": 0} if data.startswith(b"ttcf") else {}
    return TTFont(BytesIO(data), recalcTimestamp=False, **options)


@dataclass(frozen=True)
class FontInfo:
    axes: dict
    label: str


@lru_cache(maxsize=12)
def font_info(data):
    with open_font(data) as font:
        if "glyf" not in font:
            raise ValueError(
                "Use a TrueType-outline font. CFF and CFF2 outlines are unsupported."
            )
        axes = {}
        if "fvar" in font:
            axes = {
                axis.axisTag: (axis.minValue, axis.defaultValue, axis.maxValue)
                for axis in font["fvar"].axes
            }
        return FontInfo(axes, font["name"].getDebugName(6) or "DocumentFont")


def read_face(path):
    try:
        data = path.read_bytes()
        return data, font_info(data)
    except Exception as error:
        raise ValueError(f"Cannot use font {path.name}: {error}") from error


def angle(axes):
    if "slnt" not in axes:
        return 0
    low, _, high = axes["slnt"]
    return max(low, -12) if low < 0 else min(high, 12)


def italic_axis(axes):
    return ("ital" in axes and axes["ital"][0] <= 1 <= axes["ital"][2]) or bool(
        angle(axes)
    )


def fallback_tags(language, families):
    match = language.lower()
    tags = sorted(
        (
            tag
            for tag in families
            if tag != "default" and (match == tag or match.startswith(tag + "-"))
        ),
        key=len,
        reverse=True,
    )
    if "default" in families:
        tags.append("default")
    return tags + [tag for tag in families if tag not in tags]


def web_fonts(repo, url_for):
    """Generate CSS and map relative asset names to validated local font bytes."""
    primary, fallbacks, weights = publication_fonts(repo)
    rules = []
    assets = {}

    def face_rules(family, name):
        if not family:
            return False
        seen = set()
        for role in FACE_WEIGHTS:
            if role not in family:
                continue
            path = family[role]
            if path.suffix.lower() == ".ttc":
                continue
            data, info = read_face(path)
            axes = info.axes
            asset = f"{sha256(data).hexdigest()}.ttf"
            assets[asset] = data
            is_italic = "italic" in role
            styles = ["italic" if is_italic else "normal"]
            if role == "regular" and "italic" not in family and italic_axis(axes):
                if "ital" in axes and axes["ital"][0] <= 1 <= axes["ital"][2]:
                    styles.append("italic")
                else:
                    low, _, high = axes["slnt"]
                    styles.append(f"oblique {-high:g}deg {-low:g}deg")
            low, _, high = axes.get("wght", (FACE_WEIGHTS[role],) * 3)
            if "bold" in role:
                low = high = FACE_WEIGHTS[role]
            weight = f"{low:g} {high:g}" if low != high else f"{low:g}"
            for style in styles:
                key = (style, weight)
                if key not in seen:
                    seen.add(key)
                    rules.append(
                        f'@font-face{{font-family:"{name}";src:url("{url_for(asset)}") format("truetype");'
                        f"font-style:{style};font-weight:{weight};font-display:swap}}"
                    )
        return bool(seen)

    primary_name = (
        ['"KBForgeDocument"'] if face_rules(primary, "KBForgeDocument") else []
    )
    names = {}
    for number, (tag, family) in enumerate(fallbacks.items()):
        name = f"KBForgeFallback{number}"
        if face_rules(family, name):
            names[tag] = f'"{name}"'
    if mono := code_font(repo):
        face_rules({"regular": mono}, "KBForgeCode")
        rules.append(
            '.publication :is(pre,code){font-family:"KBForgeCode",monospace;font-weight:400}'
        )
    if not assets and weights == DEFAULT_WEIGHTS:
        return "", {}
    for tag in [None, *sorted((key for key in names if key != "default"), key=len)]:
        tags = fallback_tags(tag or "", names)
        stack = ", ".join(
            primary_name + [names[key] for key in tags] + ["system-ui", "sans-serif"]
        )
        selector = ".publication" if tag is None else f'.publication[lang|="{tag}" i]'
        rules.append(
            f"{selector}{{font-family:{stack};--document-weight:{weights['body']};"
            "font-weight:var(--document-weight);font-synthesis:none;font-optical-sizing:none}"
        )
    rules.extend(
        [
            f".publication :is(h1,h2,h3,h4,h5,h6){{--document-weight:{weights['heading']};font-weight:var(--document-weight)}}",
            f".publication figcaption{{--document-weight:{weights['caption']};font-weight:var(--document-weight)}}",
            ".publication strong{font-weight:max(700,var(--document-weight))}",
        ]
    )
    return "\n".join(rules), assets
