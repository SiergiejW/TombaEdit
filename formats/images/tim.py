"""TIM, the PlayStation's stock image file.

A TIM is the word 0x10, a flag word and one or two blocks. The flags give
the depth in their low bits (0: 4 bits, 1: 8 bits, 2: 15-bit colour, 3:
24-bit colour) and say in bit 3 whether a palette block comes first. Each
block is its length, a VRAM position, a size in VRAM words and the words
themselves, which is why a 4-bit image's stored width is a quarter of its
pixel width. A palette block holds as many palettes as fit in it.
"""
from dataclasses import dataclass
import struct
import numpy as np
from PIL import Image
from disc.reader import FormatError
from psx.graphics import rgba

MAGIC = 0x10
DEPTHS = (4, 8, 15, 24)


@dataclass
class Tim:
    offset: int             # where it starts in the data it was read from
    size: int               # bytes it occupies
    depth: int              # 4, 8, 15 or 24
    at: tuple               # VRAM position of the pixels
    words: np.ndarray       # the pixel block as stored, height x width in VRAM words
    palette_block: np.ndarray = None    # the palette block as stored, or None
    palette_at: tuple = None

    @property
    def width(self):
        stored = self.words.shape[1]
        return {4: stored * 4, 8: stored * 2, 15: stored, 24: stored * 2 // 3}[self.depth]

    @property
    def height(self):
        return self.words.shape[0]

    @property
    def palettes(self):
        """The palette block cut into palettes, one a row; empty if none."""
        colours = 16 if self.depth == 4 else 256
        if self.palette_block is None or self.depth > 8 or self.palette_block.size < colours:
            return np.zeros((0, colours), np.uint16)
        flat = self.palette_block.reshape(-1)
        return flat[:flat.size // colours * colours].reshape(-1, colours)

    def indices(self):
        """Palette indices of an indexed image, height x width."""
        out = np.empty((self.height, self.width), np.uint8)
        if self.depth == 4:
            for n in range(4):
                out[:, n::4] = (self.words >> (n * 4)) & 15
        else:
            out[:, 0::2] = self.words & 255
            out[:, 1::2] = self.words >> 8
        return out

    def palette(self, number=0):
        """Colour words of one palette; grey steps where the file has none."""
        palettes = self.palettes
        if not len(palettes):
            size = palettes.shape[1]
            step = (np.arange(size, dtype=np.uint32) * 31 // (size - 1)).astype(np.uint16)
            return step | step << 5 | step << 10 | 0x8000
        return palettes[max(0, min(number, len(palettes) - 1))]

    def image(self, palette=0):
        """The picture as RGBA. Colour word 0 is transparent, as on the console."""
        if self.depth in (4, 8):
            return Image.fromarray(rgba(self.palette(palette)[self.indices()]))
        if self.depth == 15:
            return Image.fromarray(rgba(self.words))
        raw = np.frombuffer(self.words.astype('<u2').tobytes(), np.uint8)
        rgb = raw.reshape(self.height, -1)[:, :self.width * 3].reshape(self.height, self.width, 3)
        return Image.fromarray(rgb, 'RGB').convert('RGBA')

    def describe(self):
        text = f'{self.width} x {self.height}, {self.depth}-bit, VRAM ({self.at[0]}, {self.at[1]})'
        count = len(self.palettes)
        if count:
            text += (f', {count} palette{"s" if count != 1 else ""} at '
                     f'({self.palette_at[0]}, {self.palette_at[1]})')
        return text


def block(data, pos):
    """(end, x, y, words) of the block at `pos`: where it stops, where it
    goes in VRAM and its contents as height x width words."""
    if pos + 12 > len(data):
        raise FormatError('TIM block header is cut off')
    size, x, y, width, height = struct.unpack_from('<I4H', data, pos)
    if not (0 < width <= 1024 and 0 < height <= 512) or size < 12 + width * height * 2:
        raise FormatError('TIM block size does not match its dimensions')
    if pos + 12 + width * height * 2 > len(data):
        raise FormatError('TIM block is cut off')
    words = np.frombuffer(data, '<u2', width * height, pos + 12).reshape(height, width)
    return pos + size, x, y, words


def parse(data, offset=0):
    """The TIM at `offset`."""
    if offset + 8 > len(data) or struct.unpack_from('<I', data, offset)[0] != MAGIC:
        raise FormatError('Not a TIM image')
    flags = struct.unpack_from('<I', data, offset + 4)[0]
    if flags & ~0xB:
        raise FormatError(f'Unsupported TIM flags {flags:X}')
    depth, pos = DEPTHS[flags & 3], offset + 8
    palette = palette_at = None
    if flags & 8:
        pos, x, y, palette = block(data, pos)
        palette_at = (x, y)
    end, x, y, words = block(data, pos)
    return Tim(offset, end - offset, depth, (x, y), words, palette, palette_at)


def wrap(data):
    """A TIM made from blocks stored without its header, or b''.

    Two bare forms turn up inside archives: a palette block followed by
    a position, a size and pixels, which is a TIM less its first eight
    bytes and the pixel block's length; and a position, a size and words
    alone, which is a rectangle of VRAM."""
    size = len(data)
    if size < 16:
        return b''
    length, _x, _y, width, height = struct.unpack_from('<I4H', data)
    if length == 12 + width * height * 2 and width in (16, 256) and 0 < height <= 16 and length + 8 <= size:
        x, y, words, rows = struct.unpack_from('<4H', data, length)
        body = words * rows * 2
        if 0 < body <= size - length - 8 < body + 2048 and x < 1024 and y < 512:
            return (struct.pack('<II', MAGIC, 9 if width == 256 else 8) + bytes(data[:length])
                    + struct.pack('<I', 12 + body) + bytes(data[length:length + 8 + body]))
    x, y, words, rows = struct.unpack_from('<4H', data)
    if x < 1024 and y < 512 and 0 < words <= 1024 and 0 < rows <= 512 and words * rows >= 16 \
            and size == 8 + words * rows * 2:
        return struct.pack('<III', MAGIC, 2, 12 + words * rows * 2) + bytes(data)
    return b''


def find(data, limit=4096):
    """Every TIM in `data`, wherever it starts. Files that pack their
    resources without an index are read this way."""
    found, at, view = [], 0, bytes(data)
    while len(found) < limit:
        at = view.find(b'\x10\0\0\0', at)
        if at < 0:
            break
        try:
            tim = parse(view, at)
        except FormatError:
            at += 1
            continue
        # A block's length is its header and words and nothing else in a
        # real file; chance matches rarely agree on that.
        exact = tim.size == 8 + sum(12 + b.size * 2 for b in (tim.words, tim.palette_block) if b is not None)
        if exact and tim.at[0] < 1024 and tim.at[1] < 512:
            found.append(tim)
            at += tim.size
        else:
            at += 4
    return found


def upload(vram, tim):
    """Put a TIM's blocks where they belong in a 512 x 1024 VRAM array."""
    for origin, words in ((tim.palette_at, tim.palette_block), (tim.at, tim.words)):
        if words is None:
            continue
        height, width = words.shape
        vram[np.ix_((np.arange(height) + origin[1]) % 512, (np.arange(width) + origin[0]) % 1024)] = words
