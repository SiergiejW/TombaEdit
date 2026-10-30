"""Native text palettes for the verified PrePre/Pure 9 executables and the Japanese retail disc."""
import hashlib
from PIL import Image
from psx.graphics import rgba

# The Japanese retail disc draws its text from the same two CLUT rows of VRAM as Pure 9 does (drawMessageGlyphs
# and spawnEventTitle write the same clut words), loaded from the area's sections.
RETAIL = 'Japanese retail'


def native_versions(project):
    """The WFM versions of the disc whose palette is in the VRAM of the sections, or () when it is none."""
    from game.builds import executable
    from formats.text.usage import PREPRE9_EXES
    found = executable(project)
    if found is None:
        return ()
    if hashlib.sha1(found.data).hexdigest() in PREPRE9_EXES:
        return (b'WFM1',)
    return (b'WFM2', b'WFM3') if found.build.name == RETAIL else ()


def attach(wfm, project, source, offset):
    if wfm.version not in native_versions(project):
        return
    assets = [a for a in project.by_source.get(source, ()) if a.kind == 'WFM' and a.offset == offset]
    if not assets:
        return
    title = all(im.height == 20 for im in wfm.glyphs)
    # spawnEventTitle writes CLUT 7D16 to its objects; drawMessageGlyphs
    # uses GetClut(0x160,0x1E3). The header's first short is texture word width,
    # not a palette ID. Title CLUT is loaded with the section, after group 0.
    y = 500 if title else 483
    cache = project.__dict__.setdefault('_native_text_palettes', {})
    for asset in assets:
        groups = project.ldars.get(asset.ldar, ())
        for group in ([asset.group] if asset.group else range(1, len(groups))):
            key = asset.ldar, group, y
            if key not in cache:
                try:
                    vram = project.vram(asset.ldar, group)
                except (OSError, ValueError, IndexError, KeyError):
                    continue  # An unavailable picture must not prevent text export.
                cache[key] = tuple(int(c) for c in vram[y, 352:368])
            words = cache[key]
            if not any(words):
                continue
            palette = [tuple(c) for c in rgba(words)]
            # Keep recognition keys stable: character assignments identify raw
            # glyph shapes/indices, independent of preview palette changes.
            for i, (image, indices) in enumerate(zip(wfm.glyphs, wfm.indices)):
                painted = Image.new('RGBA', image.size)
                painted.putdata([palette[n] for n in indices])
                wfm.glyphs[i] = painted
            wfm.palette_source = f'{asset.ldar} group {group}, CLUT ({352}, {y})'
            return
