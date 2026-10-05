"""Compare the WHM decoder with US MIPS routines on a user-owned disc.

python -m tests.validate_collision "rom/Tomba! (USA).cue"
No game bytes or disassembly are stored by this test.
"""
import hashlib
import json
import struct
import sys
from collections import Counter
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, mips_const as r
from formats.archive.ldar import Project
from formats.collision.whm import parse_whm
from formats.level.runtime import US_SHA1
from formats.level.scene import loaded_resources, area_of
from formats.level.runtime import InitialPoseResolver


class Oracle:
    def __init__(self, exe):
        if hashlib.sha1(exe).hexdigest() != US_SHA1:
            raise ValueError('Collision oracle requires the verified US retail executable')
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0, 0x1000000)
        self.u.mem_map(0x1F800000, 0x1000)
        base = struct.unpack_from('<I', exe, 0x18)[0]
        self.write(base, exe[0x800:])

    def write(self, at, data):
        self.u.mem_write(at & 0x1FFFFFFF, data)

    def word(self, at, value):
        self.write(at, struct.pack('<I', value))

    def call(self, pc, *args):
        self.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
        self.u.reg_write(r.UC_MIPS_REG_RA, 0x80001000)
        for reg, value in zip((r.UC_MIPS_REG_A0, r.UC_MIPS_REG_A1, r.UC_MIPS_REG_A2, r.UC_MIPS_REG_A3), args):
            self.u.reg_write(reg, value & 0xFFFFFFFF)
        self.u.emu_start(pc, 0x80001000, count=4000)
        if self.u.reg_read(r.UC_MIPS_REG_PC) != 0x80001000:
            raise AssertionError('Collision routine did not return')
        return self.u.reg_read(r.UC_MIPS_REG_V0)

    def column(self, span):
        self.write(0x80400000, struct.pack('<HHhhH', 1, span.attribute, span.y0, span.y1, span.parameter))
        self.word(0x1F800278, 0x80400000)

    def floor_height(self, span, x):
        self.column(span)
        self.write(0x80300000, bytes(0x100))
        # Query below the floor so its computed height is returned in +16.
        y = span.height_at(x, integer=True) + 1
        self.write(0x80300016, struct.pack('<h', y))
        assert self.call(0x8004339C, 0x80300000, x, y) == 1
        return struct.unpack('<h', self.u.mem_read(0x300016, 2))[0]

    def solid(self, span, x, y):
        self.column(span)
        return bool(self.call(0x800443CC, 0x80300000, x, y))


def main(path):
    p = Project(path)
    oracle = Oracle(p.disc.read('SCUS_942.36'))
    counts = Counter()
    unique = set()
    floors, solids = [], []
    for groups in p.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind != 'WHM':
                    continue
                whm = parse_whm(p.asset_data(asset))
                counts['banks'] += 1
                counts['planes'] += len(whm.planes)
                counts['records'] += len(whm.spans)
                for s in whm.spans:
                    key = (s.attribute, s.y0, s.y1, s.parameter)
                    if key in unique:
                        continue
                    unique.add(key)
                    if not s.wall and s.attribute & 1 and len(floors) < 1200:
                        floors.append(s)
                    if s.wall and s.y1 <= 0 and len(solids) < 1200:
                        solids.append(s)
    for s in floors:
        for x in range(8):
            expected = s.height_at(x, integer=True)
            actual = oracle.floor_height(s, x)
            assert actual == expected, (s, x, expected, actual)
            counts['floor_height_checks'] += 1
    for s in solids:
        for x in (s.start - 1, s.start, s.start + s.length, s.start + s.length + 1):
            if not 0 <= x < 8:
                continue
            for y in (s.y0 + s.y1 - 1, s.y0 + s.y1, s.y0, s.y0 + 1):
                expected = s.start <= x <= s.start + s.length and s.y0 + s.y1 <= y <= s.y0
                actual = oracle.solid(s, x, y)
                assert actual == expected, (s, x, y, expected, actual)
                counts['solid_boundary_checks'] += 1
    # Verify the section's path/depth transform and the origin tables against
    # the game's actual pointer lookup, including the mansion's turned walls.
    oracle.word(0x800A53DC, 0x80300000)
    oracle.write(0x80300000, bytes(16))   # Phoenix mountain's default route
    oracle.write(0x800A38E4, struct.pack('<hh', -30000, 30000))
    for path, groups in p.ldars.items():
        area = area_of(path)
        if area < 0:
            continue
        for group in groups[1:]:
            resources = loaded_resources(p, path, group.index)
            resolver = InitialPoseResolver(p, area, group.index - 1, resources)
            if not resolver.available:
                continue
            x0, z0, turned, only = resolver.collision_frame(area, group.index - 1)
            oracle.write(0x8009BCC8, struct.pack('<HH', area, group.index - 1))
            oracle.write(0x1F8001C8, struct.pack('<H', int(turned)))
            for slot in (0, 1):
                oracle.word(0x1F800308 + slot * 4, 0)
                if ('WHM', slot) in resources:
                    asset = resources['WHM', slot]
                    address = 0x80C00000 + slot * 0x20000
                    oracle.write(address, p.asset_data(asset))
                    oracle.word(0x1F800308 + slot * 4, address)
            for (kind, slot), asset in resources.items():
                if kind != 'WHM' or only not in (None, slot):
                    continue
                # Except the special mountain transition route, non-village
                # collision lookup uses slot 0 only.
                if area != 0 and only is None and slot != 0:
                    continue
                data = p.asset_data(asset)
                whm = parse_whm(data)
                deeper = 270 if area == 0 and group.index < 4 and slot == 0 and ('WHM', 1) in resources else 0
                for plane in whm.planes:
                    column = min(12, len(plane.columns) - 1)
                    depth = z0 + deeper + plane.index * 90 * (-1 if turned else 1)
                    # Single-plane turned rooms clamp depth, so their chosen
                    # display slice can be the entrance position instead.
                    probe_depth = depth + (-1 if turned else 1)
                    if area == 0 and group.index != 4 and slot == 1 and plane.index == 3:
                        probe_depth = depth  # the near bank includes the Z=270 boundary itself
                    actual = oracle.call(0x80042654, x0 + column * 8, probe_depth)
                    table = struct.unpack_from('<H', data, 8 + plane.index * 2)[0]
                    expected = (0x80C00000 + slot * 0x20000 + table +
                                struct.unpack_from('<H', data, table + column * 2)[0])
                    assert actual == expected, (path, group.index, slot, plane.index,
                                                x0, z0, turned, hex(actual), hex(expected))
                    counts['section_lookup_checks'] += 1
            if area == 3 and group.index in (2, 6) and ('WHM', 1) in resources:
                oracle.write(0x80300002, struct.pack('<h', -1))
                ax, az, turned, slot = resolver.collision_frame(area, group.index - 1, alternate=True)
                data = p.asset_data(resources['WHM', slot])
                for plane in parse_whm(data).planes:
                    table = struct.unpack_from('<H', data, 8 + plane.index * 2)[0]
                    actual = oracle.call(0x80042654, ax + 96, az + plane.index * 90 + 1)
                    expected = 0x80C00000 + slot * 0x20000 + table + struct.unpack_from('<H', data, table + 24)[0]
                    assert actual == expected, ('alternate', path, group.index, plane.index, hex(actual), hex(expected))
                    counts['alternate_route_checks'] += 1
                oracle.write(0x80300002, bytes(2))
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
