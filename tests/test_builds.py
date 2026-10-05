"""Formats of the 1997 builds and the per-executable address table."""
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from disc.reader import Disc, FormatError
from formats.archive.ldar import Asset, LoadGroup, Project
from formats.audio import sfx, wvd
from formats.models.wmd import parse_wmd, layout_of, primitive_size, RETAIL, EARLY
from formats.sprites.wpp import parse_wpp
from formats.text.wfm import Wfm
from game.builds import BUILDS, US_RETAIL, Executable, executable
from psx.graphics import texture_page
from tests.test_formats import iso_fixture


def early_quad():
    """One textured quad in the 1997 layout: colour, a word per corner, positions."""
    primitive = struct.pack('<4B', 128, 128, 128, 0x2C)
    for (u, v), word in zip([(0, 0), (1, 0), (0, 1), (1, 1)], (0x7800, 17, 0, 0)):
        primitive += struct.pack('<BBH', u, v, word)
    for x, y, z in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]:
        primitive += struct.pack('<hhhH', x, y, z, 0)
    return struct.pack('<4I', 1, 8, 0, 1) + primitive + bytes(6 * 4)


class EarlyWmdTests(unittest.TestCase):
    def test_corner_words_carry_uv_clut_and_page(self):
        data = early_quad()
        self.assertEqual(layout_of(data), EARLY)
        mesh = parse_wmd(data)[0]
        vertices, uv, colors = mesh.batches[(17, 0x7800, False)]
        self.assertEqual(vertices[3].tolist(), [1, -1, 0])
        self.assertAlmostEqual(float(uv[1][0]), 1.5 / 256)
        self.assertEqual(mesh.polygons[0]['kind'], 'FT4')
        with self.assertRaises(FormatError):
            parse_wmd(data, RETAIL)

    def test_primitive_sizes(self):
        self.assertEqual([primitive_size(kind, EARLY) for kind in range(4)], [40, 52, 48, 64])
        self.assertEqual([primitive_size(kind, RETAIL) for kind in range(4)], [32, 40, 40, 52])
        for kind in range(4, 8):
            self.assertEqual(primitive_size(kind, EARLY), primitive_size(kind, RETAIL))

    def test_annotation_covers_the_early_layout(self):
        from formats.annotate import regions
        data = early_quad()
        found = regions('WMD', data)
        self.assertEqual(sum(r.end - r.start for r in found), len(data))
        self.assertTrue(any(r.name.endswith('CLUT word') for r in found))


class Wfm1Tests(unittest.TestCase):
    @staticmethod
    def fixture(words):
        # A 5 x 2 glyph: each row is padded to two 16-bit words.
        rows = bytes((0x21, 0x43, 0x05, 0xEE, 0x11, 0x11, 0x01, 0x00))
        data = struct.pack('<4sIIHH', b'WFM1', 0, 34, 1, 1) + struct.pack('<H', 18)
        data += struct.pack('<4H', 0, 2, 5, 0) + rows + struct.pack('<H', 2)
        return data + struct.pack(f'<{len(words)}H', *words)

    def test_short_header_and_padded_rows(self):
        w = Wfm(self.fixture([0x0000, 0xFFFF]))
        self.assertEqual(w.version, b'WFM1')
        self.assertEqual(w.glyphs[0].size, (5, 2))
        self.assertEqual(w.indices[0], [1, 2, 3, 4, 5, 1, 1, 1, 1, 1])

    def test_f4_takes_no_arguments(self):
        w = Wfm(self.fixture([0x0000, 0xFFF4, 0x0000, 0xFFFF]))
        self.assertEqual([t[0] for t in w.dialogues[0].tokens], [0, 0xFFF4, 0, 0xFFFF])
        self.assertFalse(w.dialogues[0].warning)

    def test_annotation(self):
        from formats.annotate import regions
        found = regions('WFM', self.fixture([0x0000, 0xFFFF]))
        self.assertEqual((found[0].start, found[0].end), (0, 4))
        self.assertTrue(any('padded' in r.detail for r in found))


