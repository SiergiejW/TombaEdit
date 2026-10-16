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


# The game keeps its palettes in the rows of VRAM from here down; above
# them a CLUT word names a place among the textures.
PALETTE_ROWS = 448


def palette_runtime(clut):
    """True when a CLUT word names a row among the textures: a slot the game
    writes a palette into while it runs, which holds texture pixels until
    then."""
    return (clut >> 6) & 511 < PALETTE_ROWS


def palette_missing(vram, clut, colours=16):
    """True when the palette a CLUT word names is not in this VRAM: its row
    holds nothing, or is a slot the game fills while it runs."""
    x, y = (clut & 63) * 16, (clut >> 6) & 511
    return palette_runtime(clut) or not vram[y, x:x + colours].any()


def texture_page(vram, tpage, clut, palette=None, flagged=None):
    """One 256 x 256 texture page through a palette: the row `clut` names, or
    the sixteen colour words given in `palette`.

    Bit 15 of a colour word marks it for blending: a semi-transparent
    primitive blends the texels that carry it and draws the rest solid.
    `flagged` keeps only the texels with the bit (True) or without it
    (False) and leaves the others clear."""
    def picture(words):
        if flagged is not None:
            words = np.where((words >> 15 == 1) == flagged, words, 0)
        return Image.fromarray(rgba(words))
    x, y = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
    depth = (tpage >> 7) & 3
    yy = (np.arange(256) + y) % 512
    if depth >= 2:
        # Depth 3 is reserved; the GPU reads it as 15-bit colour as well.
        words = vram[np.ix_(yy, (np.arange(256) + x) % 1024)]
        return picture(words)
    per_word = 4 if depth == 0 else 2
    px = np.arange(256)
    words = vram[np.ix_(yy, (x + px // per_word) % 1024)]
    indices = (words >> ((px % per_word) * (4 if depth == 0 else 8))) & (15 if depth == 0 else 255)
    if palette is not None and depth == 0:
        return Image.fromarray(rgba(np.asarray(palette, np.uint16)[indices]))
    cx, cy = (clut & 63) * 16, (clut >> 6) & 511
    flat = vram.reshape(-1)
    palette = flat[(cy * 1024 + cx + np.arange(16 if depth == 0 else 256)) % flat.size]
    return picture(palette[indices])


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


def render_sprite(parts, vram, page_base=0, shard=None, tpage=None, clut=None, grey_missing=False, blend=False,
                  texture_cache=None):
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
    def decoded(page, palette, stand_in=None, flagged=None):
        key = (id(vram), page, palette, stand_in is not None, flagged)
        if texture_cache is not None and key in texture_cache:
            return texture_cache[key]
        image = texture_page(vram, page, palette, stand_in, flagged)
        if texture_cache is not None:
            if len(texture_cache) >= 128:
                del texture_cache[next(iter(texture_cache))]
            texture_cache[key] = image
        return image
    for p in reversed(parts):
        sx, sy, part_clut, _, _, page, _, _, _, w, h, _, _, x, y = p
        palette = part_clut if clut is None else clut
        key = (page, p[6], palette)
        if key not in pages:
            if tpage is not None:
                # Art whose palette the game only supplies while running can
                # still be shown, in grey.
                stand_in = GREY_RAMP if grey_missing and palette_missing(vram, palette) else None
                pages[key] = decoded(part_page(p, tpage), palette, stand_in)
            elif shard:
                pages[key] = sprite_texture_page(shard, page, vram, palette)
            else:
                pages[key] = decoded((page & ~31) | (((page & 31) + page_base) & 31), palette)
        tile = sprite_part_image(pages[key], p)
        if blend and tpage is not None:
            marked = sprite_part_image(decoded(part_page(p, tpage), palette, flagged=True), p)
            composite_psx(image, tile, (x - left, y - top),
                          np.asarray(marked)[..., 3] != 0, part_page(p, tpage) >> 5 & 3)
        else:
            image.alpha_composite(tile, (x - left, y - top))
    return image


def composite_psx(image, tile, position, marked, mode):
    """GPU STP blending in five-bit channels against the current picture.

    Empty pixels of a transparent export use a black framebuffer. Additive
    and subtractive effects depend on the background in the running game.
    """
    x, y = position
    source = np.asarray(tile).copy()
    target = np.asarray(image.crop((x, y, x + tile.width, y + tile.height))).copy()
    back, front = target[..., :3].astype(np.int16) >> 3, source[..., :3].astype(np.int16) >> 3
    if mode == 0:
        rgb = (back >> 1) + (front >> 1)
    elif mode == 1:
        rgb = back + front
    elif mode == 2:
        rgb = back - front
    else:
        rgb = back + (front >> 2)
    rgb = np.clip(rgb, 0, 31).astype(np.uint8)
    rgb = (rgb << 3) | (rgb >> 2)
    visible = source[..., 3] != 0
    target[visible] = source[visible]
    target[..., :3][marked & visible] = rgb[marked & visible]
    image.paste(Image.fromarray(target), (x, y))


def sprite_part_image(page, part):
    """Sample all four UV corners, including mirrored and rotated parts.

    Width and height describe the screen rectangle, not the direction the
    UVs travel. Clock-room chairs and chandeliers have reversed U corners.
    """
    w, h = part[9:11]
    u0, v0, u1, v1, u2, v2, u3, v3 = (part[i] for i in (0, 1, 3, 4, 7, 8, 11, 12))
    if (u0 == u2 and u1 == u3 and v0 == v1 and v2 == v3
            and abs(u1 - u0) == w - 1 and abs(v2 - v0) == h - 1):
        tile = page.crop((min(u0, u1), min(v0, v2), max(u0, u1) + 1, max(v0, v2) + 1))
        if u1 < u0:
            tile = tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if v2 < v0:
            tile = tile.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        return tile
    uv = np.asarray(((part[0], part[1]), (part[3], part[4]),
                     (part[7], part[8]), (part[11], part[12])), np.float64)
    # Most parts name their last texel; some name the one after it, the way
    # a quad's far edge is not drawn. Such an edge is the part's own width or
    # height away from its start, and is brought in by one.
    for end, start, axis, extent in ((1, 0, 0, w), (3, 2, 0, w), (2, 0, 1, h), (3, 1, 1, h)):
        delta = uv[end, axis] - uv[start, axis]
        if abs(delta) == extent and extent > 1:
            uv[end, axis] -= np.sign(delta)
    # UV bytes wrap at the page boundary. Use the screen extent to distinguish
    # a wrapped edge from an intentionally reversed edge.
    for end, start, extent in ((1, 0, w), (2, 0, h), (3, 2, w), (3, 1, h)):
        for axis in range(2):
            delta = uv[end, axis] - uv[start, axis]
            if abs(delta) != extent - 1:
                for wrapped in (delta - 256, delta + 256):
                    if abs(wrapped) == extent - 1:
                        uv[end, axis] = uv[start, axis] + wrapped
                        break
    across = np.linspace(0, 1, w)[None, :, None]
    down = np.linspace(0, 1, h)[:, None, None]
    top = uv[0] * (1 - across) + uv[1] * across
    bottom = uv[2] * (1 - across) + uv[3] * across
    coords = np.rint(top * (1 - down) + bottom * down).astype(np.int32)
    pixels = np.asarray(page)
    return Image.fromarray(pixels[coords[:, :, 1] % page.height, coords[:, :, 0] % page.width])
