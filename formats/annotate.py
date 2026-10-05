"""Byte ranges of a resource and what they hold, for the hex view.

Each format gets a function that walks its structure and returns Region
records. A region names a byte range, says what it is, and carries a group:
ranges in one group are painted the same colour. Structures that have no
decoder of their own, such as code overlays, are classified word by word.
"""
from dataclasses import dataclass
import struct

# Area overlays are linked for one address per build, US retail's being this
# one; the loader ignores the address in their load record (routine 80021D70).
OVERLAY_BASE = 0x800E7388
RAM_LOW, RAM_HIGH = 0x80010000, 0x80200000
JR_RA = 0x03E00008


@dataclass
class Region:
    start: int
    end: int
    group: str
    name: str
    detail: str = ''


def u16(data, at):
    return struct.unpack_from('<H', data, at)[0]


def u32(data, at):
    return struct.unpack_from('<I', data, at)[0]


def fields(out, at, layout, prefix):
    """Add one region per (size, group, name, detail) entry of a record."""
    for size, group, name, detail in layout:
        out.append(Region(at, at + size, group, f'{prefix}: {name}', detail))
        at += size
    return at


SPR_PART = ((2, 'uv', 'U, V of corner 0', 'Texel position on the texture page.'),
            (2, 'clut', 'CLUT word', 'Palette position: row * 64 + x / 16.'),
            (2, 'uv', 'U, V of corner 1', ''),
            (2, 'page', 'texture page word', 'Relative page; the drawing object adds its base.'),
            (2, 'uv', 'U, V of corner 2', ''),
            (2, 'size', 'width, height', 'Size of the part in pixels.'),
            (2, 'uv', 'U, V of corner 3', ''),
            (2, 'position', 'X, Y offset', 'Signed offset from the object origin.'))


