"""Native text palettes for the verified PrePre/Pure 9 executables."""
import hashlib
from PIL import Image
from psx.graphics import rgba


def attach(wfm, project, source, offset):
    from game.builds import executable
    from formats.text.usage import PREPRE9_EXES
    if wfm.version != b'WFM1':
        return
    found = executable(project)
    if found is None or hashlib.sha1(found.data).hexdigest() not in PREPRE9_EXES:
        return
    assets = [a for a in project.by_source.get(source, ()) if a.kind == 'WFM' and a.offset == offset]
    if not assets:
        return
    title = all(im.height == 20 for im in wfm.glyphs)
    # spawnEventTitle writes CLUT 7D16 to its objects; drawMessageGlyphs
    # uses GetClut(160,1E3). The header's first short is texture word width,
    # not a palette ID. Title CLUT is loaded with the section, after group 0.
    y = 500 if title else 483
    cache = project.__dict__.setdefault('_native_text_palettes', {})
    for asset in assets:
        groups = project.ldars.get(asset.ldar, ())
        for group in ([asset.group] if asset.group else range(1, len(groups))):
            key = asset.ldar, group, y
            if key not in cache:
                vram = project.vram(asset.ldar, group)
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
