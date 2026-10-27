"""Executable-resident PrePre 8 messages and five-byte atlas glyphs.

80035B84 selects A5DE4's message tables; 80035C1C selects A5E14's fonts.
Control arities come from 800358C8. This build has no WFM files.
"""
import hashlib
import struct
import json
from pathlib import Path
import numpy as np
from PIL import Image
from formats.text.wfm import Wfm, Dialogue, glyph_key
from psx.graphics import texture_page

CONTROLS = {0xFFFF: ('END_CLOSE', 0), 0xFFFE: ('NEXT', 0),
            0xFFFD: ('NEWLINE', 0), 0xFFFC: ('CLEAR', 0),
            0xFFFB: ('BUBBLE', 3), 0xFFFA: ('EVENT_SET', 2),
            0xFFF9: ('EVENT_COMPLETE', 1), 0xFFF8: ('PAUSE', 1), 0xFFF7: ('END', 0)}


def register(project):
    """Expose the embedded bank alongside ordinary font/text resources."""
    from game.builds import executable
    from formats.archive.ldar import Asset
    found = executable(project)
    groups = project.ldars.get('SYS/LDSYS.BIN')
    if found is None or not found.build.legacy8 or not groups:
        return
    source = project.disc.entries.get(project.catalog.executable)
    if source is not None:
        groups[0].assets.append(Asset('SYS/LDSYS.BIN', 0, 0x800A5DE4, 0, 0xD0FF,
                                    found.base, source, 0, source.size))


class EmbeddedBank(Wfm):
    def recognise(self):
        from formats.text.wfm import USER_GLYPHS
        super().recognise()
        names = json.loads(Path(__file__).with_name('glyphs_prepre8.json').read_text(encoding='utf8'))
        for number, key in enumerate(self.keys):
            if number >= 256:
                self.characters[number] = None
                continue
            if key not in USER_GLYPHS and key in names:
                self.characters[number] = names[key]

    def render(self, index, page=None):
        normal = Wfm.__new__(Wfm)
        normal.__dict__.update(self.__dict__)
        tokens = []
        for word, args in self.dialogues[index].tokens:
            if word == 0xFFFB:
                tokens.append((0xFFFA, args[:2]))
            elif word == 0xFFFC:
                tokens.append((0xFFFB, ()))
            elif word == 0xFFF8:
                tokens.append((0xFFF9, args))
            elif word in (0xFFF9, 0xFFFA, 0xFFFE):
                continue
            else:
                tokens.append((word, args))
        normal.dialogues = [Dialogue(self.dialogues[index].offset, tokens, characters=self.characters)]
        return Wfm.render(normal, 0, page)


def bank(project):
    from game.builds import executable
    found = executable(project)
    if found is None or not found.build.legacy8:
        return None
    if '_embedded_text_bank' in project.__dict__:
        return project._embedded_text_bank
    def read(address, size):
        if not found.holds(address, size):
            raise ValueError('Prototype text pointer outside executable')
        at = address - found.base + 0x800
        return found.data[at:at + size]
    tables = struct.unpack('<12I', read(0x800A5DE4, 48))
    fonts = struct.unpack('<12I', read(0x800A5E14, 48))
    bounds = sorted(set(tables + (0x800A5DE4,)))
    # Index 1 is ink; 2..D are its shadow shades. E is the box fill and
    # F the outside border: neither belongs to a standalone glyph.
    atlas = texture_page(project.vram('SYS/LDAR00.BIN', 1), 13, 0,
                         palette=np.array([0, 0x0400] + [0x4210] * 12 + [0, 0], dtype=np.uint16))
    result = EmbeddedBank.__new__(EmbeddedBank)
    result.version = b'PP8'
    result.groups, result.glyphs, result.indices = [], [], []
    result.keys, result.exact_keys, result.glyph_headers = [], [], []
    result.characters, result.dialogues = [], []
    offsets = {}
    for font in dict.fromkeys(fonts):
        offsets[font] = len(result.glyphs)
        for number in range(256 if font == 0x800A2BCC else 305):
            u, v, width, height, palette = read(font + number * 5, 5)
            if not (0 < width <= 32 and 0 < height <= 32):
                raise ValueError('Invalid prototype font descriptor')
            image = (Image.fromarray(np.asarray(atlas)[np.ix_((v + np.arange(height)) % 256,
                                                             (u + np.arange(width)) % 256)])
                     if font == 0x800A2BCC else Image.new('RGBA', (width, height)))
            result.glyphs.append(image)
            result.indices.append([])
            result.keys.append(glyph_key(image))
            result.exact_keys.append(hashlib.sha256(bytes(image.size) + image.tobytes()).hexdigest()[:24])
            result.glyph_headers.append((palette, width, height, 0))
            result.characters.append(None)
    result.recognise()
    for group, table in enumerate(tables):
        result.groups.append(len(result.dialogues))
        end = next(bound for bound in bounds if bound > table)
        for line, at in enumerate(range(table, end, 4)):
            start = found.word(at)
            pos, tokens = start, []
            for _ in range(4096):
                word = struct.unpack('<H', read(pos, 2))[0]
                pos += 2
                if word >= 0xFF00 and word not in CONTROLS:
                    raise ValueError(f'Unknown prototype text control {word:04X}')
                count = CONTROLS.get(word, ('', 0))[1]
                args = struct.unpack(f'<{count}H', read(pos, count * 2)) if count else ()
                pos += count * 2
                if word < 0xFF00:
                    word = (word & 0xF000) | ((word & 0xFFF) + offsets[fonts[group]])
                tokens.append((word, args))
                if word in (0xFFFF, 0xFFF7):
                    break
            else:
                raise ValueError('Unterminated prototype message')
            dialogue = Dialogue(start - found.base + 0x800, tokens, characters=result.characters)
            dialogue.controls = CONTROLS
            dialogue.name = f'{group:02X}:{line:02X}'
            if fonts[group] != 0x800A2BCC:
                dialogue.warning = 'Area-1 font texture is not present on this demo disc.'
            result.dialogues.append(dialogue)
    from formats.text.usage import prepre8
    prepre8(found, result)
    project._embedded_text_bank = result
    return result
