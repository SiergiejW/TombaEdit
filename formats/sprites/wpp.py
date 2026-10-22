"""WPP picture banks: packed pixels for Tomba and some enemy sprites.

Tomba has far more frames than fit in VRAM, so only the frame on screen is
kept there. US routine 8003A614 unpacks one bank entry into a scratch buffer
and 8003B0D4 uploads it to a fixed slot of a texture page every time the
animation moves on. The matching SPR bank has one frame per entry, and its
part UVs address that slot.

SPR supplies the assembly of parts; WPP supplies their packed pictures.
Sprites without a matching WPP bank use the section's resident VRAM pixels.

Bank layout: a 32-bit entry count, count + 1 absolute offsets (the last one
is the end of the bank), then the entries. An entry is a byte-oriented RLE
stream: a flag byte describes the next eight items, low bit first. A clear
bit copies one literal byte, a set bit reads a count and a value and repeats
the value. Unpacked, an entry is a 16-bit width in VRAM words, a 16-bit
height in rows and the 4-bit pixels.

Family 6 slot 3 (63FF) reuses the offset table for a different payload:
GAM-compressed TIM images. Its table has no count and starts at the first
offset.
"""
from dataclasses import dataclass
import struct
import numpy as np
from PIL import Image
from disc.reader import FormatError
from formats.archive.gam import decompress
from psx.graphics import rgba

# VRAM position of the palette block every section uploads; the first column
# holds Tomba's outfits, one per row.
TOMBA_CLUT = (128, 480)

# Tomba's draw routine (the European MAIN0 overlay's at 800EA124) ignores the
# palettes his parts store. It counts the parts down and gives a part the
# player's word +08 while bit 1 of the count still to draw is set, +C4
# otherwise. initPlayer sets the two (US 800A53A0 and 800A545C) to a hair
# row and a shorts row of the outfit block from the pairs of table 8007D5BC;
# a new game wears its first two rows. The words the parts store, 7830/7870,
# 7009/7049 or 7C0C/7C4C, follow the same pattern but are never drawn.
TOMBA_OUTFIT = (0, 1)

# Where 8003B0D4 uploads Tomba's current picture: the top of texture page 0,
# two buffers 16 VRAM words wide side by side, drawn alternately. A picture
# goes one word and four rows in from a buffer's corner.
PLAYER_BUFFERS = ((0, 0), (16, 0))
PLAYER_BUFFER = (16, 64)
PLAYER_PICTURE = (1, 4)


def reads_player_buffer(vram, parts, base):
    """True when these parts, drawn with page base `base`, read only the
    picture buffers of page 0 and VRAM holds nothing there: they show pieces
    of Tomba's current picture."""
    from psx.graphics import part_page
    words, rows = PLAYER_BUFFER
    for part in parts:
        page = part_page(part, base)
        if page & 31 or page >> 7 & 3:
            return False
        us, vs = (part[0], part[3], part[7], part[11]), (part[1], part[4], part[8], part[12])
        if max(us) // 4 >= words * len(PLAYER_BUFFERS) or min(vs) > rows:
            return False
    return not vram[:rows, :words * len(PLAYER_BUFFERS)].any()


def with_player_picture(vram, picture):
    """A copy of `vram` with `picture` uploaded to both of Tomba's buffers."""
    out = vram.copy()
    indices = picture.indices.astype(np.uint16)
    height, width = indices.shape
    width -= width % 4
    words = indices[:, 0:width:4] | indices[:, 1:width:4] << 4 | indices[:, 2:width:4] << 8 | indices[:, 3:width:4] << 12
    dx, dy = PLAYER_PICTURE
    for x, y in PLAYER_BUFFERS:
        out[y + dy:y + dy + height, x + dx:x + dx + words.shape[1]] = words
    return out


