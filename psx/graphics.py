"""PSX colour, VRAM texture pages and compound SPR frames."""
import struct
import numpy as np
from PIL import Image
from disc.reader import FormatError


def rgba(words):
    words = np.asarray(words, dtype=np.uint16)
    rgb = [((words >> shift) & 31).astype(np.uint8) for shift in (0, 5, 10)]
    return np.stack([((c << 3) | (c >> 2)) for c in rgb] +
                    [np.where(words == 0, 0, 255).astype(np.uint8)], axis=-1)


# Stand-in palette for texels whose own palette row is empty: a grey ramp,
# index 0 transparent as usual.
GREY_RAMP = np.array([0] + [level | level << 5 | level << 10 for level in range(3, 32, 2)], np.uint16)


def palette_missing(vram, clut, colours=16):
    """True when the palette row a CLUT word names holds nothing."""
    x, y = (clut & 63) * 16, (clut >> 6) & 511
    return not vram[y, x:x + colours].any()


def texture_page(vram, tpage, clut, palette=None):
    """One 256 x 256 texture page through a palette: the row `clut` names, or
    the sixteen colour words given in `palette`."""
    x, y = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
    depth = (tpage >> 7) & 3
    yy = (np.arange(256) + y) % 512
    if depth >= 2:
        # Depth 3 is reserved; the GPU reads it as 15-bit colour as well.
        words = vram[np.ix_(yy, (np.arange(256) + x) % 1024)]
        return Image.fromarray(rgba(words))
    per_word = 4 if depth == 0 else 2
    px = np.arange(256)
    words = vram[np.ix_(yy, (x + px // per_word) % 1024)]
    indices = (words >> ((px % per_word) * (4 if depth == 0 else 8))) & (15 if depth == 0 else 255)
    if palette is not None and depth == 0:
        return Image.fromarray(rgba(np.asarray(palette, np.uint16)[indices]))
    cx, cy = (clut & 63) * 16, (clut >> 6) & 511
    flat = vram.reshape(-1)
    palette = flat[(cy * 1024 + cx + np.arange(16 if depth == 0 else 256)) % flat.size]
    return Image.fromarray(rgba(palette[indices]))


def sprite_frames(data):
    if len(data) < 4:
        raise FormatError("SPR has no frame table")
    first = struct.unpack_from("<H", data, 2)[0]
    if not first or first % 4 or first > len(data):
        raise FormatError("Invalid SPR frame table")
    frames = []
    for pos in range(0, first, 4):
        count, offset = struct.unpack_from("<HH", data, pos)
        if count > 4096 or offset < first or offset + count * 16 > len(data):
            raise FormatError(f"SPR frame {pos // 4} extends outside asset")
        frames.append([struct.unpack_from("<BBHBBBBBBBBBBbb", data, offset + i * 16)
                       for i in range(count)])
    return frames


def sprite_texture_page(shard, page, vram, clut):
    """Decode a SPR virtual 4-bit page from the LDAR texture upload."""
    if shard is None:
        return texture_page(vram, page, clut)
    width, height, data = shard
    pages = width // 64
    index = page & 31
    if not pages or index >= pages or height < 256:
        return Image.new('RGBA', (256, 256))
    rows = np.frombuffer(data, dtype=np.uint8).reshape(height, width * 2)
    packed = rows[:256, index * 128:(index + 1) * 128]
    indices = np.empty((256, 256), dtype=np.uint8)
    indices[:, 0::2] = packed & 15
    indices[:, 1::2] = packed >> 4
    cx, cy = (clut & 63) * 16, (clut >> 6) & 511
    palette = vram.reshape(-1)[(cy * 1024 + cx + np.arange(16)) % vram.size]
    return Image.fromarray(rgba(palette[indices]))


def part_page(part, base=0):
    """Texture page word a part is drawn with once the object's base is added."""
    return ((part[5] | part[6] << 8) + base) & 0x1FF


def guess_page(frames, vram, preferred=()):
    """Texture page base for a bank nothing else identifies: the one under
    which a few frames show the most pixels. Pages where a texture upload of
    the bank's own load group begins are tried first; a bank's art usually
    starts there."""
    sample = [frame for frame in frames if frame][:12]

    def opaque(base):
        try:
            return sum(sum(render_sprite(frame, vram, tpage=base, grey_missing=True).getchannel('A').histogram()[1:])
                       for frame in sample)
        except FormatError:
            return -1
    for candidates in (list(dict.fromkeys(preferred)), range(32)):
        if sample and candidates:
            best = max(candidates, key=opaque)
            if opaque(best) > 0:
                return best
    return 0


def render_sprite(parts, vram, page_base=0, shard=None, tpage=None, clut=None, grey_missing=False):
    """Composite one frame. With `tpage` the parts are read from VRAM the way
    the game draws them: the value is added to each part's page word and
    `clut` replaces the part palette. Without it the older page guesses
    (`page_base`, or the section's texture upload in `shard`) are used."""
    if not parts:
        return Image.new("RGBA", (1, 1))
    left = min(p[13] for p in parts)
    top = min(p[14] for p in parts)
    right = max(p[13] + p[9] for p in parts)
    bottom = max(p[14] + p[10] for p in parts)
    image = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)))
    pages = {}
    for p in reversed(parts):
        sx, sy, part_clut, _, _, page, _, _, _, w, h, _, _, x, y = p
        palette = part_clut if clut is None else clut
        key = (page, p[6], palette)
        if key not in pages:
            if tpage is not None:
                # Art whose palette the game only supplies while running can
                # still be shown, in grey.
                stand_in = GREY_RAMP if grey_missing and palette_missing(vram, palette) else None
                pages[key] = texture_page(vram, part_page(p, tpage), palette, stand_in)
            elif shard:
                pages[key] = sprite_texture_page(shard, page, vram, palette)
            else:
                pages[key] = texture_page(vram, (page & ~31) | (((page & 31) + page_base) & 31), palette)
        tile = pages[key].crop((sx, sy, sx + w, sy + h))
        image.alpha_composite(tile, (x - left, y - top))
    return image
