"""Shared Tomba2Edit artwork, resolved relative to source or the frozen bundle."""
from pathlib import Path
import sys
from PyQt6.QtGui import QIcon

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
FILES = {
    "app": "tomba/tomba1.ico", "disc": "graphics/disc.png",
    "WFM": "graphics/quill.png", "SPR": "graphics/fruit.png",
    "WPP": "tomba/tomba1.png", "WMD": "graphics/block.png",
    "GRPX": "tomba/123.png", "WHM": "graphics/molecule.png",
    "CLM": "graphics/molecule.png", "CLUT": "tomba/44.png", "APD": "graphics/map.png",
    "SEQ": "graphics/cassette.png", "WVD": "graphics/cassette.png",
    "STR": "graphics/clapperboard.png", "INS": "graphics/report.png",
    "GAM": "graphics/book-brown.png", "LDAR": "graphics/map.png",
    "FOUR": "graphics/border-all.png", "Unknown": "graphics/report.png",
    "LEVEL": "tomba/79.png",
}
# Stock PlayStation files and other games' archives, under the nearest
# picture there is.
for kinds, like in ((("TIM",), "GRPX"), (("TMD",), "WMD"), (("MOV",), "STR"),
                    (("XA", "XAX", "VH", "VB", "VA", "VAB", "MID", "DA"), "SEQ"),
                    (("LPK", "APK", "PAK", "LVL", "RAQ", "FAR", "DAT"), "GAM")):
    for kind in kinds:
        FILES[kind] = FILES[like]
_cache = {}


def icon(kind):
    kind = kind if kind in FILES else "Unknown"
    if kind not in _cache:
        _cache[kind] = QIcon(str(ROOT / "icons" / FILES[kind]))
    return _cache[kind]