@dataclass
class Picture:
    index: int
    offset: int
    packed: int
    width: int          # pixels
    height: int
    indices: object     # (height, width) uint8 palette indices
    cluts: object = None  # (rows, colours) uint16, for TIM entries

    def image(self, palette=None):
        if palette is None:
            grey = (self.indices * (17 if self.indices.max(initial=0) < 16 else 1)).astype(np.uint8)
            return Image.fromarray(grey, 'L').convert('RGBA')
        return Image.fromarray(rgba(np.asarray(palette, np.uint16)[self.indices]))


def unpack(data, start, end):
    out, pos = bytearray(), start
    while pos < end:
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if pos >= end:
                break
            if flags >> bit & 1:
                if pos + 2 > end:
                    raise FormatError('WPP run is cut off')
                out += bytes((data[pos + 1],)) * data[pos]
                pos += 2
            else:
                out.append(data[pos])
                pos += 1
    return bytes(out)


def nibbles(data, words, height, offset):
    packed = np.frombuffer(data, np.uint8, words * 2 * height, offset).reshape(height, words * 2)
    indices = np.empty((height, words * 4), np.uint8)
    indices[:, 0::2] = packed & 15
    indices[:, 1::2] = packed >> 4
    return indices


def parse_tim(data, index=0, offset=0, packed=0):
    if len(data) < 20 or struct.unpack_from('<I', data)[0] != 0x10:
        raise FormatError('WPP entry is not a TIM image')
    mode, pos, cluts = struct.unpack_from('<I', data, 4)[0], 8, None
    if mode & 8:
        size, _, _, width, height = struct.unpack_from('<I4H', data, pos)
        if pos + size > len(data) or width * height * 2 > size - 12:
            raise FormatError('TIM palette block is cut off')
        cluts = np.frombuffer(data, '<u2', width * height, pos + 12).reshape(height, width)
        pos += size
    if pos + 12 > len(data):
        raise FormatError('TIM pixel block is missing')
    size, _, _, words, height = struct.unpack_from('<I4H', data, pos)
    if words * height * 2 > len(data) - pos - 12:
        raise FormatError('TIM pixel block is cut off')
    depth = mode & 3
    if depth == 0:
        indices = nibbles(data, words, height, pos + 12)
    elif depth == 1:
        indices = np.frombuffer(data, np.uint8, words * 2 * height, pos + 12).reshape(height, words * 2)
    else:
        raise FormatError('Only indexed TIM images are expected in a WPP bank')
    return Picture(index, offset, packed, indices.shape[1], height, indices, cluts)


def parse_wpp(data):
    """Return (kind, pictures); kind is 'frames' or 'tim'."""
    if len(data) < 12:
        raise FormatError('WPP bank is too small')
    first, second = struct.unpack_from('<II', data)
    if first == 0x10 and second < 0x10:
        # Early builds store the image on its own, neither packed nor indexed.
        return 'tim', [parse_tim(data, 0, 0, len(data))]
    if first % 4 == 0 and 8 <= first <= len(data) and data[first:first + 4] == b'GAM\0':
        offsets = struct.unpack_from(f'<{first // 4}I', data)
        if any(a >= b for a, b in zip(offsets, offsets[1:])) or offsets[-1] > len(data):
            raise FormatError('Invalid WPP image offsets')
        return 'tim', [parse_tim(decompress(data[a:b]), i, a, b - a)
                       for i, (a, b) in enumerate(zip(offsets, offsets[1:]))]
    count = first
    if not 0 < count <= 4096 or 8 + count * 4 > len(data):
        raise FormatError('Invalid WPP entry count')
    offsets = struct.unpack_from(f'<{count + 1}I', data, 4)
    if offsets[0] < 8 + count * 4 or offsets[-1] > len(data) or any(
            a >= b for a, b in zip(offsets, offsets[1:])):
        raise FormatError('Invalid WPP entry offsets')
    pictures = []
    for i, (start, end) in enumerate(zip(offsets, offsets[1:])):
        raw = unpack(data, start, end)
        if len(raw) < 4:
            raise FormatError(f'WPP entry {i} has no size header')
        words, height = struct.unpack_from('<HH', raw)
        if not 0 < words <= 64 or not 0 < height <= 256 or 4 + words * height * 2 > len(raw):
            raise FormatError(f'WPP entry {i} has an invalid size')
        pictures.append(Picture(i, start, end - start, words * 4, height,
                                nibbles(raw, words, height, 4)))
    return 'frames', pictures


