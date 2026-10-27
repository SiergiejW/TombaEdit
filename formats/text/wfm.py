"""WFM glyphs and dialogue control words, after vervalkon's WFM3 notes."""
from dataclasses import dataclass, field
import hashlib
import json
import unicodedata
from pathlib import Path
from psx.graphics import rgba
from formats.text.tombadict import letters
import struct
from PIL import Image, ImageDraw
from disc.reader import FormatError

DIALOGUE_CLUT = (0x0000,0x0400,0x4E73,0x2529,0x35AD,0x4210,0x14A5,0x7E4D,0x03E0,0x421F,0x297F,0x5319,0x4674,0x3A11,0,0)
EVENT_CLUT = (0x01FF,0x8400,0x7FFF,0x3DEF,0x2529,0x56B5,0x00F0,0x0198,0x6739,0x0134,0x01FF,0x7C00,0x7C00,0x7C00,0x7C00,0x7C00)
GLYPH_DICTIONARY = json.loads(Path(__file__).with_name('glyph_dictionary.json').read_text('utf8'))
# WFM IDs are font-local. Recognize the bitmap before consulting the shared
# character vocabulary; applying tombadict's numeric IDs directly is incorrect.
EXACT_GLYPHS = json.loads(Path(__file__).with_name('glyphs_us.json').read_text('utf8'))
CANONICAL = {value: value for value in letters.values()}

# Characters given to glyphs in the application: shape key -> character.
# They come before the built-in dictionaries, so a wrong guess can be put
# right, and they are what names the glyphs of a font nobody has read yet.
USER_GLYPHS = {}


def glyph_key(image):
    """What a glyph's character is kept under: a hash of its size and of
    which of its pixels are lit, whatever their colour. The same letter in
    another colour has the same key."""
    if max(image.size) >= 256:
        return ''
    mask = bytes(1 if a and (r or g or b) else 0 for r,g,b,a in image.getdata())
    return hashlib.sha256(bytes([image.width, image.height]) + mask).hexdigest()[:24]


def glyph_letter(image):
    value = GLYPH_DICTIONARY.get(glyph_key(image))
    return CANONICAL.get(value, value)

# Flags in the top of a glyph word. In WFM1 a kana that is voiced is two
# words: the kana with MARKED and then the mark (dakuten or handakuten) with
# MARK, drawn over the same cell. In WFM3 a word with OVER alone is the
# prompt drawn in the corner of the box.
OVER, MARKED, MARK = 0x4000, 0x1000, 0x2000


def corner(word):
    """True for a glyph drawn in the corner of the box, not in the text."""
    return word < 0xFF00 and word & OVER and not word & (MARKED | MARK)


def composed(text):
    """Join each kana to the mark written after it: か and a dakuten read が."""
    return unicodedata.normalize('NFC', text)


CONTROLS = {
    0xFFFF: ("END_CLOSE", 0), 0xFFFE: ("END", 0), 0xFFFD: ("NEWLINE", 0),
    0xFFFC: ("WAIT_INPUT", 0), 0xFFFB: ("CLEAR", 0), 0xFFFA: ("BUBBLE", 2),
    0xFFF9: ("WAIT", 1), 0xFFF8: ("VOICE_TAIL", 2), 0xFFF7: ("COLOR", 1),
    0xFFF6: ("UNKNOWN_F6", 2), 0xFFF5: ("PROMPT", 0),
    0xFFF3: ("UNKNOWN_F3", 1), 0xFFF2: ("UNKNOWN_F2", 1), 0xFFF0: ("UNKNOWN_F0", 2),
}


@dataclass
class Dialogue:
    offset: int
    tokens: list
    warning: str = ""

    characters: list = field(default_factory=list)
    # An event title's (column, row, flags) per letter, from the overlays
    # (formats.text.titles); None for other text.
    layout: list = None

    def script(self):
        if self.layout:
            from formats.text.titles import text
            return composed(text(self, self.layout, self.letter))
        parts = []
        for word, args in self.tokens:
            if word >= 0xFF00:
                if word == 0xFFF6 and args == (0, 0):
                    continue
                names = getattr(self, 'controls', None) or {**EARLY_CONTROLS, **CONTROLS}
                name = names.get(word, (f"UNKNOWN_{word:04X}", 0))[0]
                parts.append(f"\n<{name}{''.join(f' {a:04X}' for a in args)}>")
            else:
                if corner(word):
                    continue
                gid = word & 0xFFF
                char = self.characters[gid] if gid < len(self.characters) else None
                parts.append(char if char is not None else f'[g{gid:03X}]')
        return composed("".join(parts)).strip() + (f"\n\n{self.warning}" if self.warning else "")

    def letter(self, word, unknown='[g{:03X}]'):
        gid = word & 0xFFF
        char = self.characters[gid] if gid < len(self.characters) else None
        return char if char is not None else unknown.format(gid)