def spr(data):
    out = []
    first = u16(data, 2) if len(data) >= 4 else 0
    if not first or first % 4 or first > len(data):
        return out
    for frame in range(first // 4):
        count, offset = struct.unpack_from('<HH', data, frame * 4)
        out.append(Region(frame * 4, frame * 4 + 2, 'count', f'Frame {frame}: part count',
                          f'{count} parts.'))
        out.append(Region(frame * 4 + 2, frame * 4 + 4, 'pointer', f'Frame {frame}: offset of its parts',
                          f'Parts start at 0x{offset:X}.'))
        for part in range(count):
            at = offset + part * 16
            if at + 16 <= len(data):
                fields(out, at, SPR_PART, f'Frame {frame} part {part}')
    return out


def offset_table(out, data, count, at, what, end_entry=False):
    offsets = []
    for i in range(count + end_entry):
        value = u32(data, at + i * 4)
        offsets.append(value)
        last = end_entry and i == count
        out.append(Region(at + i * 4, at + i * 4 + 4, 'pointer',
                          'End of the bank' if last else f'Offset of {what} {i}', f'0x{value:X}'))
    return offsets


WMD_KINDS = ('FT3', 'FT4', 'GT3', 'GT4', 'F3', 'F4', 'G3', 'G4')


def wmd(data):
    out = []
    count = u32(data, 0) if len(data) >= 4 else 0
    if not 0 < count <= 4096 or 4 + count * 4 > len(data):
        return out
    from formats.models.wmd import layout_of, primitive_size, EARLY
    layout = layout_of(data)
    if layout is None:
        return out
    out.append(Region(0, 4, 'count', 'Model count', f'{count} models.'))
    offsets = offset_table(out, data, count, 4, 'model') + [len(data)]
    for model, (start, end) in enumerate(zip(offsets, offsets[1:])):
        at = start
        for kind in range(8):
            if at + 4 > end:
                break
            amount = u32(data, at)
            vertices = 3 + kind % 2
            colours = vertices if kind % 4 >= 2 else 1
            textured = kind < 4
            size = primitive_size(kind, layout)
            out.append(Region(at, at + 4, 'count', f'Model {model}: {WMD_KINDS[kind]} count',
                              f'{amount} primitives of {size} bytes.'))
            at += 4
            for n in range(amount):
                if at + size > end:
                    break
                p, name = at, f'Model {model} {WMD_KINDS[kind]} {n}'
                if textured and layout == EARLY:
                    # The 1997 layout: colours, a word per corner, positions.
                    out.append(Region(p, p + colours * 4, 'colour', f'{name}: colours',
                                      'Red, green, blue and the GPU command byte, per colour.'))
                    p += colours * 4
                    for corner in range(vertices):
                        what = ('CLUT word', 'texture page word')[corner] if corner < 2 else 'unused'
                        p = fields(out, p, ((2, 'uv', f'U, V of corner {corner}', ''),
                                            (2, ('clut', 'page', 'padding', 'padding')[corner], what, '')), name)
                    out.append(Region(p, p + vertices * 8, 'position', f'{name}: vertices',
                                      'X, Y, Z as signed words and padding'))
                    at += size
                    continue
                if textured:
                    p = fields(out, p, ((2, 'clut', 'CLUT word', ''), (2, 'page', 'texture page word', '')), name)
                out.append(Region(p, p + colours * 4, 'colour', f'{name}: colours',
                                  'Red, green, blue and the GPU command byte, per colour.'))
                p += colours * 4
                out.append(Region(p, p + vertices * 8, 'position', f'{name}: vertices',
                                  'X, Y, Z as signed words, then U and V' if textured else
                                  'X, Y, Z as signed words and padding'))
                p += vertices * 8
                if not textured:
                    out.append(Region(p, at + size, 'size', f'{name}: normals', 'One per colour, and a closing word.'))
                at += size
    return out


def four(data):
    out = []
    count = u32(data, 0) if len(data) >= 4 else 0
    if not 0 < count <= 4096 or 4 + count * 4 > len(data):
        return out
    out.append(Region(0, 4, 'count', 'Deformation count', f'{count} deformations.'))
    offsets = offset_table(out, data, count, 4, 'deformation') + [len(data)]
    strides = (32, 40, 48, 64, 32, 40, 48, 64)
    for index, (start, end) in enumerate(zip(offsets, offsets[1:])):
        at = start
        for kind, stride in enumerate(strides):
            if at + 4 > end:
                break
            amount = u32(data, at)
            out.append(Region(at, at + 4, 'count', f'Deformation {index}: {WMD_KINDS[kind]} count',
                              f'{amount} records of {stride} bytes.'))
            at += 4
            corners = 3 + kind % 2
            for n in range(amount):
                if at + stride > end:
                    break
                out.append(Region(at, at + corners * 8, 'position', f'Deformation {index} {WMD_KINDS[kind]} {n}: deltas',
                                  'One signed X, Y, Z delta per corner, subtracted scaled by the weight.'))
                out.append(Region(at + corners * 8, at + stride, 'size', f'Deformation {index} {WMD_KINDS[kind]} {n}: reserved', ''))
                at += stride
    return out


APD_RECORD = ((1, 'count', 'section', 'Section the object belongs to; negative values are stored inverted.'),
              (1, 'page', 'layer', 'Selects the object pool and handler table. Bit 7 is a flag.'),
              (1, 'clut', 'type', 'Index into the layer\'s handler table. FF ends the list.'),
              (1, 'size', 'variant A', ''),
              (1, 'size', 'variant B', 'Usually picks the look of the object.'),
              (1, 'colour', 'facing', 'Copied to the object; bit 0 is the unmirrored flag.'),
              (6, 'position', 'X, Y, Z', 'Signed words. Y is negative upwards.'),
              (1, 'uv', 'flags', 'Bit 4: the model index byte is used.'),
              (1, 'uv', 'draw order', ''),
              (1, 'pointer', 'model index', 'FF for none.'),
              (1, 'uv', 'position mode', 'Low two bits: absolute, parent, child or sibling position.'))


def apd(data):
    out = []
    for at in range(0, len(data) - 15, 16):
        if data[at + 2] == 255:
            out.append(Region(at, at + 16, 'padding', 'End of placements', 'Type FF closes the list.'))
            break
        fields(out, at, APD_RECORD, f'Placement {at // 16}')
    return out


def whm(data):
    from formats.collision.whm import parse_whm
    from disc.reader import FormatError
    out = []
    try:
        parsed = parse_whm(data)
    except FormatError:
        return out
    count = len(parsed.planes)
    fields(out, 0, ((1, 'clut', 'format tag', ''), (1, 'count', 'plane count', f'{count} planes.'),
                    (2, 'position', 'origin', ''), (2, 'size', 'width', f'{parsed.width} units, 8 per column.'),
                    (2, 'size', 'height', ''), (2, 'pointer', 'offset of plane 1', '')), 'Header')
    for i in range(1, count):
        out.append(Region(8 + i * 2, 10 + i * 2, 'pointer', f'Offset of plane {i}', ''))
    columns = parsed.width // 8
    for plane in parsed.planes:
        spans = plane.spans
        if not plane.columns:
            continue
        base = u16(data, 8 + plane.index * 2)
        out.append(Region(base, base + columns * 2, 'pointer', f'Plane {plane.index}: column offsets',
                          'One 16-bit offset per 8 units of X, relative to the start of the plane.'))
        for span in spans:
            fields(out, span.offset, (
                (2, 'clut', 'attribute', 'Bits 0..3: floor, ceiling, left and right boundaries; bit 4: filled region.'),
                (2, 'position', 'base Y', 'Base height, negative upwards.'),
                (2, 'size', 'Y delta', 'Signed change from base Y, including filled regions.'),
                (2, 'uv', 'horizontal interval / contact', 'Low nibble: start; next nibble: width; high byte: contact control.')),
                f'Plane {plane.index} column {span.column} span')
    return out


def wpp(data):
    out = []
    first = u32(data, 0) if len(data) >= 12 else 0
    if first % 4 == 0 and 8 <= first <= len(data) and data[first:first + 4] == b'GAM\0':
        offsets = offset_table(out, data, first // 4, 0, 'image')
        for i, (start, end) in enumerate(zip(offsets, offsets[1:])):
            out.append(Region(start, end, 'colour' if i % 2 else 'size', f'Image {i}', 'GAM-compressed TIM image.'))
        return out
    if not 0 < first <= 4096 or 8 + first * 4 > len(data):
        return out
    out.append(Region(0, 4, 'count', 'Picture count', f'{first} pictures.'))
    offsets = offset_table(out, data, first, 4, 'picture', end_entry=True)
    for i, (start, end) in enumerate(zip(offsets, offsets[1:])):
        out.append(Region(start, end, 'colour' if i % 2 else 'size', f'Picture {i}',
                          'Run-length packed: a flag byte, then eight literals or count and value pairs.'))
    return out


def wfm(data):
    out = []
    from formats.text.wfm import GLYPH_TABLE
    glyph_table = GLYPH_TABLE.get(bytes(data[:4]))
    if glyph_table is None or len(data) < glyph_table:
        return out
    early = glyph_table == 16
    table, dialogues, glyphs = struct.unpack_from('<IHH', data, 8)
    fields(out, 0, ((4, 'clut', 'magic', data[:4].decode('ascii')), (4, 'padding', 'reserved', ''),
                    (4, 'pointer', 'dialogue table offset', f'0x{table:X}'),
                    (2, 'count', 'dialogue count', str(dialogues)), (2, 'count', 'glyph count', str(glyphs)))
           + (() if early else ((128, 'padding', 'reserved', ''),)), 'Header')
    for i in range(glyphs):
        at = glyph_table + i * 2
        if at + 2 > len(data):
            break
        pointer = u16(data, at)
        out.append(Region(at, at + 2, 'pointer', f'Offset of glyph {i:03X}', f'0x{pointer:X}'))
        if pointer + 8 <= len(data):
            _, height, width, _ = struct.unpack_from('<4H', data, pointer)
            end = fields(out, pointer, ((2, 'clut', 'palette', ''), (2, 'size', 'height', ''),
                                        (2, 'size', 'width', ''), (2, 'padding', 'unused', '')), f'Glyph {i:03X}')
            size = (width + 3) // 4 * 2 * height if early else (width * height + 1) // 2
            out.append(Region(end, min(len(data), end + size), 'colour', f'Glyph {i:03X}: pixels',
                              '4 bits a pixel, low nibble first' + (', each row padded to 16 bits.' if early else '.')))
    starts = []
    for i in range(dialogues):
        at = table + i * 2
        if at + 2 > len(data):
            break
        starts.append(table + u16(data, at))
        out.append(Region(at, at + 2, 'pointer', f'Offset of dialogue {i}', f'0x{starts[-1]:X}'))
    bounds = sorted(set(starts + [len(data)]))
    for i, start in enumerate(starts):
        end = next(b for b in bounds if b > start)
        out.append(Region(start, end, 'uv' if i % 2 else 'position', f'Dialogue {i}',
                          '16-bit words: glyph numbers with flags, or control words from FFF0 up.'))
    return out


def instructions(data, base=OVERLAY_BASE):
    """Classify a code overlay word by word.

    Functions are found from their stack prologue to the return that
    follows; words outside them that point into loaded memory are tables,
    eight-byte animation steps are recognised where a table points at them,
    and text and zero runs are named. Everything else is left unmarked."""
    out, words = [], len(data) // 4
    if not words:
        return out
    values = struct.unpack_from(f'<{words}I', data)
    kind = [None] * words
    inside = lambda value: base <= value < base + len(data)
    # An overlay opens with a count and that many entry points.
    count = values[0]
    if 0 < count < 256 and count < words and all(inside(v) for v in values[1:count + 1]):
        out.append(Region(0, 4, 'count', 'Entry count', f'{count} entry points follow.'))
        for i in range(1, count + 1):
            kind[i] = 'entry'
            out.append(Region(i * 4, i * 4 + 4, 'pointer', f'Entry point {i - 1}',
                              f'Function at 0x{values[i]:08X}, file offset 0x{values[i] - base:X}.'))
        kind[0] = 'entry'
    i = functions = 0
    while i < words:
        value = values[i]
        # addiu $sp, $sp, -n
        if kind[i] is None and value >> 16 == 0x27BD and value & 0x8000:
            frame = 0x10000 - (value & 0xFFFF)
            end = next((j for j in range(i + 1, min(words - 1, i + 6000)) if values[j] == JR_RA), None)
            if end is not None and frame <= 0x400:
                end += 2            # the return and its delay slot
                calls = sum(1 for v in values[i:end] if v >> 26 == 3)
                functions += 1
                out.append(Region(i * 4, end * 4, 'code' if functions % 2 else 'code2',
                                  f'Function 0x{base + i * 4:08X}',
                                  f'{end - i} instructions, {frame} byte stack frame, {calls} calls.'))
                for j in range(i, end):
                    kind[j] = 'code'
                i = end
                continue
        i += 1
    # Animation steps reached through pointers.
    for i in range(words):
        if kind[i] is not None or not inside(values[i]):
            continue
        at = (values[i] - base) // 4
        steps = 0
        while at + 1 < words and kind[at] is None and kind[at + 1] is None:
            frame, a, b, control = struct.unpack_from('<4H', data, at * 4)
            if frame >= 1024 or (control & 0x3FFF) > 600 or not (control & 0x3FFF or control & 0xC000):
                break
            kind[at] = kind[at + 1] = 'step'
            jump = bool(control & 0x4000)
            out.append(Region(at * 4, at * 4 + 8, 'uv', f'Animation step 0x{base + at * 4:08X}',
                              f'Frame {frame} for {control & 0x3FFF} ticks'
                              + {0: ', then the next step.', 0x8000: ', then hold.'}.get(control & 0xC000, ', then jump.')))
            at += 2
            steps += 1
            if control & 0xC000:
                if jump and at < words and kind[at] is None and RAM_LOW <= values[at] < RAM_HIGH:
                    kind[at] = 'step'
                    out.append(Region(at * 4, at * 4 + 4, 'pointer', 'Animation jump target', f'0x{values[at]:08X}'))
                break
    # Pointer tables, text and padding in what is left.
    i = 0
    while i < words:
        if kind[i] is not None:
            i += 1
            continue
        j = i
        if RAM_LOW <= values[i] < RAM_HIGH:
            while j < words and kind[j] is None and RAM_LOW <= values[j] < RAM_HIGH:
                j += 1
            local = sum(1 for v in values[i:j] if inside(v))
            out.append(Region(i * 4, j * 4, 'pointer', f'Pointer table 0x{base + i * 4:08X}',
                              f'{j - i} addresses, {local} into this file and {j - i - local} into the executable.'))
        elif values[i] == 0:
            while j < words and kind[j] is None and values[j] == 0:
                j += 1
            if j - i >= 4:
                out.append(Region(i * 4, j * 4, 'padding', 'Zero fill', f'{(j - i) * 4} bytes.'))
        else:
            chunk = data[i * 4:i * 4 + 4]
            if all(32 <= c < 127 for c in chunk):
                end = i * 4
                while end < len(data) and 32 <= data[end] < 127:
                    end += 1
                if end - i * 4 >= 6:
                    text = data[i * 4:end].decode('ascii')
                    out.append(Region(i * 4, end, 'clut', 'Text', text[:80]))
                    j = (end + 3) // 4
        i = max(j, i + 1)
    return out


ANNOTATORS = {'SPR': spr, 'WMD': wmd, 'FOUR': four, 'APD': apd, 'WHM': whm, 'WPP': wpp, 'WFM': wfm,
              'INS': instructions}


def regions(kind, data, base=None):
    """Sorted, non-overlapping regions of a resource, or [] if its layout is
    unknown. `base` is where the build loads its code overlays."""
    annotator = ANNOTATORS.get(kind)
    if annotator is None:
        return []
    try:
        found = annotator(data, base) if base and annotator is instructions else annotator(data)
    except (struct.error, IndexError, ValueError):
        return []
    found.sort(key=lambda region: (region.start, region.end))
    out, at = [], 0
    for region in found:
        if region.start >= at and region.end > region.start:
            out.append(region)
            at = region.end
    return out