def tomba_palettes(vram):
    """The outfit palettes a section's CLUT upload provides, top row first."""
    x, y = TOMBA_CLUT
    rows = [vram[y + row, x:x + 16] for row in range(32)]
    return [row for row in rows if row.any()]


def part_palettes(vram, parts, tomba, clut=None):
    """{part number: palette} for the parts of a frame whose palette is
    known: Tomba's parts the hair and shorts rows of the first outfit as his
    draw routine hands them out, other parts the row their CLUT word (or
    `clut`) names when VRAM holds it."""
    x, y = TOMBA_CLUT
    hair, shorts = (vram[y + row, x:x + 16] for row in TOMBA_OUTFIT)
    if tomba and hair.any() and shorts.any():
        return {n: hair if (len(parts) - n) & 2 else shorts for n in range(len(parts))}
    rows = {}
    for n, part in enumerate(parts):
        word = (part[2] if clut is None else clut) & 0x7FFF
        row = vram[(word >> 6) & 511, (word & 63) * 16:(word & 63) * 16 + 16]
        if row.any():
            rows[n] = row
    return rows


def frame_image(picture, parts, palette, part_palettes=None):
    """Assemble a SPR frame whose parts address one unpacked WPP picture.

    Part UVs keep the offsets they had on the source sheet; the game only
    uploads the picture, so they are taken relative to the frame's corner.
    """
    if not parts:
        return Image.new('RGBA', (1, 1))
    source = picture.image(palette)
    u0, v0 = min(p[0] for p in parts), min(p[1] for p in parts)
    left, top = min(p[13] for p in parts), min(p[14] for p in parts)
    right = max(p[13] + p[9] for p in parts)
    bottom = max(p[14] + p[10] for p in parts)
    image = Image.new('RGBA', (max(1, right - left), max(1, bottom - top)))
    for index in reversed(range(len(parts))):
        p = parts[index]
        part_source = picture.image(part_palettes[index]) if part_palettes and index in part_palettes else source
        u, v = p[0] - u0, p[1] - v0
        image.alpha_composite(part_source.crop((u, v, u + p[9], v + p[10])), (p[13] - left, p[14] - top))
    return image


def bank_palettes(vram, frames=None, tomba=True):
    """Palettes to offer for a picture bank, best first: [(name, words)].

    The palettes the matching SPR bank names come first when VRAM holds
    them, as it does for the phoenix bank. Tomba is drawn through the rows
    of the outfit block whatever his parts name, so his bank gets those."""
    found = []
    if not tomba:
        for clut in sorted({part[2] & 0x7FFF for frame in frames or [] for part in frame}):
            x, y = (clut & 63) * 16, (clut >> 6) & 511
            row = vram[y, x:x + 16]
            if len(row) == 16 and row.any():
                found.append((f'CLUT 0x{clut:04X}', row))
    if tomba or not found:
        found += [(f'Tomba palette {i}', row) for i, row in enumerate(tomba_palettes(vram))]
    return found


def renderer(frames, pictures, vram, tomba):
    """Frame drawing callback for a SPR bank whose pixels live in `pictures`,
    using the first palette bank_palettes() offers; Tomba's parts take the
    palettes his draw routine gives them (part_palettes())."""
    palettes = bank_palettes(vram, frames, tomba)
    palette = palettes[0][1] if palettes else None

    def render(index, overrides=None):
        parts = frames[index]
        if not parts or index >= len(pictures):
            return Image.new('RGBA', (1, 1))
        rows = part_palettes(vram, parts, True) if tomba else {}
        rows.update({part: vram[(clut >> 6) & 511, (clut & 63) * 16:(clut & 63) * 16 + 16]
                     for part, clut in (overrides or {}).items()})
        return frame_image(pictures[index], parts, palette, rows)
    return render