# Where the glyph pointer table starts. WFM1, used by the builds from 1997,
# has the same 16-byte header as WFM3 without the 128 reserved bytes after it.
GLYPH_TABLE = {b"WFM1": 16, b"WFM3": 144}
# WFM1 text uses FFF4 inside running text with nothing after it.
EARLY_CONTROLS = {0xFFF4: ("UNKNOWN_F4", 0)}
MAGICS = tuple(GLYPH_TABLE)


class Wfm:
    def __init__(self, data):
        self.version = bytes(data[:4])
        glyph_table = GLYPH_TABLE.get(self.version)
        if glyph_table is None or len(data) < glyph_table:
            raise FormatError("Not a WFM font/dialogue resource")
        reserved, table, nd, ng = struct.unpack_from("<IIHH", data, 4)
        if reserved or glyph_table + ng * 2 > len(data) or table + nd * 2 > len(data):
            raise FormatError("Invalid WFM header or pointer tables")
        # WFM3: the 128 bytes after the header are 64 group bases. A message
        # box (group, line) shows dialogue base[group] + line (routine
        # openMessageBox of Tombi-Decomp); group 0 is the system text.
        self.groups = list(struct.unpack_from("<64H", data, 16)) if glyph_table == 144 else []
        self.glyphs = []
        self.keys = []          # shape key of each glyph, what its character is looked up by
        self.exact_keys = []    # and the key of its exact pixels
        self.characters = []
        self.indices = []
        self.glyph_headers = []
        palette = [(0, 0, 0, 0)] + [(256 - i * 16,) * 3 + (255,) for i in range(1, 16)]
        for i in range(ng):
            ptr = struct.unpack_from("<H", data, glyph_table + i * 2)[0]
            if ptr + 8 > len(data):
                raise FormatError("WFM glyph header outside resource")
            pal, height, width, unused = struct.unpack_from("<4H", data, ptr)
            # WFM3 packs a glyph's pixels end to end. WFM1 starts every row
            # on a 16-bit word, so a 10 pixel row takes six bytes.
            row = (width + 3) // 4 * 2 if self.version == b"WFM1" else 0
            size = row * height if row else (width * height + 1) // 2
            if not 0 < width <= 512 or not 0 < height <= 512 or ptr + 8 + size > len(data):
                raise FormatError("Invalid WFM glyph dimensions")
            indices = [n for b in data[ptr + 8:ptr + 8 + size] for n in (b & 15, b >> 4)]
            if row:
                indices = [n for y in range(height) for n in indices[y * row * 2:y * row * 2 + width]]
            palette = [tuple(c) for c in rgba(EVENT_CLUT if height in (20, 24) else DIALOGUE_CLUT)]
            self.indices.append(indices[:width * height])
            im = Image.new("RGBA", (width, height))
            im.putdata([palette[n] for n in indices[:width * height]])
            self.glyphs.append(im)
            key = hashlib.sha256(bytes(im.size) + bytes(indices[:width * height])).hexdigest()[:24] if max(im.size) < 256 else ''
            self.exact_keys.append(key)
            # The 1997 title font is drawn on a solid ground, so every one
            # of its glyphs has the same lit pixels; those are told apart
            # by their exact pixels instead.
            solid = all(a and (r or g or b) for r, g, b, a in im.getdata())
            self.keys.append(key if solid else glyph_key(im))
            self.characters.append(None)
            self.glyph_headers.append((pal, width, height, unused))
        self.recognise()
        starts = [table + struct.unpack_from("<H", data, table + i * 2)[0] for i in range(nd)]
        if any(p < table + nd * 2 or p >= len(data) for p in starts):
            raise FormatError("Dialogue pointer outside WFM resource")
        bounds = sorted(set(starts + [len(data)]))
        self.dialogues = []
        controls = {**CONTROLS, **EARLY_CONTROLS} if self.version == b"WFM1" else CONTROLS
        for start in starts:
            end = next(p for p in bounds if p > start)
            pos, tokens, warning = start, [], ""
            while pos + 2 <= end:
                word = struct.unpack_from("<H", data, pos)[0]
                pos += 2
                if word >= 0xFF00 and word not in controls:
                    warning = f"Unknown control {word:04X}; decoding stopped at {pos - 2:04X}."
                    tokens.append((word, ()))
                    break
                nargs = controls.get(word, ("", 0))[1]
                if pos + nargs * 2 > end:
                    warning = "Truncated control arguments."
                    break
                args = struct.unpack_from(f"<{nargs}H", data, pos)
                pos += nargs * 2
                tokens.append((word, args))
                if word in (0xFFFF, 0xFFFE):
                    break
            else:
                warning = "No end control before the next dialogue boundary."
            self.dialogues.append(Dialogue(start, tokens, warning, self.characters))

    def message(self, group, line):
        """The dialogue a message box (group, line) shows, or None."""
        if not 0 <= group < len(self.groups):
            return None
        index = self.groups[group] + line
        return self.dialogues[index] if 0 <= index < len(self.dialogues) else None

    def recognise(self):
        """Work out each glyph's character again: the one given to its
        shape in the application, then the built-in dictionaries. The list
        is changed in place, since every entry reads from it."""
        for number, (key, exact, image) in enumerate(zip(self.keys, self.exact_keys, self.glyphs)):
            if key in USER_GLYPHS:
                self.characters[number] = USER_GLYPHS[key] or None
            elif key == exact:
                self.characters[number] = EXACT_GLYPHS.get(exact, GLYPH_DICTIONARY.get(exact))
            else:
                self.characters[number] = EXACT_GLYPHS.get(exact, glyph_letter(image))

    def pages(self, index):
        pages, tokens = [], []
        for token in self.dialogues[index].tokens:
            tokens.append(token)
            if token[0] == 0xFFFB:
                pages.append(tokens); tokens = []
        if tokens and any(w < 0xFF00 for w, _ in tokens):
            pages.append(tokens)
        return pages or [tokens]

    def render(self, index, page=None):
        sequences = self.pages(index)
        chosen = sequences if page is None else [sequences[min(page,len(sequences)-1)]]
        bubble = next((args for word,args in self.dialogues[index].tokens if word == 0xFFFA), (256,48))
        panels = []
        for tokens in chosen:
            lines, line = [], []
            blink = None
            for word, args in tokens:
                if word == 0xFFFD:
                    lines.append(line); line=[]
                elif word < 0xFF00:
                    gid = word & 0xFFF
                    glyph = self.glyphs[gid] if gid < len(self.glyphs) else Image.new('RGBA',(8,16),'red')
                    if corner(word):
                        blink = glyph
                    elif word & MARK and line:
                        # The mark goes over the kana before it, up in its
                        # top right corner.
                        both = line[-1].copy()
                        both.alpha_composite(glyph.crop((0, glyph.height * 6 // 10, glyph.width, glyph.height)),
                                             (min(2, both.width - 1), 0))
                        line[-1] = both
                    else:
                        line.append(glyph)
            lines.append(line)
            width = max([sum(im.width for im in line) for line in lines]+[bubble[0]])+16
            heights = [max([im.height for im in line]+[8])+2 for line in lines]
            height = max(sum(heights)+16,bubble[1]+8)
            if width > 8192 or height > 16384:
                raise FormatError('Dialogue preview exceeds image size limit')
            result = Image.new('RGBA',(width,height),(220,216,194,255))
            draw = ImageDraw.Draw(result)
            draw.rectangle((0,0,width-1,height-1),outline=(32,24,16),width=2)
            draw.rectangle((3,3,width-4,height-4),outline=(255,252,230),width=1)
            y=8
            for line,h in zip(lines,heights):
                x=8
                for im in line:
                    result.alpha_composite(im,(x,y));x+=im.width
                y+=h
            if blink:
                result.alpha_composite(blink,(width-blink.width-6,height-blink.height-4))
            panels.append(result)
        out=Image.new('RGBA',(max(p.width for p in panels),sum(p.height for p in panels)+8*(len(panels)-1)))
        y=0
        for im in panels:
            out.alpha_composite(im,(0,y));y+=im.height+8
        return out

    def atlas(self):
        cw = max([im.width for im in self.glyphs] + [8]) + 8
        ch = max([im.height for im in self.glyphs] + [8]) + 20
        result = Image.new("RGBA", (cw * 16, max(1, (len(self.glyphs) + 15) // 16) * ch), (28, 28, 30, 255))
        draw = ImageDraw.Draw(result)
        for i, im in enumerate(self.glyphs):
            x, y = (i % 16) * cw, (i // 16) * ch
            result.alpha_composite(im, (x + 4, y))
            draw.text((x + 2, y + ch - 15), f"{i:03X}", fill="gray")
        return result
