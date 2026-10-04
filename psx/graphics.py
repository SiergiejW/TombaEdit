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


def texture_page(vram, tpage, clut):
    x, y = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
    depth = (tpage >> 7) & 3
    yy = (np.arange(256) + y) % 512
    if depth == 2:
        words = vram[np.ix_(yy, (np.arange(256) + x) % 1024)]
        return Image.fromarray(rgba(words))
    if depth not in (0, 1):
        raise FormatError(f"Reserved texture depth in page {tpage:04X}")
    per_word = 4 if depth == 0 else 2
    px = np.arange(256)
    words = vram[np.ix_(yy, (x + px // per_word) % 1024)]
    indices = (words >> ((px % per_word) * (4 if depth == 0 else 8))) & (15 if depth == 0 else 255)
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


def render_sprite(parts, vram, page_base=0):
    if not parts:
        return Image.new("RGBA", (1, 1))
    left = min(p[13] for p in parts)
    top = min(p[14] for p in parts)
    right = max(p[13] + p[9] for p in parts)
    bottom = max(p[14] + p[10] for p in parts)
    image = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)))
    pages = {}
    for p in reversed(parts):
        sx, sy, clut, _, _, page, _, _, _, w, h, _, _, x, y = p
        # SPR pages are relative to the section's first texture shard.
        page = (page & ~31) | (((page & 31) + page_base) & 31)
        key = (page, clut)
        if key not in pages:
            pages[key] = texture_page(vram, page, clut)
        tile = pages[key].crop((sx, sy, sx + w, sy + h))
        image.alpha_composite(tile, (x - left, y - top))
    return image
