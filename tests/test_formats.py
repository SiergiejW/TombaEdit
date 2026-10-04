import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from tombaedit.disc import Disc, DiscEntry, FormatError, cue_track
from tombaedit.gam import decompress
from tombaedit.catalog import Catalog, bcd, link_record
from tombaedit.ldar import parse_ldar, Project, Asset, LoadGroup, type_name
from tombaedit.graphics import rgba, texture_page, sprite_frames, render_sprite
from tombaedit.wfm import Wfm
from tombaedit.wmd import parse_wmd


def record(name, lba, size, directory=False):
    data = bytearray((33 + len(name) + 1) & ~1)
    data[0] = len(data)
    struct.pack_into("<I", data, 2, lba)
    struct.pack_into("<I", data, 10, size)
    data[25] = 2 if directory else 0
    data[32] = len(name)
    data[33:33 + len(name)] = name
    return data


def iso_fixture():
    image = bytearray(24 * 2048)
    pvd = bytearray(2048)
    pvd[:7] = b"\x01CD001\x01"
    struct.pack_into("<H", pvd, 128, 2048)
    pvd[156:190] = record(b"\0", 20, 2048, True)
    image[16 * 2048:17 * 2048] = pvd
    directory = record(b"\0", 20, 2048, True) + record(b"\1", 20, 2048, True)
    directory += record(b"HELLO.BIN;1", 21, 3000)
    image[20 * 2048:20 * 2048 + len(directory)] = directory
    payload = bytes(i % 251 for i in range(3000))
    image[21 * 2048:21 * 2048 + len(payload)] = payload
    return image, payload


