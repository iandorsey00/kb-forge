"""Instantiate and embed TrueType faces for a single PDF publication."""

from hashlib import sha256
from io import BytesIO
from itertools import groupby
import os
from pathlib import Path
import re
from threading import Lock
from xml.sax.saxutils import escape

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .fonts import (
    DEFAULT_WEIGHTS,
    FACE_WEIGHTS,
    angle,
    default_cjk_paths,
    fallback_tags,
    italic_axis,
    open_font,
    read_face,
)

FONT_LOCK = Lock()
CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\U00020000-\U000323af]")


def instance_coordinates(axes, weight, italic):
    coordinates = {tag: default for tag, (_, default, _) in axes.items()}
    if "wght" in axes:
        low, _, high = axes["wght"]
        coordinates["wght"] = max(low, min(weight, high))
    if "ital" in axes:
        low, default, high = axes["ital"]
        value = int(italic)
        coordinates["ital"] = value if low <= value <= high else default
    if "slnt" in axes:
        low, _, high = axes["slnt"]
        coordinates["slnt"] = (
            angle(axes)
            if italic and coordinates.get("ital") != 1
            else max(low, min(0, high))
        )
    return coordinates


def register_face(path, data, info, weight, italic):
    axes = info.axes
    coordinates = instance_coordinates(axes, weight, italic)
    digest = sha256(data + repr(sorted(coordinates.items())).encode()).hexdigest()[:24]
    label = re.sub(r"[^a-zA-Z0-9-]", "", info.label)[:32] or "DocumentFont"
    name = f"{label}-{digest}"
    with FONT_LOCK:
        if name not in pdfmetrics.getRegisteredFontNames():
            try:
                stream = BytesIO(data)
                if axes:
                    from fontTools.varLib.instancer import instantiateVariableFont

                    with open_font(data) as original:
                        instance = instantiateVariableFont(
                            original, coordinates, inplace=True
                        )
                        # ReportLab deduplicates by PostScript name. Distinct coordinates
                        # must register distinct faces even when the source name is shared.
                        names = instance["name"]
                        for record in [
                            record for record in names.names if record.nameID == 6
                        ]:
                            names.setName(
                                name,
                                6,
                                record.platformID,
                                record.platEncID,
                                record.langID,
                            )
                        names.setName(name, 6, 3, 1, 0x409)
                        stream = BytesIO()
                        instance.save(stream)
                        stream.seek(0)
                pdfmetrics.registerFont(TTFont(name, stream, asciiReadable=True))
            except Exception as error:
                raise ValueError(
                    f"Cannot embed PDF font {path.name}: {error}"
                ) from error
    return name


class DocumentFonts:
    def __init__(self, theme, language):
        self.primary, self.fallbacks, self.weights = theme.get(
            "typography", ({}, {}, DEFAULT_WEIGHTS)
        )
        if not self.primary and (configured := os.environ.get("KBFORGE_PDF_FONT")):
            self.primary = {"regular": Path(configured)}
        self.preferred_fallbacks = [
            self.fallbacks[tag] for tag in fallback_tags(language, self.fallbacks)
        ]
        self.sources = {}
        self.faces = {}
        self.matches = {}
        self.code_path = theme.get("code_font")
        self.system_cjk = next(
            (path for path in default_cjk_paths() if path.is_file()), None
        )

    def source(self, path):
        if path not in self.sources:
            self.sources[path] = read_face(path)
        return self.sources[path]

    def choose(self, family, weight, italic):
        upright = family["regular"]
        _, regular = self.source(upright)
        candidates = {}
        for role, path in family.items():
            if ("italic" in role) == italic:
                candidates[FACE_WEIGHTS[role]] = (path, role)
        if italic and 400 not in candidates and italic_axis(regular.axes):
            candidates[400] = (upright, "regular")
        if not candidates:
            return self.choose(family, weight, False)
        if weight in candidates and weight == 700:
            return candidates[weight][0]
        if 400 in candidates:
            path, _ = candidates[400]
            if "wght" in self.source(path)[1].axes:
                return path
        return min(
            candidates.items(), key=lambda pair: (abs(weight - pair[0]), pair[0])
        )[1][0]

    def face(self, family, weight, italic):
        path = self.choose(family, weight, italic)
        key = path, weight, italic
        if key not in self.faces:
            self.faces[key] = register_face(path, *self.source(path), weight, italic)
        return self.faces[key]

    def primary_face(self, weight, italic=False):
        if self.primary:
            return self.face(self.primary, weight, italic)
        if weight >= 600:
            return "Helvetica-BoldOblique" if italic else "Helvetica-Bold"
        return "Helvetica-Oblique" if italic else "Helvetica"

    def code_face(self):
        if self.code_path:
            return self.face({"regular": self.code_path}, 400, False)
        return "Courier"

    def match(self, character, weight, italic, *, code=False):
        key = character, weight, italic, code
        if key in self.matches:
            return self.matches[key]

        def covers(name):
            font = pdfmetrics.getFont(name)
            if character in "\n\t\r":
                return True
            if not font._dynamicFont:
                return character.encode("cp1252", errors="ignore") != b""
            return ord(character) in font.face.charToGlyph

        if code and covers(name := self.code_face()):
            self.matches[key] = name
            return name
        name = self.primary_face(weight, italic)
        if not covers(name):
            fallback = [*self.preferred_fallbacks]
            if self.system_cjk and CJK.fullmatch(character):
                fallback.append({"regular": self.system_cjk})
            for family in fallback:
                name = self.face(family, weight, italic)
                if covers(name):
                    break
            else:
                raise ValueError(
                    f"The PDF font lacks glyph {character!r} (U+{ord(character):04X}). "
                    "Choose a font family or publishing.font_fallbacks with coverage."
                )
        self.matches[key] = name
        return name

    def segments(self, text, weight, italic=False, *, code=False):
        for font, letters in groupby(
            text, lambda char: self.match(char, weight, italic, code=code)
        ):
            yield font, "".join(letters)

    def markup(self, text, weight, italic=False, *, code=False):
        return "".join(
            f'<font name="{font}">{escape(part).replace(chr(10), "<br/>")}</font>'
            for font, part in self.segments(text, weight, italic, code=code)
        )
