"""The console's stock formats and the archives other games wrap them in."""
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from disc.reader import FormatError
from formats.archive import bpe, containers, lzss
from formats.audio import seq, sfx, smf, sources, vab, xa
from formats.images import save_icon, tim
from formats.models import tmd
from formats.movie import mdec


def tim_file(depth=4, palettes=2, width=8, height=2, at=(320, 0)):
    """A TIM with a pixel ramp; indexed ones get `palettes` palettes."""
    flags = {4: 0, 8: 1, 15: 2, 24: 3}[depth]
    out = b''
    if depth in (4, 8):
        colours = 16 if depth == 4 else 256
        words = np.arange(colours * palettes, dtype='<u2') | 0x8000
        out += struct.pack('<I4H', 12 + words.size * 2, 0, 480, colours, palettes) + words.tobytes()
        flags |= 8
    stored = {4: width // 4, 8: width // 2, 15: width, 24: width * 3 // 2}[depth]
    pixels = (np.arange(stored * height, dtype='<u2') * 0x1111 if depth == 4 else
              np.arange(stored * height, dtype='<u2'))
    out += struct.pack('<I4H', 12 + pixels.size * 2, at[0], at[1], stored, height) + pixels.tobytes()
    return struct.pack('<II', tim.MAGIC, flags) + out


def bank(sizes=(48, 32), programs=1):
    """(header, body) of a VAB whose waveforms are silent blocks."""
    head = bytearray(sfx.header_length(programs))
    head[:4] = sfx.MAGIC
    struct.pack_into('<HHH', head, 18, programs, len(sizes), len(sizes))
    head[sfx.HEADER] = 1                                    # program 0 has one tone
    tone = sfx.HEADER + sfx.PROGRAM_TABLE
    head[tone + 4], head[tone + 6], head[tone + 7] = 60, 0, 127     # centre, key range
    struct.pack_into('<hh', head, tone + 20, 0, 1)                  # program 0, waveform 1
    for n, size in enumerate(sizes):
        struct.pack_into('<H', head, len(head) - sfx.SIZE_TABLE + 2 + n * 2, size // 8)
    body = bytearray()
    for size in sizes:
        blocks = bytearray(size)
        blocks[16:18] = b'\x0c\x00'
        blocks[size - 15] = 1                               # last block ends the waveform
        body += blocks
    return bytes(head), bytes(body)


def sequence(version=1):
    events = bytes((0, 0xC0, 0, 0, 0x90, 60, 100, 96, 0x90, 60, 0, 0, 0xFF, 0x2F, 0))
    head = b'pQES' + struct.pack('>I', version) + b'\x01\xe0\x07\xa1\x20\x04\x02'
    return head + (struct.pack('>I', len(events)) if version == 0 else b'') + events


class TimTests(unittest.TestCase):
    def test_every_depth_and_palette(self):
        four = tim.parse(tim_file(4))
        self.assertEqual((four.width, four.height, four.depth, len(four.palettes)), (8, 2, 4, 2))
        self.assertEqual(four.indices()[0].tolist(), [0, 0, 0, 0, 1, 1, 1, 1])
        self.assertNotEqual(four.image(0).getpixel((4, 0)), four.image(1).getpixel((4, 0)))
        eight = tim.parse(tim_file(8, 1))
        self.assertEqual((eight.width, eight.indices()[0, :4].tolist()), (8, [0, 0, 1, 0]))
        self.assertEqual(tim.parse(tim_file(15)).image().size, (8, 2))
        self.assertEqual(tim.parse(tim_file(24, width=4)).image().getpixel((0, 0)), (0, 0, 1, 255))
        self.assertIn('2 palettes', four.describe())

    def test_rejects_what_is_not_one(self):
        for data in (b'', b'\x10\0\0\0', tim_file()[:-2], struct.pack('<II', tim.MAGIC, 0x40) + bytes(40)):
            with self.assertRaises(FormatError):
                tim.parse(data)

    def test_found_inside_other_data_and_uploaded(self):
        picture = tim_file(4)
        found = tim.find(b'\x10\0\0\0junk' + picture + bytes(7) + picture)
        self.assertEqual([t.offset for t in found], [8, 8 + len(picture) + 7])
        vram = np.zeros((512, 1024), np.uint16)
        tim.upload(vram, found[0])
        self.assertEqual(int(vram[0, 321]), 0x1111)
        self.assertEqual(int(vram[480, 1]), 0x8001)

    def test_blocks_stored_without_the_header(self):
        full = tim_file(8, 1, width=16, height=4)
        palette = full[8:8 + 524]
        bare = palette + full[8 + 524 + 4:]                 # no magic, flags or pixel length
        self.assertEqual(tim.wrap(bare), full)
        rectangle = struct.pack('<4H', 0, 0, 8, 2) + bytes(32)
        self.assertEqual(tim.parse(tim.wrap(rectangle)).depth, 15)
        self.assertEqual(tim.wrap(bytes(64)), b'')


class PackingTests(unittest.TestCase):
    def test_lzss_literals_references_and_early_stop(self):
        # Five literals, then three zeros from the ring, as the head of a
        # TIM packs: 10 00 00 00 08 | 00 00 00.
        packed = bytes((0x1F, 0x10, 0, 0, 0, 0x08, 0xEF, 0xF0))
        self.assertEqual(lzss.decompress(packed), bytes((0x10, 0, 0, 0, 8, 0, 0, 0)))
        self.assertEqual(lzss.decompress(packed, stop=2)[:2], b'\x10\0')
        # An overlapping reference repeats what it is still writing.
        self.assertEqual(lzss.decompress(bytes((0x01, 0x41, 0xEE, 0xF2))), b'AAAAAA')

    def test_byte_pairs(self):
        # Value 'B' stands for "AA" and 'C' for "BB"; every other is itself.
        table = bytes((0xC1, 0x41, 0x41, 0x00, 0x42, 0x42, 0xFF, 0xC4, 0xBA))
        block = table + b'\x00\x03' + b'C!A'
        packed = bpe.MAGIC + struct.pack('<I', 4 + len(block)) + block
        self.assertEqual(bpe.expand(packed), b'AAAA!A')
        self.assertEqual(bpe.expand(packed, stop=2)[:2], b'AA')
        with self.assertRaises(FormatError):
            bpe.expand(b'LZSS' + packed[4:])
        with self.assertRaises(FormatError):
            bpe.expand(packed[:-4])


class BankTests(unittest.TestCase):
    def test_header_and_body_in_one_piece_or_two(self):
        head, body = bank()
        self.assertEqual(vab.waveform_sizes(head), [48, 32])
        whole, used = vab.whole(head + body)
        self.assertEqual(used, len(head) + len(body))
        self.assertEqual(whole, vab.canonical(head, body))
        self.assertEqual([size for _, _, _, size in sfx.samples(whole)], [48, 32])
        # Padding between the two is not a body; the search finds where it is.
        padded = head + bytes(0x1E0) + body
        self.assertIsNone(vab.whole(padded))
        self.assertEqual(vab.find_body(padded), len(head) + 0x1E0)
        self.assertEqual(vab.header_size(b'pBAV' + bytes(8)), 0)

    def test_bank_source_rows_and_sound(self):
        head, body = bank()
        source = sources.BankSource('Bank', vab.canonical(head, body))
        rows = source.rows()
        self.assertEqual([row.cells[0] for row in rows], ['Waveform 001', 'Waveform 002'])
        self.assertEqual(rows[0].cells[-1], 'P0')
        self.assertEqual(len(rows[0].preview()), 28 * 3)
        self.assertTrue(source.play(0, 22050).startswith(b'RIFF'))
        self.assertIn(('Loops', 'No'), source.details(0))

    def test_sequence_ranks_the_bank_that_has_its_notes(self):
        head, body = bank()
        good = vab.canonical(head, body)
        empty = bytearray(good)
        empty[sfx.HEADER] = 0                               # no program at all
        found = sources.sequence_sources(sequence(), 'Tune', [('A/EMPTY.VH', bytes(empty)), ('A/GOOD.VH', good)])
        self.assertEqual([s.name for s in found], ['A/GOOD.VH'])
        self.assertEqual(found[0].rows()[0].cells, ('Program 0', '1', '60 to 60', '1 tone'))
        self.assertTrue(found[0].midi().startswith(b'MThd'))
        nothing = sources.sequence_sources(sequence(), 'Tune', [])
        self.assertEqual(nothing[0].summary, 'no bank')
        with self.assertRaises(ValueError):
            nothing[0].play(0, 0)


class SequenceTests(unittest.TestCase):
    def test_version_0_loses_its_length_word(self):
        new, old = sequence(1), sequence(0)
        self.assertEqual(containers.sequence(old), (new, len(old)))
        self.assertEqual(containers.sequence(b'junk' + new + bytes(9), 4), (new, len(new)))
        self.assertEqual(containers.sequence(b'pQES' + bytes(30)), (b'', 0))

    def test_midi_tracks_merge_into_one(self):
        def track(*events):
            body = b''.join(events) + b'\x00\xff\x2f\x00'
            return b'MTrk' + struct.pack('>I', len(body)) + body
        file = (b'MThd' + struct.pack('>IHHH', 6, 1, 2, 96)
                + track(b'\x00\xff\x51\x03\x06\x1a\x80', b'\x00\xff\x03\x04Name')
                + track(b'\x00\xc0\x05', b'\x60\x90\x3c\x64', b'\x60\x3c\x00'))
        music = smf.to_seq(file)
        self.assertEqual(seq.header(music, 0), (96, 400000))
        self.assertEqual(seq.events(music, 0), [(0, 0xFF, 400000, 0), (0, 0xC0, 5, 0),
                                                (96, 0x90, 60, 100), (96, 0x90, 60, 0)])
        with self.assertRaises(FormatError):
            smf.to_seq(b'RIFF' + bytes(20))


class ModelTests(unittest.TestCase):
    @staticmethod
    def model():
        vertices = b''.join(struct.pack('<4h', x, y, 0, 0) for x, y in ((0, 0), (8, 0), (0, 8), (8, 8)))
        normals = struct.pack('<4h', 0, 0, 4096, 0)
        flat = bytes((4, 3, 0, 0x20)) + bytes((255, 0, 0, 0x20)) + struct.pack('<4H', 0, 0, 1, 2)
        textured = (bytes((9, 7, 1, 0x2D))
                    + struct.pack('<BBH', 0, 0, 0x7800) + struct.pack('<BBH', 7, 0, 5)
                    + struct.pack('<BBH', 0, 7, 0) + struct.pack('<BBH', 7, 7, 0)
                    + bytes((128, 128, 128, 0)) + struct.pack('<4H', 0, 1, 2, 3))
        primitives = flat + textured
        record = struct.pack('<6Ii', 28, 4, 28 + len(vertices), 1, 28 + len(vertices) + len(normals), 2, 0)
        return struct.pack('<3I', tmd.MAGIC, 0, 1) + record + vertices + normals + primitives

    def test_lit_and_unlit_primitives(self):
        data = self.model()
        self.assertEqual(tmd.size(data), len(data))
        mesh = tmd.parse(data)[0]
        self.assertEqual([p['kind'] for p in mesh.polygons], ['F3', 'FT4'])
        flat, textured = mesh.polygons
        self.assertEqual(flat['vertices'], [(0, 0, 0), (8, 0, 0), (0, -8, 0)])
        self.assertEqual((textured['page'], textured['clut']), (5, 0x7800))
        self.assertEqual(len(mesh.batches[(5, 0x7800, False)][0]), 6)
        self.assertEqual(mesh.batches[(-1, 0, False)][2][0].tolist(), [1, 0, 0])

    def test_rejects_addresses_and_short_files(self):
        data = bytearray(self.model())
        self.assertIsNone(tmd.objects(data[:30]))
        data[4] = 1                                         # offsets already memory addresses
        with self.assertRaises(FormatError):
            tmd.parse(bytes(data))


class ContainerTests(unittest.TestCase):
    def test_pair_table_with_packed_pictures(self):
        picture = tim_file(4)
        packed = b''.join(bytes((0xFF,)) + picture[i:i + 8] for i in range(0, len(picture), 8))
        table = struct.pack('<4I', 16, len(packed), 16 + len(packed), len(packed))
        layout, items = containers.contents(table + packed + packed)
        self.assertEqual(layout, 'pairs')
        self.assertEqual([(i.kind, i.packed, i.data) for i in items], [('TIM', 'LZSS', picture)] * 2)
        self.assertIn('8 x 2, 4-bit', items[0].note)

    def test_counted_table_joins_header_and_body(self):
        head, body = bank()
        first = 0x800
        second = first + len(head) + 0x60                   # padded apart, as on a disc
        total = second + len(body)
        table = struct.pack('<6I', 2, total, first, len(head), second, len(body))
        data = table + bytes(first - len(table)) + head + bytes(0x60) + body
        layout, items = containers.contents(data)
        self.assertEqual(layout, 'counted')
        self.assertEqual([i.kind for i in items], ['VAB', 'VAB body'])
        self.assertEqual(vab.whole(items[0].data)[0], vab.canonical(head, body))

    def test_named_sector_index(self):
        music = sequence()
        header = bytearray(2048)
        header[8:12] = b'Indx'
        struct.pack_into('<I', header, 16, 1)
        struct.pack_into('<12s3I', header, 0x20, b'TUNE.SEQ', 1, 1, len(music))
        layout, items = containers.contents(bytes(header) + music + bytes(2048 - len(music)))
        self.assertEqual((layout, items[0].name, items[0].kind, items[0].data), ('LVL', 'TUNE.SEQ', 'SEQ', music))

    def test_search_without_any_index(self):
        picture, model = tim_file(8, 1), ModelTests.model()
        data = b'\xAA' * 12 + picture + b'\xAA' * 8 + model + b'\xAA' * 4 + sequence()
        layout, items = containers.contents(data)
        self.assertIsNone(layout)
        self.assertEqual([(i.kind, i.offset) for i in items],
                         [('TIM', 12), ('TMD', 20 + len(picture)), ('SEQ', 24 + len(picture) + len(model))])

    def test_what_a_file_starts_with(self):
        head, body = bank()
        self.assertEqual([containers.sniff(d) for d in (tim_file(), head, head + body, sequence(), b'MThd' + bytes(20),
                                                        ModelTests.model(), b'PS-X EXE' + bytes(8), bytes(64))],
                         ['TIM', 'VAB header', 'VAB', 'SEQ', 'MIDI', 'TMD', 'EXE', 'Data'])


class StreamTests(unittest.TestCase):
    @staticmethod
    def sector(submode=0, coding=0, channel=0, body=b''):
        raw = bytearray(xa.SECTOR)
        raw[:12] = sources.SYNC
        raw[16:20] = raw[20:24] = bytes((1, channel, submode, coding))
        raw[24:24 + len(body)] = body
        return bytes(raw)

    def image(self, sectors):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'track.bin'
        path.write_bytes(b''.join(sectors))
        disc = SimpleNamespace(stride=xa.SECTOR, path=path, start=0)
        return disc, SimpleNamespace(path='FILE', lba=0, size=len(sectors) * 2048)

    def test_reserved_coding_values_read_as_the_default(self):
        self.assertEqual(xa.coding(0x00), (1, 37800, 4))
        self.assertEqual(xa.coding(0x05), (2, 18900, 4))
        self.assertEqual(xa.coding(0xE8), (1, 37800, 4))
        self.assertEqual(xa.coding(0x11), (2, 37800, 8))

    def test_sound_alone_video_and_cd_audio(self):
        audio, empty = self.sector(0x64), self.sector()
        video = self.sector(0x48, body=b'\x60\x01\x01\x80')
        self.assertEqual(sources.stream_kind(*self.image([audio, empty, empty, empty] * 4)), 'xa')
        self.assertEqual(sources.stream_kind(*self.image([video, video, audio, video] * 4)), 'movie')
        self.assertEqual(sources.stream_kind(*self.image([bytes(range(256)) * 9 + bytes(48)] * 4)), 'cdda')
        self.assertEqual(sources.stream_kind(*self.image([self.sector(0x08)] * 4)), '')

    def test_channels_split_into_clips(self):
        # Channel 0 plays, ends a record, then plays again; channel 1 runs through.
        order = [(0, 0x64), (1, 0x64), (0, 0xE4), (1, 0x64), (0, 0x64), (1, 0x64), (0, 0x64), (1, 0x64)]
        disc, entry = self.image([self.sector(submode, 0, channel) for channel, submode in order])
        source = sources.XaSource('FILE', disc.path, 0, len(order))
        self.assertEqual([row.cells[0] for row in source.rows()],
                         ['Channel 0, clip 1', 'Channel 0, clip 2', 'Channel 1'])
        self.assertEqual([len(clip[3]) for clip in source.clips], [2, 2, 4])
        self.assertTrue(source.play(2, 0).startswith(b'RIFF'))


class MovieTests(unittest.TestCase):
    def test_version_3_codes_the_dc_as_a_difference(self):
        # Six blocks of one macroblock, each a size code, its bits and an
        # end of block. Luma size 2 is "01"; chroma size 0 is "00".
        bits = '00' + '10' + '00' + '10' + '01' + '11' + '10' + ('100' + '10') * 3
        bits += '0' * (-len(bits) % 16)
        body = b''.join(int(bits[i:i + 16], 2).to_bytes(2, 'little') for i in range(0, len(bits), 16))
        blocks = mdec._decode_blocks(mdec._Bits(body), 6, 1, True)
        self.assertEqual(blocks[:, 0].tolist(), [1024, 1024, 1048, 1048, 1048, 1048])
        frame = struct.pack('<4H', 1, 0x3800, 1, 3) + body
        self.assertEqual(mdec.decode(frame, 16, 16).shape, (16, 16, 3))


class SaveIconTests(unittest.TestCase):
    def test_title_and_frames(self):
        data = bytearray(0x180)
        data[:4] = b'SC\x12\x01'
        data[4:8] = 'テス'.encode('shift_jis')
        struct.pack_into('<2H', data, 0x60, 0, 0x801F)
        data[0x80] = 0x10
        self.assertEqual(save_icon.title(data), 'テス')
        pictures = save_icon.icons(data)
        self.assertEqual(len(pictures), 2)
        self.assertEqual(pictures[0].getpixel((1, 0)), (255, 0, 0, 255))
        self.assertEqual(save_icon.sheet(data, 2).size, (72, 32))


if __name__ == '__main__':
    unittest.main()
