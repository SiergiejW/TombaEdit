"""Constant CLUT uploads stored in area code, rather than GRPX resources."""
import struct
import numpy as np


def constant_uploads(code, base, load_image):
    """Read literal LoadImage calls whose RECT and source are fully known.

    This deliberately excludes runtime expressions, non-palette uploads and
    ambiguous control flow. US X09 loads the clock door's two palette rows
    at 8011C1B4 from 8012A5CC, into VRAM (128, 508, 16, 2).
    """
    words = struct.unpack_from(f'<{len(code) // 4}I', code)
    target = 0x0C000000 | ((load_image >> 2) & 0x03FFFFFF)
    uploads = []
    for at, word in enumerate(words):
        if word != target:
            continue
        registers, stack = {0: 0, 29: 0}, {}
        # Literal upload setup is a short, straight sequence. Stop at an
        # earlier branch or call so values cannot cross unrelated paths.
        start = at
        while start > max(0, at - 24):
            prior = words[start - 1]
            op = prior >> 26
            if op in (1, 2, 3, 4, 5, 6, 7) or op == 0 and prior & 63 in (8, 9):
                break
            start -= 1
        # The instruction in the call's delay slot can finish the RECT.
        for instruction in words[start:at + 2]:
            op = instruction >> 26
            rs, rt = (instruction >> 21) & 31, (instruction >> 16) & 31
            immediate = instruction & 0xFFFF
            signed = immediate - 0x10000 if immediate & 0x8000 else immediate
            source = registers.get(rs)
            if op == 15:
                registers[rt] = immediate << 16
            elif op in (8, 9, 13):
                registers[rt] = None if source is None else (
                    source | immediate if op == 13 else (source + signed) & 0xFFFFFFFF)
            elif op == 0 and instruction & 63 in (33, 37):
                rd = (instruction >> 11) & 31
                other = registers.get(rt)
                registers[rd] = None if source is None or other is None else (
                    source + other if instruction & 63 == 33 else source | other)
            elif op == 0 and instruction:
                registers[(instruction >> 11) & 31] = None
            elif op in (41, 43) and rs == 29 and source is not None:
                address, value = (source + signed) & 0xFFFFFFFF, registers.get(rt)
                for n in range(1 if op == 41 else 2):
                    if value is None:
                        stack.pop(address + n * 2, None)
                    else:
                        stack[address + n * 2] = value >> (n * 16) & 0xFFFF
            elif op not in (3, 41, 43):
                registers[rt] = None
            registers[0] = 0
        rect, pointer = registers.get(4), registers.get(5)
        if rect is None or pointer is None or any(rect + i * 2 not in stack for i in range(4)):
            continue
        x, y, width, height = (stack[rect + i * 2] for i in range(4))
        if width not in (16, 256) or not 0 < height <= 4 or x % 16 or x + width > 1024 or y + height > 512:
            continue
        offset, size = pointer - base, width * height * 2
        if 0 <= offset <= len(code) - size:
            uploads.append((x, y, width, height, code[offset:offset + size]))
    return uploads


def apply_model_palettes(resolver, vram, models):
    """Use unique overlay palette rows referenced by the loaded WMD banks."""
    if not resolver.available:
        return 0
    # These known builds use the same libgpu layout: LoadImage is FA0 bytes
    # after GetClut. Verify its prologue before interpreting any call sites.
    load_image = resolver.build.get_clut + 0xFA0
    if resolver.read(load_image, 4) != bytes.fromhex('e0ffbd27'):
        return 0
    wanted = {p['clut'] for bank in models.values() for mesh in bank
              for p in mesh.polygons if p['page'] >= 0}
    code = resolver.overlay_code
    rows = {}
    for x, y, width, height, data in constant_uploads(code, resolver.build.overlay, load_image):
        for n in range(height):
            clut = (y + n) << 6 | x >> 4
            if clut in wanted:
                rows.setdefault((x, y + n, width), set()).add(data[n * width * 2:(n + 1) * width * 2])
    applied = 0
    for (x, y, width), choices in rows.items():
        if len(choices) == 1:
            vram[y, x:x + width] = np.frombuffer(next(iter(choices)), '<u2')
            applied += 1
    return applied
