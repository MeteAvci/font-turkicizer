# Developed by: Mete Avcı
# Core glyph engine hardened with native-first preservation and safe contour replay.
import math
from typing import Dict, Iterable, Optional, Tuple, List, Any

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.pens.recordingPen import RecordingPen, DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import ControlBoundsPen


Bounds = Tuple[float, float, float, float]


class TurkicizerCore:
    """
    Native-first Turkish glyph injector.

    Rules:
    1. If the font already contains a real native glyph for a target Unicode,
       keep it and only guarantee cmap mapping.
    2. If the font contains a matching unencoded glyph by common names
       (Idotaccent, Gbreve, uni0130, etc.), map it and keep it.
    3. Generate only missing glyphs.
    4. Never use spacing punctuation such as asciicircum as a diacritic accent.
       If real mark glyphs are absent, draw controlled fallback marks.
    5. When replaying decorative/open contours into TTGlyphPen, force-close
       open contours so demo/handwritten fonts do not crash with PenError.
    """

    TARGETS = [
        ("Ccedilla", 0x00C7, "C", "cedilla", ["Ccedilla", "uni00C7"]),
        ("ccedilla", 0x00E7, "c", "cedilla", ["ccedilla", "uni00E7"]),
        ("Gbreve", 0x011E, "G", "breve", ["Gbreve", "uni011E"]),
        ("gbreve", 0x011F, "g", "breve", ["gbreve", "uni011F"]),
        ("Idotaccent", 0x0130, "I", "dotaccent", ["Idotaccent", "I.dot", "uni0130"]),
        ("idotless", 0x0131, "i", None, ["idotless", "dotlessi", "uni0131"]),
        ("Scedilla", 0x015E, "S", "cedilla", ["Scedilla", "uni015E"]),
        ("scedilla", 0x015F, "s", "cedilla", ["scedilla", "uni015F"]),
        ("Odieresis", 0x00D6, "O", "dieresis", ["Odieresis", "uni00D6"]),
        ("odieresis", 0x00F6, "o", "dieresis", ["odieresis", "uni00F6"]),
        ("Udieresis", 0x00DC, "U", "dieresis", ["Udieresis", "uni00DC"]),
        ("udieresis", 0x00FC, "u", "dieresis", ["udieresis", "uni00FC"]),
        ("Lira", 0x20BA, "L", None, ["uni20BA", "Lira", "TurkishLira", "liraTurkish", "lira"]),
        ("Acircumflex", 0x00C2, "A", "circumflex", ["Acircumflex", "uni00C2"]),
        ("acircumflex", 0x00E2, "a", "circumflex", ["acircumflex", "uni00E2"]),
        ("Icircumflex", 0x00CE, "I", "circumflex", ["Icircumflex", "uni00CE"]),
        ("icircumflex", 0x00EE, "i", "circumflex", ["icircumflex", "uni00EE"]),
        ("Ucircumflex", 0x00DB, "U", "circumflex", ["Ucircumflex", "uni00DB"]),
        ("ucircumflex", 0x00FB, "u", "circumflex", ["ucircumflex", "uni00FB"]),
        ("Ocircumflex", 0x00D4, "O", "circumflex", ["Ocircumflex", "uni00D4"]),
        ("ocircumflex", 0x00F4, "o", "circumflex", ["ocircumflex", "uni00F4"]),
        ("Ecircumflex", 0x00CA, "E", "circumflex", ["Ecircumflex", "uni00CA"]),
        ("ecircumflex", 0x00EA, "e", "circumflex", ["ecircumflex", "uni00EA"]),
    ]

    BASE_UNICODES = {
        "A": 0x0041, "a": 0x0061, "C": 0x0043, "c": 0x0063,
        "E": 0x0045, "e": 0x0065, "G": 0x0047, "g": 0x0067,
        "I": 0x0049, "i": 0x0069, "L": 0x004C,
        "O": 0x004F, "o": 0x006F, "S": 0x0053, "s": 0x0073,
        "U": 0x0055, "u": 0x0075,
    }

    ACCENT_CANDIDATES = {
        "cedilla": ["cedilla", "cedillacomb", "uni0327"],
        "breve": ["breve", "brevecomb", "uni0306"],
        "dotaccent": ["dotaccent", "dotaccentcomb", "uni0307"],
        "dieresis": ["dieresis", "dieresiscomb", "uni0308"],
        "circumflex": ["circumflex", "circumflexcomb", "uni0302"],
    }

    CAP_ACCENT_CANDIDATES = {
        "cedilla": ["cedilla", "cedillacomb", "uni0327"],
        "breve": ["breve.cap", "brevecap", "Breve", "breve", "brevecomb", "uni0306"],
        "dotaccent": ["dotaccent.cap", "dotaccentcap", "Dotaccent", "dotaccent", "dotaccentcomb", "uni0307"],
        "dieresis": ["dieresis.cap", "dieresiscap", "Dieresis", "dieresis", "dieresiscomb", "uni0308"],
        "circumflex": ["circumflex.cap", "circumflexcap", "Circumflex", "circumflex", "circumflexcomb", "uni0302"],
    }

    # These are spacing punctuation, not marks.  Using them as accents causes
    # chunky, detached, badly placed ^ marks in decorative fonts.
    BAD_ACCENT_SUBSTITUTES = {"asciicircum", "grave", "acute", "asciitilde", "tilde", "macron"}

    def inject_turkish_glyphs(self, font: TTFont, log=None) -> None:
        logger = log or (lambda *_: None)
        is_cff = "CFF " in font

        for glyph_name, unicode_val, base_key, accent_key, preferred_names in self.TARGETS:
            existing = self.find_existing_target_glyph(font, unicode_val, preferred_names)
            if existing:
                self.map_unicode(font, existing, unicode_val)
                logger(f"[=] Keeping native U+{unicode_val:04X} -> {existing}")
                continue

            base_name = self.get_base_glyph_name(font, base_key)
            if not base_name:
                logger(f"[!] Missing base '{base_key}' for U+{unicode_val:04X}; skipped")
                continue

            try:
                logger(f"[+] Creating missing U+{unicode_val:04X} as {glyph_name}")
                if is_cff:
                    self.add_cff_glyph(font, glyph_name, unicode_val, base_name, accent_key)
                else:
                    self.add_glyf_glyph(font, glyph_name, unicode_val, base_name, accent_key)
            except Exception as exc:
                logger(f"[!] Could not create U+{unicode_val:04X} ({glyph_name}): {exc}")

    # ------------------------------------------------------------------
    # Discovery / native preservation
    # ------------------------------------------------------------------

    def unicode_cmap(self, font: TTFont) -> Dict[int, str]:
        cmap: Dict[int, str] = {}
        if "cmap" not in font:
            return cmap
        for table in font["cmap"].tables:
            if table.isUnicode():
                cmap.update(table.cmap)
        return cmap

    def get_base_glyph_name(self, font: TTFont, base_key: str) -> Optional[str]:
        cmap = self.unicode_cmap(font)
        name = cmap.get(self.BASE_UNICODES.get(base_key, -1))
        if name and name in font.getGlyphSet():
            return name
        if base_key in font.getGlyphSet():
            return base_key
        return None

    def glyph_has_ink(self, font: TTFont, glyph_name: str) -> bool:
        if not glyph_name or glyph_name == ".notdef":
            return False
        glyph_set = font.getGlyphSet()
        if glyph_name not in glyph_set:
            return False
        return self.get_glyph_bounds(glyph_set, glyph_name) != (0, 0, 0, 0)

    def find_existing_target_glyph(
        self,
        font: TTFont,
        unicode_val: int,
        preferred_names: Iterable[str],
    ) -> Optional[str]:
        cmap = self.unicode_cmap(font)
        mapped = cmap.get(unicode_val)
        if mapped and self.glyph_has_ink(font, mapped):
            return mapped

        glyph_set = font.getGlyphSet()
        for name in preferred_names:
            if name in glyph_set and self.glyph_has_ink(font, name):
                return name

        return None

    def find_accent_name(self, font: TTFont, accent_key: str, uppercase: bool) -> Optional[str]:
        glyph_set = font.getGlyphSet()
        candidates: List[str] = []
        if uppercase:
            candidates.extend(self.CAP_ACCENT_CANDIDATES.get(accent_key, []))
        candidates.extend(self.ACCENT_CANDIDATES.get(accent_key, []))

        for name in candidates:
            if name in self.BAD_ACCENT_SUBSTITUTES:
                continue
            if name in glyph_set and self.glyph_has_ink(font, name):
                return name
        return None

    # ------------------------------------------------------------------
    # Contour and geometry helpers
    # ------------------------------------------------------------------

    def get_glyph_bounds(self, glyph_set, name: str) -> Bounds:
        try:
            pen = ControlBoundsPen(glyph_set)
            glyph_set[name].draw(pen)
            return pen.bounds if pen.bounds else (0, 0, 0, 0)
        except Exception:
            return (0, 0, 0, 0)

    def italic_slant(self, font: TTFont) -> float:
        angle = font["post"].italicAngle if "post" in font else 0
        return math.tan(math.radians(-angle))

    def replay_safely(self, recording: RecordingPen, target_pen) -> None:
        """
        Replay a RecordingPen stream and force-close open contours.

        TTGlyphPen rejects open contours.  Decorative/demo fonts often contain
        them.  For generated composite glyphs we prefer a valid closed outline
        over crashing the whole conversion.
        """
        contour_open = False

        for cmd, args in recording.value:
            if cmd == "moveTo":
                if contour_open:
                    target_pen.closePath()
                target_pen.moveTo(*args)
                contour_open = True
            elif cmd == "lineTo":
                target_pen.lineTo(*args)
            elif cmd == "curveTo":
                target_pen.curveTo(*args)
            elif cmd == "qCurveTo":
                target_pen.qCurveTo(*args)
            elif cmd == "closePath":
                if contour_open:
                    target_pen.closePath()
                contour_open = False
            elif cmd == "endPath":
                if contour_open:
                    target_pen.closePath()
                contour_open = False
            elif cmd == "addComponent":
                if contour_open:
                    target_pen.closePath()
                    contour_open = False
                target_pen.addComponent(*args)

        if contour_open:
            target_pen.closePath()

    def split_contours(self, glyph_set, glyph_name: str):
        rec = DecomposingRecordingPen(glyph_set)
        glyph_set[glyph_name].draw(rec)

        contours = []
        current = []
        for cmd, args in rec.value:
            if cmd == "moveTo" and current:
                contours.append(current)
                current = []
            current.append((cmd, args))
            if cmd in ("closePath", "endPath"):
                contours.append(current)
                current = []
        if current:
            contours.append(current)
        return contours

    def replay_without_i_dot(self, glyph_set, base_name: str, out_pen) -> None:
        contours = self.split_contours(glyph_set, base_name)
        if len(contours) <= 1:
            rec = DecomposingRecordingPen(glyph_set)
            glyph_set[base_name].draw(rec)
            self.replay_safely(rec, out_pen)
            return

        dot_idx = -1
        max_y = -10**9
        for idx, contour in enumerate(contours):
            cbp = ControlBoundsPen(glyph_set)
            rec = RecordingPen()
            rec.value = contour
            try:
                rec.replay(cbp)
            except Exception:
                continue
            if cbp.bounds and cbp.bounds[3] > max_y:
                max_y = cbp.bounds[3]
                dot_idx = idx

        filtered = RecordingPen()
        for idx, contour in enumerate(contours):
            if idx != dot_idx:
                filtered.value.extend(contour)
        self.replay_safely(filtered, out_pen)

    def get_dotless_i_bounds(self, glyph_set, base_name: str) -> Bounds:
        """Return bounds of lowercase i after removing its top dot contour."""
        contours = self.split_contours(glyph_set, base_name)
        if len(contours) <= 1:
            return self.get_glyph_bounds(glyph_set, base_name)

        dot_idx = -1
        max_y = -10**9
        contour_bounds = []
        for idx, contour in enumerate(contours):
            cbp = ControlBoundsPen(glyph_set)
            rec = RecordingPen()
            rec.value = contour
            try:
                rec.replay(cbp)
            except Exception:
                contour_bounds.append(None)
                continue
            contour_bounds.append(cbp.bounds)
            if cbp.bounds and cbp.bounds[3] > max_y:
                max_y = cbp.bounds[3]
                dot_idx = idx

        filtered = RecordingPen()
        for idx, contour in enumerate(contours):
            if idx != dot_idx:
                filtered.value.extend(contour)

        cbp = ControlBoundsPen(glyph_set)
        try:
            self.replay_safely(filtered, cbp)
            if cbp.bounds:
                return cbp.bounds
        except Exception:
            pass

        return self.get_glyph_bounds(glyph_set, base_name)

    def optical_top_center(self, glyph_set, base_name: str, slant: float) -> float:
        bounds = self.get_glyph_bounds(glyph_set, base_name)
        x_min, y_min, x_max, y_max = bounds
        if bounds == (0, 0, 0, 0):
            return 0.0

        rec = DecomposingRecordingPen(glyph_set)
        glyph_set[base_name].draw(rec)

        band_height = max(18, (y_max - y_min) * 0.14)
        threshold = y_max - band_height
        xs = []

        for cmd, args in rec.value:
            if not args:
                continue
            points = [a for a in args if isinstance(a, tuple) and len(a) >= 2]
            for x, y in points:
                if y >= threshold:
                    xs.append(x - slant * y)

        if not xs:
            return ((x_min + x_max) / 2.0) - slant * y_max
        return (min(xs) + max(xs)) / 2.0

    def base_stroke_estimate(self, glyph_set, base_name: str) -> float:
        x_min, y_min, x_max, y_max = self.get_glyph_bounds(glyph_set, base_name)
        height = max(1, y_max - y_min)
        width = max(1, x_max - x_min)
        return max(18, min(width, height) * 0.08)

    def accent_transform(self, font: TTFont, base_name: str, accent_name: str, accent_key: str, use_dotless_i: bool = False) -> Tuple[float, float, float, float]:
        glyph_set = font.getGlyphSet()
        if use_dotless_i:
            b_xmin, b_ymin, b_xmax, b_ymax = self.get_dotless_i_bounds(glyph_set, base_name)
        else:
            b_xmin, b_ymin, b_xmax, b_ymax = self.get_glyph_bounds(glyph_set, base_name)
        a_xmin, a_ymin, a_xmax, a_ymax = self.get_glyph_bounds(glyph_set, accent_name)

        uppercase = base_name[:1].isupper()
        slant = self.italic_slant(font)
        scale = 1.0

        if accent_key == "cedilla":
            target_y = b_ymin - max(12, (b_ymax - b_ymin) * 0.035)
            base_center = ((b_xmin + b_xmax) / 2.0) - slant * b_ymin
            target_x = base_center + slant * target_y
            dx = target_x - ((a_xmin + a_xmax) / 2.0)
            dy = target_y - a_ymax
            return scale, 0.0, dx, dy

        gap = max(22, (b_ymax - b_ymin) * (0.055 if uppercase else 0.05))
        target_y = b_ymax + gap
        if use_dotless_i:
            top_center = ((b_xmin + b_xmax) / 2.0) - slant * b_ymax
        else:
            top_center = self.optical_top_center(glyph_set, base_name, slant)
        target_x = top_center + slant * target_y
        dx = target_x - ((a_xmin + a_xmax) / 2.0)
        dy = target_y - a_ymin
        return scale, 0.0, dx, dy

    # ------------------------------------------------------------------
    # Fallback marks for fonts with no real accent glyphs
    # ------------------------------------------------------------------


    def pick_fallback_asset(self, font: TTFont, accent_key: str) -> Optional[str]:
        """
        Pick a style-compatible glyph from the font for a missing accent.

        These are *not* considered real accents in native-preservation logic, but
        when a font lacks true accent glyphs they are often better stylistic
        raw material than generic vector drawings.  Dacomment-style demo fonts
        usually have period/comma/asciicircum in the same hand.
        """
        glyph_set = font.getGlyphSet()
        candidates = {
            "dotaccent": ["period", "bullet", "asterisk"],
            "dieresis": ["period", "bullet", "asterisk"],
            "cedilla": ["comma", "quotesinglbase", "semicolon"],
            "circumflex": ["asciicircum"],
        }.get(accent_key, [])
        for name in candidates:
            if name in glyph_set and self.get_glyph_bounds(glyph_set, name) != (0, 0, 0, 0):
                return name
        return None

    def draw_transformed_glyph(
        self,
        pen,
        font: TTFont,
        glyph_name: str,
        target_center_x: float,
        target_bottom_y: float,
        target_width: Optional[float] = None,
        target_height: Optional[float] = None,
        center_y: bool = False,
    ) -> None:
        glyph_set = font.getGlyphSet()
        g_xmin, g_ymin, g_xmax, g_ymax = self.get_glyph_bounds(glyph_set, glyph_name)
        g_w = max(1, g_xmax - g_xmin)
        g_h = max(1, g_ymax - g_ymin)

        if target_width and target_height:
            scale = min(target_width / g_w, target_height / g_h)
        elif target_width:
            scale = target_width / g_w
        elif target_height:
            scale = target_height / g_h
        else:
            scale = 1.0

        x_center = (g_xmin + g_xmax) / 2.0
        if center_y and target_height:
            y_anchor = (g_ymin + g_ymax) / 2.0
            dy = target_bottom_y + target_height / 2.0 - y_anchor * scale
        else:
            dy = target_bottom_y - g_ymin * scale

        dx = target_center_x - x_center * scale
        rec = DecomposingRecordingPen(glyph_set)
        glyph_set[glyph_name].draw(rec)
        self.replay_safely(rec, TransformPen(pen, (scale, 0, 0, scale, dx, dy)))

    def draw_fallback_accent(self, pen, font: TTFont, base_name: str, accent_key: str, use_dotless_i: bool = False) -> None:
        glyph_set = font.getGlyphSet()
        if use_dotless_i:
            b_xmin, b_ymin, b_xmax, b_ymax = self.get_dotless_i_bounds(glyph_set, base_name)
        else:
            b_xmin, b_ymin, b_xmax, b_ymax = self.get_glyph_bounds(glyph_set, base_name)
        height = max(1, b_ymax - b_ymin)
        width = max(1, b_xmax - b_xmin)
        uppercase = base_name[:1].isupper()
        slant = self.italic_slant(font)
        stroke = self.base_stroke_estimate(glyph_set, base_name)

        # Bottom marks: prefer the font's own comma, because decorative fonts
        # often have a strong handwritten comma that looks much better than a
        # generic tiny hook.
        if accent_key == "cedilla":
            target_y = b_ymin - max(10, height * 0.025)
            center_deslanted = ((b_xmin + b_xmax) / 2.0) - slant * b_ymin
            x = center_deslanted + slant * target_y

            asset = self.pick_fallback_asset(font, "cedilla")
            if asset:
                target_w = max(width * 0.22, stroke * 2.8, 74)
                target_h = max(height * 0.20, stroke * 4.2, 100)
                self.draw_transformed_glyph(
                    pen, font, asset,
                    target_center_x=x,
                    target_bottom_y=target_y - target_h * 0.92,
                    target_width=target_w,
                    target_height=target_h,
                )
                return

            s = max(stroke * 2.35, width * 0.18, 64)
            pen.moveTo((x + s * 0.20, target_y))
            pen.curveTo((x - s * 0.45, target_y - s * 0.20), (x + s * 0.05, target_y - s * 0.85), (x - s * 0.30, target_y - s * 1.24))
            pen.curveTo((x - s * 0.08, target_y - s * 1.46), (x + s * 0.58, target_y - s * 1.20), (x + s * 0.48, target_y - s * 0.74))
            pen.lineTo((x + s * 0.12, target_y - s * 0.66))
            pen.curveTo((x + s * 0.12, target_y - s * 0.92), (x - s * 0.18, target_y - s * 0.94), (x - s * 0.14, target_y - s * 1.07))
            pen.curveTo((x + s * 0.28, target_y - s * 0.72), (x - s * 0.30, target_y - s * 0.26), (x + s * 0.02, target_y))
            pen.closePath()
            return

        # Top marks.  Use an optical anchor on the top ink band, then draw
        # either a style-compatible font asset or a thicker procedural fallback.
        gap = max(18, height * (0.045 if uppercase else 0.040))
        y0 = b_ymax + gap
        if use_dotless_i:
            center_deslanted = ((b_xmin + b_xmax) / 2.0) - slant * b_ymax
        else:
            center_deslanted = self.optical_top_center(glyph_set, base_name, slant)
        x = center_deslanted + slant * y0

        if accent_key == "dotaccent":
            asset = self.pick_fallback_asset(font, "dotaccent")
            target_w = max(width * 0.22, stroke * 2.5, 58)
            target_h = max(height * 0.14, stroke * 2.6, 58)
            if asset:
                self.draw_transformed_glyph(
                    pen, font, asset,
                    target_center_x=x,
                    target_bottom_y=y0,
                    target_width=target_w,
                    target_height=target_h,
                )
            else:
                r = max(stroke * 0.9, width * 0.070, 24)
                self.draw_circle(pen, x + slant * r, y0 + r, r)
            return

        if accent_key == "dieresis":
            asset = self.pick_fallback_asset(font, "dieresis")
            target_w = max(width * 0.16, stroke * 2.0, 42)
            target_h = max(height * 0.12, stroke * 2.2, 46)
            spread = max(width * 0.27, target_w * 2.2, 88)
            if asset:
                self.draw_transformed_glyph(pen, font, asset, x - spread / 2, y0, target_w, target_h)
                self.draw_transformed_glyph(pen, font, asset, x + spread / 2, y0, target_w, target_h)
            else:
                r = max(stroke * 0.78, width * 0.055, 22)
                self.draw_circle(pen, x - spread / 2 + slant * r, y0 + r, r)
                self.draw_circle(pen, x + spread / 2 + slant * r, y0 + r, r)
            return

        if accent_key == "circumflex":
            asset = self.pick_fallback_asset(font, "circumflex")
            target_w = max(width * (0.68 if width < 340 else 0.42), stroke * 5.6, 135)
            target_w = min(target_w, max(width * 0.92, 180))
            target_h = max(height * 0.18, stroke * 3.4, 82)
            if asset:
                self.draw_transformed_glyph(
                    pen, font, asset,
                    target_center_x=x,
                    target_bottom_y=y0,
                    target_width=target_w,
                    target_height=target_h,
                )
            else:
                w = target_w
                h = target_h
                thickness = max(stroke * 1.05, 24)
                pen.moveTo((x - w / 2, y0))
                pen.lineTo((x, y0 + h))
                pen.lineTo((x + w / 2, y0))
                pen.lineTo((x + w / 2 - thickness, y0))
                pen.lineTo((x, y0 + h - thickness * 0.95))
                pen.lineTo((x - w / 2 + thickness, y0))
                pen.closePath()
            return

        if accent_key == "breve":
            # Procedural breve: make it deliberately visible.  The previous
            # version was technically correct but too tiny on marker/script fonts.
            w = max(width * 0.48, stroke * 5.8, 135)
            w = min(w, max(width * 0.86, 180))
            h = max(stroke * 2.2, height * 0.12, 58)
            thickness = max(stroke * 0.95, 24)
            y = y0 + h
            pen.moveTo((x - w / 2, y))
            pen.curveTo((x - w * 0.39, y - h), (x - w * 0.18, y - h - thickness), (x, y - h - thickness))
            pen.curveTo((x + w * 0.18, y - h - thickness), (x + w * 0.39, y - h), (x + w / 2, y))
            pen.lineTo((x + w / 2 - thickness, y))
            pen.curveTo((x + w * 0.28, y - h * 0.50), (x + w * 0.13, y - h * 0.62), (x, y - h * 0.62))
            pen.curveTo((x - w * 0.13, y - h * 0.62), (x - w * 0.28, y - h * 0.50), (x - w / 2 + thickness, y))
            pen.closePath()
            return

    def draw_circle(self, pen, cx: float, cy: float, r: float) -> None:
        k = 0.5522847498
        pen.moveTo((cx + r, cy))
        pen.curveTo((cx + r, cy + k * r), (cx + k * r, cy + r), (cx, cy + r))
        pen.curveTo((cx - k * r, cy + r), (cx - r, cy + k * r), (cx - r, cy))
        pen.curveTo((cx - r, cy - k * r), (cx - k * r, cy - r), (cx, cy - r))
        pen.curveTo((cx + k * r, cy - r), (cx + r, cy - k * r), (cx + r, cy))
        pen.closePath()

    # ------------------------------------------------------------------
    # glyf / TrueType generation
    # ------------------------------------------------------------------

    def add_glyf_glyph(self, font: TTFont, name: str, unicode_val: int, base_name: str, accent_key: Optional[str]) -> None:
        glyph_set = font.getGlyphSet()
        glyf = font["glyf"]
        hmtx = font["hmtx"]

        tt_pen = TTGlyphPen(glyph_set)

        if name == "idotless":
            self.replay_without_i_dot(glyph_set, base_name, tt_pen)
        elif name == "Lira":
            is_bold = bool(font["OS/2"].fsSelection & (1 << 5)) if "OS/2" in font else bool(font["head"].macStyle & 1)
            is_italic = bool(font["OS/2"].fsSelection & 1) if "OS/2" in font else bool(font["head"].macStyle & 2)
            self.draw_lira(tt_pen, font, is_bold, is_italic)
        elif accent_key:
            use_dotless_i = name == "icircumflex"
            if use_dotless_i:
                # Lowercase î must be built on dotless ı, not dotted i.
                self.replay_without_i_dot(glyph_set, base_name, tt_pen)
            else:
                base_rec = DecomposingRecordingPen(glyph_set)
                glyph_set[base_name].draw(base_rec)
                self.replay_safely(base_rec, tt_pen)

            uppercase = base_name[:1].isupper()
            accent_name = self.find_accent_name(font, accent_key, uppercase)

            if accent_name:
                sx, shy, dx, dy = self.accent_transform(font, base_name, accent_name, accent_key, use_dotless_i=use_dotless_i)
                acc_rec = DecomposingRecordingPen(glyph_set)
                glyph_set[accent_name].draw(acc_rec)
                trans = TransformPen(tt_pen, (sx, 0, shy, sx, dx, dy))
                self.replay_safely(acc_rec, trans)
            else:
                self.draw_fallback_accent(tt_pen, font, base_name, accent_key, use_dotless_i=use_dotless_i)
        else:
            return

        new_glyph = tt_pen.glyph()
        if hasattr(new_glyph, "flags"):
            new_glyph.flags = [int(flag) & 0x7F for flag in new_glyph.flags]

        glyf.glyphs[name] = new_glyph
        try:
            new_glyph.recalcBounds(glyf)
        except Exception:
            pass

        if name not in font.getGlyphOrder():
            order = font.getGlyphOrder()
            order.append(name)
            font.setGlyphOrder(order)

        hmtx.metrics[name] = self.compute_glyf_metrics(font, name, base_name)
        self.map_unicode(font, name, unicode_val)

    def compute_glyf_metrics(self, font: TTFont, name: str, base_name: str) -> Tuple[int, int]:
        glyph_set = font.getGlyphSet()
        glyf = font["glyf"]
        hmtx = font["hmtx"]
        base_width, base_lsb = hmtx.metrics.get(base_name, (600, 0))

        if name == "Lira":
            try:
                return int(max(base_width * 1.35, glyf[name].xMax + 40)), 0
            except Exception:
                return int(base_width * 1.35), 0

        try:
            b_xmin, _, b_xmax, _ = self.get_glyph_bounds(glyph_set, base_name)
            bp = ControlBoundsPen(glyph_set)
            glyf[name].draw(bp, glyf)
            n_xmin, _, n_xmax, _ = bp.bounds if bp.bounds else (b_xmin, 0, b_xmax, 0)
            width = base_width + max(0, b_xmin - n_xmin) + max(0, n_xmax - b_xmax)
            return int(width), int(n_xmin)
        except Exception:
            return int(base_width), int(base_lsb)

    # ------------------------------------------------------------------
    # CFF generation
    # ------------------------------------------------------------------

    def add_cff_glyph(self, font: TTFont, name: str, unicode_val: int, base_name: str, accent_key: Optional[str]) -> None:
        top_dict = font["CFF "].cff.topDictIndex[0]
        charstrings = top_dict.CharStrings
        glyph_set = font.getGlyphSet()
        hmtx = font["hmtx"]
        private = getattr(top_dict, "Private", None)

        if getattr(charstrings, "charStringsAreIndexed", False):
            charstrings.charStrings = {key: charstrings[key] for key in charstrings.keys()}
            charstrings.charStringsAreIndexed = 0

        if name not in top_dict.charset:
            top_dict.charset.append(name)
        if name not in font.getGlyphOrder():
            order = font.getGlyphOrder()
            order.append(name)
            font.setGlyphOrder(order)

        width = hmtx.metrics.get(base_name, (600, 0))[0]
        if name == "Lira":
            is_bold = bool(font["OS/2"].fsSelection & (1 << 5)) if "OS/2" in font else bool(font["head"].macStyle & 1)
            target_width = int(width * (1.8 if is_bold else 1.4))
            t2_pen = T2CharStringPen(target_width, glyph_set)
            self.draw_lira(t2_pen, font, is_bold, bool(font["OS/2"].fsSelection & 1) if "OS/2" in font else False)
            charstrings[name] = t2_pen.getCharString(private=private)
            hmtx.metrics[name] = (target_width, 0)
            self.map_unicode(font, name, unicode_val)
            return

        t2_pen = T2CharStringPen(width, glyph_set)
        if name == "idotless":
            self.replay_without_i_dot(glyph_set, base_name, t2_pen)
        elif accent_key:
            use_dotless_i = name == "icircumflex"
            if use_dotless_i:
                # Lowercase î must be built on dotless ı, not dotted i.
                self.replay_without_i_dot(glyph_set, base_name, t2_pen)
            else:
                base_rec = DecomposingRecordingPen(glyph_set)
                glyph_set[base_name].draw(base_rec)
                self.replay_safely(base_rec, t2_pen)

            uppercase = base_name[:1].isupper()
            accent_name = self.find_accent_name(font, accent_key, uppercase)
            if accent_name:
                sx, shy, dx, dy = self.accent_transform(font, base_name, accent_name, accent_key, use_dotless_i=use_dotless_i)
                acc_rec = DecomposingRecordingPen(glyph_set)
                glyph_set[accent_name].draw(acc_rec)
                trans = TransformPen(t2_pen, (sx, 0, shy, sx, dx, dy))
                self.replay_safely(acc_rec, trans)
            else:
                self.draw_fallback_accent(t2_pen, font, base_name, accent_key, use_dotless_i=use_dotless_i)
        else:
            return

        charstrings[name] = t2_pen.getCharString(private=private)
        hmtx.metrics[name] = (self.compute_cff_width(font, name, base_name), 0)
        self.map_unicode(font, name, unicode_val)

    def compute_cff_width(self, font: TTFont, name: str, base_name: str) -> int:
        hmtx = font["hmtx"]
        base_width = hmtx.metrics.get(base_name, (600, 0))[0]
        try:
            glyph_set = font.getGlyphSet()
            b_xmin, _, b_xmax, _ = self.get_glyph_bounds(glyph_set, base_name)
            n_xmin, _, n_xmax, _ = self.get_glyph_bounds(glyph_set, name)
            return int(base_width + max(0, b_xmin - n_xmin) + max(0, n_xmax - b_xmax))
        except Exception:
            return int(base_width)

    # ------------------------------------------------------------------
    # Turkish lira fallback
    # ------------------------------------------------------------------

    def draw_lira(self, pen, font: TTFont, is_bold: bool, is_italic: bool) -> None:
        cap_height = 700
        try:
            if "OS/2" in font and getattr(font["OS/2"], "sCapHeight", 0) > 0:
                cap_height = font["OS/2"].sCapHeight
            else:
                glyph_set = font.getGlyphSet()
                for base in ("H", "I", "L"):
                    if base in glyph_set:
                        bounds = self.get_glyph_bounds(glyph_set, base)
                        if bounds != (0, 0, 0, 0):
                            cap_height = bounds[3]
                            break
        except Exception:
            pass

        slant = self.italic_slant(font) if is_italic else 0.0
        scale = cap_height / 455.0
        scale_x = 2.0 if is_bold else 1.5

        def p(x, y):
            nx = (x - 180) * scale * scale_x
            ny = (532 - y) * scale
            return (nx + slant * ny, ny)

        pen.moveTo(p(267, 77))
        pen.lineTo(p(267, 213))
        pen.lineTo(p(181, 244))
        pen.lineTo(p(181, 280))
        pen.lineTo(p(267, 249))
        pen.lineTo(p(267, 268))
        pen.lineTo(p(181, 299))
        pen.lineTo(p(181, 336))
        pen.lineTo(p(267, 305))
        pen.lineTo(p(267, 532))
        pen.curveTo(p(282, 533), p(297, 533), p(312, 532))
        pen.curveTo(p(320, 531), p(327, 530), p(334, 528))
        pen.curveTo(p(350, 524), p(366, 517), p(381, 510))
        pen.curveTo(p(450, 469), p(493, 394), p(493, 313))
        pen.lineTo(p(448, 313))
        pen.curveTo(p(448, 405), p(380, 482), p(289, 494))
        pen.lineTo(p(289, 297))
        pen.lineTo(p(429, 246))
        pen.lineTo(p(429, 210))
        pen.lineTo(p(289, 261))
        pen.lineTo(p(289, 242))
        pen.lineTo(p(429, 191))
        pen.lineTo(p(429, 155))
        pen.lineTo(p(289, 206))
        pen.lineTo(p(289, 87))
        pen.closePath()

    def map_unicode(self, font: TTFont, name: str, unicode_val: int) -> None:
        if "cmap" not in font:
            return
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[unicode_val] = name