class EarlyContainerTests(unittest.TestCase):
    def test_wpp_can_be_one_plain_tim(self):
        palette = struct.pack('<I4H', 12 + 32, 0, 480, 16, 1) + bytes(32)
        pixels = struct.pack('<I4H', 12 + 4, 320, 0, 1, 2) + bytes((0x10, 0x32, 0x54, 0x76))
        kind, pictures = parse_wpp(struct.pack('<II', 0x10, 8) + palette + pixels)
        self.assertEqual(kind, 'tim')
        self.assertEqual((pictures[0].width, pictures[0].height), (4, 2))
        self.assertEqual(pictures[0].indices[1].tolist(), [4, 5, 6, 7])

    def test_wvd_sections_in_either_order(self):
        head = bytearray(sfx.header_length(0))
        head[:4] = sfx.MAGIC

        def section(blob):
            return struct.pack('<2I', 8, 8 + len(blob)) + bytes(blob)

        def container(first, second):
            return struct.pack('<3I', 12, 12 + len(first), 12 + len(first) + len(second)) + first + second

        later = wvd.banks(container(section(bytes(16)), section(head)))
        early = wvd.banks(container(section(head), section(bytes(16))))
        self.assertEqual(len(later), 1)
        self.assertEqual(later, early)

    def test_town_picture_and_cells_in_placement_slots(self):
        blobs = {0: struct.pack('<II', 0x10, 8) + bytes(601),          # a TIM
                 1: struct.pack('<HH', 4, 3) + bytes(4 * 3 + 1),       # a cell map
                 2: bytes(48)}                                         # a placement list
        entry = SimpleNamespace(path='D004.GAM')
        assets = [Asset('L', 1, 0, 0, code, 0, entry, n, len(blobs[n]))
                  for n, code in enumerate((0x81FF, 0x85FF, 0x80FF))]
        stub = SimpleNamespace(ldars={'L': [LoadGroup(1, 0, assets)]}, asset_data=lambda a: blobs[a.offset])
        Project.reclassify(stub)
        self.assertEqual([(a.kind, a.slot) for a in assets], [('CLM', 15), ('CLM', 14), ('APD', 0)])
        self.assertIn('CLM 81FF', assets[0].label)

    def test_reserved_texture_depth_reads_as_direct_colour(self):
        vram = np.zeros((512, 1024), dtype=np.uint16)
        vram[0, 0] = 0x1F
        self.assertEqual(texture_page(vram, 3 << 7, 0).getpixel((0, 0)), (255, 0, 0, 255))

    def test_clonecd_control_file_opens_its_image(self):
        iso, payload = iso_fixture()
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / 'disc.ccd'
            control.write_text('[CloneCD]\nVersion=3\n')
            with self.assertRaises(FormatError):
                Disc(control)
            control.with_suffix('.img').write_bytes(iso)
            self.assertEqual(Disc(control).read('HELLO.BIN'), payload)


class BuildTests(unittest.TestCase):
    def test_every_build_lists_the_same_things(self):
        for build in BUILDS.values():
            with self.subTest(build.name):
                self.assertEqual(set(build.tables), {2, 3, 4, 5, 7, 8})
                self.assertEqual((len(build.visibility), len(build.draw_queues), len(build.silent)), (6, 7, 3))
                code = (build.set_animation, build.get_clut) + build.visibility + build.draw_queues + build.silent
                self.assertEqual(len(set(code)), len(code))
                for address in code:
                    self.assertTrue(address % 4 == 0 and 0x80010000 <= address < build.overlay)
                for address in list(build.tables.values()) + [build.slot_tables, build.entrances, build.origins]:
                    self.assertTrue(address % 4 == 0 and 0x80010000 <= address < build.overlay)
                self.assertEqual(build.variant is None, build.early)
                self.assertEqual(build.event, None if build.early else build.area - 0x20)

    def test_us_retail_addresses(self):
        build = BUILDS[US_RETAIL]
        self.assertEqual((build.overlay, build.area, build.tables[2]), (0x800E7388, 0x8009BCC8, 0x800772BC))

    def test_executable_lookup_and_reads(self):
        data = bytearray(0x800 + 16)
        data[:8] = b'PS-X EXE'
        struct.pack_into('<I', data, 0x18, 0x80010000)
        struct.pack_into('<I', data, 0x808, 0x12345678)
        exe = Executable(bytes(data), BUILDS[US_RETAIL])
        self.assertEqual(exe.word(0x80010008), 0x12345678)
        self.assertTrue(exe.holds(0x8001000C, 4))
        self.assertFalse(exe.holds(0x8001000E, 4))
        project = SimpleNamespace(disc=SimpleNamespace(read=lambda path: bytes(data)),
                                  catalog=SimpleNamespace(executable='SLUS_000.00'))
        self.assertIsNone(executable(project))

    def test_area_variants_only_after_1997(self):
        from formats.level.runtime import runtime_area
        self.assertEqual([runtime_area(a, 0) for a in (7, 12, 19, 5)], [1, 4, 2, 5])
        self.assertEqual(runtime_area(19, 2), 19)
        self.assertEqual([runtime_area(a, 0, True) for a in (7, 12, 19)], [7, 12, 19])

    def test_overlay_annotation_follows_the_build(self):
        from formats.annotate import regions
        base = 0x800ED548
        words = [1, base + 8, 0x27BDFFE8, 0x0C000000, 0x03E00008, 0, base + 32, 0x80012345, 5, 0x80030000]
        names = {(r.start, r.end): r.name for r in regions('INS', struct.pack('<10I', *words), base)}
        self.assertTrue(names[(8, 24)].startswith('Function'))
        self.assertTrue(names[(32, 40)].startswith('Animation step'))


if __name__ == '__main__':
    unittest.main()
