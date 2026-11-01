"""Check CAR recognition, LDAR footer validation and user-supplied Special Edition images.

Run: python tools/validate_special_edition.py [--scenes] [IMAGE.car ...]
Use --unit-only to run the synthetic format regressions without any game data.
"""
import argparse
from collections import Counter
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from disc.reader import DISC_SUFFIXES, Disc, DiscEntry, FormatError
from formats.archive.ldar import Project, parse_ldar, table_name
from game.catalog import Catalog
from game.builds import executable


class FormatRegressions(unittest.TestCase):
    def test_car_requires_a_valid_disc(self):
        raw = bytearray(20 * 2352)
        pvd = 16 * 2352 + 24
        raw[pvd:pvd + 7] = b'\x01CD001\x01'
        raw[pvd + 40:pvd + 72] = b'CAR TEST'.ljust(32, b' ')
        struct.pack_into('<H', raw, pvd + 128, 2048)
        record = bytearray(34)
        record[0], record[25], record[32] = 34, 2, 1
        struct.pack_into('<I', record, 2, 18)
        struct.pack_into('<I', record, 10, 2048)
        raw[pvd + 156:pvd + 190] = record
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.car'
            path.write_bytes(raw)
            disc = Disc(path)
            self.assertEqual((disc.stride, disc.payload_offset, disc.volume), (2352, 24, 'CAR TEST'))
            self.assertIn('.car', DISC_SUFFIXES)
            path.write_bytes(bytes(len(raw)))
            with self.assertRaises(FormatError):
                Disc(path)

    def test_null_terminated_footer_preserves_group_boundaries(self):
        catalog = Catalog('', 0, {1: DiscEntry('DATA.BIN', 0, 4)}, 1)
        asset = struct.pack('<IHHIII', 0, 1, 0x3000, 0, 4, 0)
        end = struct.pack('<IHHIII', 0, 0xFFFF, 0, 0, 0, 0)
        data = (asset + end) * 2 + bytes(4) + struct.pack('<II', 0x80090000, 0x80090028)
        ordinary = parse_ldar(data, 'SYS/LDAR13.BIN', catalog)
        terminated = parse_ldar(data + bytes(4), 'SYS/LDAR13.BIN', catalog)
        self.assertEqual([g.offset for g in ordinary], [g.offset for g in terminated])
        self.assertEqual([len(g.assets) for g in terminated], [1, 1])
        malformed = data[:-4] + struct.pack('<I', 0x8009002C) + bytes(4)
        with self.assertRaises(FormatError):
            parse_ldar(malformed, 'SYS/LDAR13.BIN', catalog)
        with self.assertRaises(FormatError):
            parse_ldar(data + bytes(8), 'SYS/LDAR13.BIN', catalog)


def validate(path, scenes=False):
    project = Project(path)
    if project.warnings:
        raise AssertionError(project.warnings)
    assert project.edition is not None, (path, 'not one of the audited complete CAR images')
    languages = sorted(project.catalogs, key=lambda n: -1 if n is None else n)
    expected = 180 if languages == list(range(9)) else 20
    assert len(project.ldars) == expected, (path, len(project.ldars))
    kinds = Counter()
    for groups in project.ldars.values():
        for group in groups:
            for asset in group.assets:
                assert asset.source is not None, asset.label
                project.asset_data(asset)
                kinds[asset.kind] += 1
    for language in languages:
        table = next(t for t in project.ldars if table_name(t) == (language, 0))
        program = executable(project, table)
        assert program is not None, (path, language, 'unknown engine')
        if scenes:
            from formats.level.runtime import InitialPoseResolver
            from formats.level.scene import loaded_resources
            resolver = InitialPoseResolver(project, 0, 0, loaded_resources(project, table, 1))
            assert resolver.available, resolver.reason
            slots = resolver.placement_slots(0, 0)
            assert slots and all(0 <= n < 16 for n in slots), slots
    if scenes:
        from formats.level.scene import build_scene
        first = 'SYS/LD0AR00.BIN' if len(languages) > 1 else 'SYS/LDAR00.BIN'
        scene = build_scene(project, first, 1)
        assert scene.entries and any(e.category == 'Sprites' for e in scene.entries)
        assert any('Initial poses traced' in note for note in scene.notes), scene.notes
        if project.edition.region == 'Japan':
            ending = build_scene(project, 'SYS/LDAR13.BIN', 2)
            assert ending.entries
    print(f'{Path(path).name}: {len(project.disc.files)} files, {len(project.ldars)} load tables, '
          f'{sum(kinds.values())} readable resources, {len(languages)} recognized engine(s)'
          + ('; scene checks passed' if scenes else ''), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='*', type=Path)
    parser.add_argument('--scenes', action='store_true')
    parser.add_argument('--unit-only', action='store_true')
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FormatRegressions))
    if not result.wasSuccessful():
        return 1
    if not args.unit_only:
        images = args.images or [ROOT / 'rom' / 'Special Edition' / f't_data_{region}.car' for region in ('u', 'j', 'e')]
        for path in images:
            validate(path, args.scenes)
    return 0


if __name__ == '__main__':
    sys.exit(main())