class DiscTests(unittest.TestCase):
    def test_iso_and_raw_sector_modes(self):
        iso, payload = iso_fixture()
        with tempfile.TemporaryDirectory() as directory:
            for stride, skip in [(2048, 0), (2352, 16), (2352, 24)]:
                raw = bytearray(len(iso) // 2048 * stride)
                for sector in range(len(iso) // 2048):
                    raw[sector * stride + skip:sector * stride + skip + 2048] = iso[sector * 2048:(sector + 1) * 2048]
                path = Path(directory) / f"mode{skip}.bin"
                path.write_bytes(raw)
                disc = Disc(path)
                self.assertEqual(disc.read("HELLO.BIN"), payload)
                self.assertEqual(disc.read("HELLO.BIN", 700, 1800), payload[1800:2500])
                self.assertEqual(len(disc.files), 1)
                with self.assertRaises(FormatError):
                    disc.read_at(24, 1)

    def test_cue_bom_spaces_pregap_and_audio_track(self):
        iso, payload = iso_fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            raw = bytearray((len(iso) // 2048 + 150) * 2352)
            for sector in range(len(iso) // 2048):
                raw[(sector + 150) * 2352 + 24:(sector + 150) * 2352 + 2072] = iso[sector * 2048:(sector + 1) * 2048]
            (path / "data track.bin").write_bytes(raw)
            cue = path / "disc.cue"
            cue.write_text('FILE "audio.bin" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n'
                           'FILE "data track.bin" BINARY\n TRACK 02 MODE2/2352\n INDEX 00 00:00:00\n INDEX 01 00:02:00\n', encoding="utf-8-sig")
            self.assertEqual(Disc(cue).read("HELLO.BIN"), payload)

    def test_bad_disc_and_audio_only_cue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.bin"
            path.write_bytes(bytes(65536))
            with self.assertRaises(FormatError): Disc(path)
            cue = path.with_suffix(".cue")
            cue.write_text('FILE "bad.bin" BINARY\n TRACK 01 AUDIO\n INDEX 01 00:00:00\n')
            with self.assertRaises(FormatError): cue_track(cue)

    def test_cyclic_directory_rejected(self):
        iso, _ = iso_fixture()
        r = record(b"LOOP", 20, 2048, True)
        iso[20 * 2048:20 * 2048 + len(r)] = r
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "loop.iso"
            path.write_bytes(iso)
            with self.assertRaises(FormatError): Disc(path)


class GamTests(unittest.TestCase):
    def test_literal_and_overlapping_reference(self):
        data = b"GAM\0" + struct.pack("<IH", 8, 8) + b"ABC" + bytes([3, 5])
        self.assertEqual(decompress(data), b"ABCABCAB")

    def test_passthrough(self):
        self.assertEqual(decompress(b"WFM3example"), b"WFM3example")

    def test_rejects_truncation_invalid_distance_and_bomb(self):
        for data in [b"GAM\0", b"GAM\0" + struct.pack("<IH", 1, 0),
                     b"GAM\0" + struct.pack("<IH", 2, 1) + b"\x01\x02",
                     b"GAM\0" + struct.pack("<I", 0xFFFFFFFF)]:
            with self.assertRaises(FormatError): decompress(data)


class LdarTests(unittest.TestCase):
    def test_msf_is_bcd_and_includes_leadin(self):
        self.assertEqual(link_record(bytes.fromhex("00 05 73 00 b2 00 00 00"), 0), (298, 178))
        with self.assertRaises(ValueError): bcd(0xAF)

    def test_continuation_offsets_and_footer(self):
        source = DiscEntry("AREA00/A.GAM", 20, 8)
        cat = SimpleNamespace(links={1: source})
        data = struct.pack("<IHHIII", 1, 1, 0x50FF, 0, 12, 0)
        data += struct.pack("<IHHIII", 0xFFFFFFFF, 0, 0xD0FF, 0, 24, 0)
        data += struct.pack("<IHHIII", 0xFFFFFFFF, 0xFFFF, 0, 0, 0, 0)
        data += struct.pack("<II", 0, 0x80010000)
        groups = parse_ldar(data, "LDAR", cat)
        self.assertEqual([a.offset for a in groups[0].assets], [0, 12])
        self.assertEqual(groups[0].assets[1].source, source)
        self.assertTrue(groups[0].assets[1].continuation)
        with self.assertRaises(FormatError): parse_ldar(data[:-1], "LDAR", cat)

    def test_vram_section_overwrites_base_with_zero(self):
        base = Asset("LDAR", 0, 0, 1, 0x10FF, 0, None, 0, 4, (0, 0, 2, 1))
        local = Asset("LDAR", 1, 20, 2, 0x1080, 0, None, 0, 2, (1, 0, 1, 1))
        project = Project.__new__(Project)
        project.ldars = {"LDAR": [LoadGroup(0, 0, [base]), LoadGroup(1, 20, [local])]}
        project.asset_data = lambda a: b"\xFF\x7F\xFF\x7F" if a is base else b"\0\0"
        self.assertEqual(project.vram("LDAR", 1)[0, :2].tolist(), [32767, 0])
        self.assertEqual(project.vram("LDAR", 0)[0, :2].tolist(), [32767, 32767])

    def test_type_aliases(self):
        for code, name in [(0x3580, "SPR"), (0x8E80, "CLM"), (0x6080, "WPP"), (0x7080, "WHM"), (0x10FF, "GRPX")]:
            self.assertEqual(type_name(code), name)


class GraphicsTests(unittest.TestCase):
    def test_psx_zero_and_stp_black(self):
        self.assertEqual(rgba([0, 0x8000, 0x1F, 0x3E0, 0x7C00]).tolist(),
                         [[0, 0, 0, 0], [0, 0, 0, 255], [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]])

    def test_page_origin_clut_and_low_nibble_first(self):
        vram = np.zeros((512, 1024), dtype=np.uint16)
        vram[256, 64] = 0x3210
        vram[480, :4] = [0, 0x1F, 0x3E0, 0x7C00]
        image = texture_page(vram, 17, 480 << 6)
        self.assertEqual([image.getpixel((x, 0)) for x in range(4)],
                         [(0, 0, 0, 0), (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)])

    def test_sprite_page_base_and_frame_bounds(self):
        vram = np.zeros((512, 1024), dtype=np.uint16)
        vram[0, 64] = 0x1111
        vram[480, 1] = 0x1F
        part = (0, 0, 480 << 6, 3, 0, 0, 0, 0, 0, 4, 1, 3, 0, -2, -1)
        self.assertIsNone(render_sprite([part], vram).getbbox())
        self.assertEqual(render_sprite([part], vram, 1).getpixel((0, 0)), (255, 0, 0, 255))
        with self.assertRaises(FormatError): sprite_frames(b"\x01\0\x04\0")


class WfmTests(unittest.TestCase):
    @staticmethod
    def fixture(words):
        data = bytearray(160 + 2 * len(words))
        data[:16] = struct.pack("<4sIIHH", b"WFM3", 0, 156, 1, 1)
        struct.pack_into("<H", data, 144, 146)
        struct.pack_into("<4H", data, 146, 2, 1, 2, 0)
        data[154] = 0x21
        struct.pack_into("<H", data, 156, 4)
        struct.pack_into(f"<{len(words)}H", data, 160, *words)
        return data

    def test_control_argument_counts_and_glyph_flags(self):
        w = Wfm(self.fixture([0xFFFA, 100, 50, 0xFFF9, 8, 0xFFF7, 1, 0xC000, 0xFFFD, 0x8000, 0xFFFF]))
        self.assertEqual([t[0] for t in w.dialogues[0].tokens], [0xFFFA, 0xFFF9, 0xFFF7, 0xC000, 0xFFFD, 0x8000, 0xFFFF])
        self.assertEqual(w.glyphs[0].getpixel((0, 0)), (240, 240, 240, 255))
        self.assertIn("[g000*]", w.dialogues[0].script())
        self.assertFalse(w.dialogues[0].warning)
        self.assertGreater(w.render(0).height, 16)

    def test_unknown_control_stops_without_guessing_arguments(self):
        w = Wfm(self.fixture([0xFFF4, 0x8000, 0xFFFF]))
        self.assertIn("Unknown control", w.dialogues[0].warning)
        self.assertEqual(len(w.dialogues[0].tokens), 1)

    def test_invalid_glyph_pointer(self):
        data = self.fixture([0xFFFF])
        struct.pack_into("<H", data, 144, 0xFFFF)
        with self.assertRaises(FormatError): Wfm(data)


class WmdTests(unittest.TestCase):
    def test_textured_quad_triangles_and_coordinates(self):
        primitive = struct.pack("<HH4B", 0x7800, 17, 128, 128, 128, 0x2C)
        for x, y, z, u, v in [(0, 0, 0, 0, 0), (1, 0, 0, 1, 0), (0, 1, 0, 0, 1), (1, 1, 0, 1, 1)]:
            primitive += struct.pack("<hhhBB", x, y, z, u, v)
        data = struct.pack("<4I", 1, 8, 0, 1) + primitive + bytes(6 * 4)
        mesh = parse_wmd(data)[0]
        vertices, uv, colors = mesh.batches[(17, 0x7800, False)]
        self.assertEqual(len(vertices), 6)
        self.assertEqual(vertices[2].tolist(), [0, -1, 0])
        self.assertEqual(vertices[3].tolist(), [1, -1, 0])
        self.assertEqual(colors[0].tolist(), [1, 1, 1])
        with self.assertRaises(FormatError): parse_wmd(data[:-1])


if __name__ == "__main__":
    unittest.main()
