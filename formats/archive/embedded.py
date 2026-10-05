"""Older builds keep their load records and group pointers in the executable."""
import re
import struct
from formats.archive.ldar import Asset, LoadGroup, type_name


def embedded_groups(disc, catalog):
    data = disc.read(catalog.executable)
    base = struct.unpack_from('<I', data, 0x18)[0]
    found = {}

    def group(address):
        if address in found:
            return found[address]
        result = None
        at = address - base + 0x800
        source, fid, offset = None, 0, 0
        assets = []
        for pos in range(at, min(at + 20000, len(data) - 15), 20):
            if pos < 0x800:
                break
            number, code, ram, a, b = struct.unpack_from('<HHIII', data, pos)
            if number == 0xFFFF and a == b == 0:
                result = assets
                break
            if type_name(code) == 'Unknown' and code >> 12 != 9:
                break
            if number or source is None:
                fid, source, offset = number, catalog.links.get(number), 0
            if source is None:
                break
            rect = struct.unpack_from('<4H', data, pos + 8) if b and code >> 12 == 1 else None
            size = rect[2] * rect[3] * 2 if rect else a
            if not size or size > 4 * 1024 * 1024:
                break
            if rect and (not rect[2] or not rect[3] or
                         rect[0] + rect[2] > 1024 or rect[1] + rect[3] > 512):
                break
            assets.append((pos, fid, code, ram, source, offset, size, rect, not bool(number)))
            offset += size
        found[address] = result
        return result

    pointers = struct.unpack_from(f'<{(len(data)-0x800)//4}I', data, 0x800)
    out = {}
    i = 0
    while i < len(pointers):
        pointer = pointers[i]
        if not base <= pointer < base + len(data) - 0x810 or group(pointer) is None:
            i += 1; continue
        first = i
        groups = []
        while i < len(pointers) and base <= pointers[i] < base + len(data) - 0x810 and group(pointers[i]) is not None:
            groups.append((pointers[i], group(pointers[i]))); i += 1
        if len(groups) < 2 or not any(rows for _, rows in groups):
            continue
        assets = [row for _, rows in groups for row in rows]
        if not any(row[2] >> 12 in (5, 6, 7, 15) for row in assets):
            continue
        area = re.search(r'(?:^|/)AREA(\d+)(?:/)', assets[0][4].path)
        path = f'SYS/LDAR{int(area[1]):02d}.BIN' if area else 'SYS/LDSYS.BIN'
        assembled = []
        for index, (address, rows) in enumerate(groups):
            g = LoadGroup(index, address - base)
            g.assets = [Asset(path, index, pos, fid, code, ram, source, offset, size, rect, continuation)
                        for pos, fid, code, ram, source, offset, size, rect, continuation in rows]
            assembled.append(g)
        if path not in out or sum(len(g.assets) for g in assembled) > sum(len(g.assets) for g in out[path]):
            out[path] = assembled
    # Base-area pointers and section pointers are adjacent in some builds.
    # Recover their identities from the verified first source, rather than
    # treating that whole pointer run as one area's section list.
    areas = {}
    for address, rows in found.items():
        if not rows:
            continue
        name = rows[0][4].path
        match = re.search(r'(?:^|/)AREA(\d+)/(A000|B(\d+)00)\.(?:GAM|000)$', name)
        if match is None:
            continue
        area = int(match[1])
        index = 0 if match[2] == 'A000' else int(match[3]) + 1
        choices = areas.setdefault(area, {})
        if index not in choices or len(rows) > len(choices[index][1]):
            choices[index] = address, rows
    out = {key: value for key, value in out.items() if key == 'SYS/LDSYS.BIN'}
    for area, choices in areas.items():
        if 0 not in choices:
            continue
        path = f'SYS/LDAR{area:02d}.BIN'
        assembled = []
        for index in range(max(choices) + 1):
            address, rows = choices.get(index, (base, []))
            g = LoadGroup(index, address - base)
            g.assets = [Asset(path, index, pos, fid, code, ram, source, offset, size, rect, continuation)
                        for pos, fid, code, ram, source, offset, size, rect, continuation in rows]
            assembled.append(g)
        out[path] = assembled
    return out
