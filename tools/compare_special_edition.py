"""Compare local Special Edition CAR discs with the three retail references.

Run from the checkout with ``python tools/compare_special_edition.py``. ROM bytes
are never written. The JSON records file hashes, decompressed content, LDAR asset
hashes, and Form 2 data beyond the 2048 bytes an ordinary ISO reader returns.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from disc.reader import Disc
from formats.archive.gam import decompress
from formats.archive.ldar import Project
from formats.text.wfm import Wfm


IMAGES = {
    'retail-jp': 'Ore! Tomba (Japan).cue',
    'retail-us': 'Tomba! (USA).cue',
    'retail-eu': 'Tombi! (Europe) (En,Es,Pt,Sv,Da).cue',
    'special-j': 'Special Edition/t_data_j.car',
    'special-u': 'Special Edition/t_data_u.car',
    'special-e': 'Special Edition/t_data_e.car',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sector_payload(raw, position, stride, offset):
    """User data only: omit sync/MSF/EDC/ECC, retain all 2324 Form 2 bytes."""
    if stride == 2048:
        return raw[position:position + 2048], b''
    subheader = raw[position + 16:position + 24] if offset == 24 else b''
    form2 = offset == 24 and bool(raw[position + 18] & 0x20)
    length = 2324 if form2 else 2048
    return raw[position + offset:position + offset + length], subheader


def ranges(values):
    result = []
    for value in values:
        if result and result[-1][1] + 1 == value:
            result[-1][1] = value
        else:
            result.append([value, value])
    return result


def inspect_image(path, name):
    disc = Disc(path)
    record = dict(source=IMAGES[name], bytes=disc.byte_size, stride=disc.stride,
                  payload_offset=disc.payload_offset, files={}, assets={}, warnings=[])
    sector_hashes = set()
    uncovered = []
    with disc.path.open('rb') as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as raw:
        record['image_sha256'] = sha(raw)
        sectors = (len(raw) // disc.stride) - disc.start
        covered = bytearray(sectors)
        directories = bytearray(sectors)
        for entry in [disc.root, *disc.entries.values()]:
            count = (entry.size + 2047) // 2048
            bitmap = directories if entry.directory else covered
            for lba in range(entry.lba, min(sectors, entry.lba + count)):
                bitmap[lba] = 1
            if entry.directory:
                continue
            data = disc.read(entry)
            decoded = decompress(data)
            stream = hashlib.sha256()
            subheaders = hashlib.sha256()
            form2 = 0
            for index in range(count):
                position = (disc.start + entry.lba + index) * disc.stride
                payload, subheader = sector_payload(raw, position, disc.stride, disc.payload_offset)
                if len(payload) == 2324:
                    form2 += 1
                else:
                    payload = payload[:min(2048, entry.size - index * 2048)]
                stream.update(payload)
                subheaders.update(subheader)
            item = dict(lba=entry.lba, size=entry.size, sha256=sha(data),
                        decoded_size=len(decoded), decoded_sha256=sha(decoded),
                        stream_sha256=stream.hexdigest(), form2_sectors=form2,
                        subheaders_sha256=subheaders.hexdigest())
            if data.startswith(b'PS-X EXE'):
                item['executable_sha1'] = hashlib.sha1(data).hexdigest()
            record['files'][entry.path] = item
        sector_types = Counter()
        for lba in range(sectors):
            position = (disc.start + lba) * disc.stride
            payload, _ = sector_payload(raw, position, disc.stride, disc.payload_offset)
            digest = sha(payload)
            sector_hashes.add(digest)
            if not covered[lba]:
                category = 'system' if lba < 16 else 'directory' if directories[lba] else 'other'
                sector_types[category] += 1
                if any(payload):
                    uncovered.append((lba, category, digest))
        record['sector_count'] = sectors
        record['non_file_sector_counts'] = dict(sector_types)
        record['uncovered_nonzero_sector_count'] = len(uncovered)
        record['trailing_partial_sector_bytes'] = len(raw) % disc.stride
    project = Project(path)
    record['warnings'] = project.warnings
    for table, groups in project.ldars.items():
        for group in groups:
            for index, asset in enumerate(group.assets):
                key = f'{table}:{group.index}:{index}:{asset.kind}:{asset.code:04X}'
                try:
                    data = project.asset_data(asset)
                    item = dict(kind=asset.kind, code=asset.code, source=asset.source.path,
                                offset=asset.offset, size=len(data), sha256=sha(data))
                    if asset.kind == 'WFM':
                        wfm = Wfm(data)
                        # Tokens establish script equality independently of glyph artwork.
                        item['dialogue_count'] = len(wfm.dialogues)
                        item['dialogue_tokens_sha256'] = sha(json.dumps(
                            [d.tokens for d in wfm.dialogues], separators=(',', ':')).encode())
                        item['glyph_count'] = len(wfm.glyphs)
                        item['glyph_pixels_sha256'] = sha(b''.join(
                            struct.pack('<HH', *image.size) + bytes(indices)
                            for image, indices in zip(wfm.glyphs, wfm.indices)))
                    record['assets'][key] = item
                except Exception as error:
                    record['warnings'].append(f'{key}: {error}')
    return record, sector_hashes, uncovered


def compare(edition, reference, field):
    left, right = edition[field], reference[field]
    common = left.keys() & right.keys()
    changed = sorted(key for key in common if left[key]['sha256'] != right[key]['sha256'])
    result = dict(identical=len(common) - len(changed), changed=changed,
                  added=sorted(left.keys() - right.keys()), removed=sorted(right.keys() - left.keys()))
    if field == 'files':
        result['decoded_identical'] = sum(left[k]['decoded_sha256'] == right[k]['decoded_sha256'] for k in common)
        result['compression_only'] = [k for k in changed if left[k]['decoded_sha256'] == right[k]['decoded_sha256']]
        result['stream_changed'] = sorted(k for k in common if left[k]['stream_sha256'] != right[k]['stream_sha256'])
        result['form2_stream_changed'] = [k for k in result['stream_changed']
                                          if left[k]['form2_sectors'] or right[k]['form2_sectors']]
        result['subheaders_changed'] = sorted(k for k in common if left[k]['subheaders_sha256'] != right[k]['subheaders_sha256'])
    else:
        result['changed_by_kind'] = dict(Counter(left[k]['kind'] for k in changed))
        result['wfm_changes'] = {
            k: {property: [right[k].get(property), left[k].get(property)]
                for property in ('dialogue_count', 'glyph_count', 'dialogue_tokens_sha256',
                                 'glyph_pixels_sha256')
                if left[k].get(property) != right[k].get(property)}
            for k in changed if left[k]['kind'] == 'WFM'}
    return result


def audit(rom_root):
    report = dict(schema=1, method={
        'files': 'SHA-256 of ISO file bytes and GAM-decoded bytes, at declared length.',
        'streams': 'Full 2324-byte Mode 2 Form 2 payload; 2048-byte Form 1 payload, cropped at file end. MSF/EDC/ECC excluded; subheaders hashed separately.',
        'assets': 'Every LDAR asset occurrence, matched by table, group, position, kind and code. WFM token and glyph hashes separate script and font changes.',
        'unallocated': 'All non-file sector user payloads, including system/directories/gaps/trailer. New-sector hashes compared with every sector of all three retail references. Novel metadata is not evidence of a new asset.',
        'limits': 'Only these six supplied files; does not inspect assets outside the CAR discs, prove trigger reachability, or identify the visual meaning of every changed pixel.'},
                  images={}, comparisons={}, cross_retail={})
    sector_sets, uncovered = {}, {}
    for name, relative in IMAGES.items():
        print(f'Inspecting {relative}', flush=True)
        record, sector_sets[name], uncovered[name] = inspect_image(rom_root / relative, name)
        report['images'][name] = record
    retail_sectors = set().union(*(sector_sets[name] for name in IMAGES if name.startswith('retail-')))
    for name in ('special-j', 'special-u', 'special-e'):
        edition = report['images'][name]
        report['comparisons'][name] = {}
        for other in ('retail-jp', 'retail-us', 'retail-eu'):
            report['comparisons'][name][other] = {
                field: compare(edition, report['images'][other], field) for field in ('files', 'assets')}
        cross = {}
        for field, digest in (('files', 'decoded_sha256'), ('assets', 'sha256')):
            lookup = defaultdict(list)
            for other in ('retail-jp', 'retail-us', 'retail-eu'):
                for key, value in report['images'][other][field].items():
                    lookup[value[digest]].append(f'{other}:{key}')
            novel = sorted(k for k, value in edition[field].items() if value[digest] not in lookup)
            cross[field] = dict(novel=novel, matched_to_any_retail=len(edition[field]) - len(novel))
            if field == 'assets':
                cross[field]['novel_by_kind'] = dict(Counter(edition[field][k]['kind'] for k in novel))
        unknown = [(lba, category) for lba, category, digest in uncovered[name] if digest not in retail_sectors]
        cross['non_file_novel_sector_counts'] = dict(Counter(category for _, category in unknown))
        cross['non_file_novel_sector_ranges'] = {category: ranges([lba for lba, kind in unknown if kind == category])
                                                 for category in sorted({kind for _, kind in unknown})}
        report['cross_retail'][name] = cross
    return report


def add_text_inventory(report, rom_root):
    """Also count menu banks embedded inside overlays outside LDAR ranges."""
    from formats.text.export import collect, plain
    # Human-readable text hashes belong to this final collector pass, which
    # attaches title layouts and records the exact glyph-dictionary revision.
    for image in report['images'].values():
        for asset in image['assets'].values():
            asset.pop('decoded_text_sha256', None)
    for comparisons in report['comparisons'].values():
        for comparison in comparisons.values():
            for change in comparison['assets']['wfm_changes'].values():
                change.pop('decoded_text_sha256', None)
    decoder_paths = ('formats/text/export.py', 'formats/text/wfm.py', 'formats/text/titles.py',
                     'formats/text/glyph_dictionary.json', 'formats/text/glyphs_us.json',
                     'formats/text/glyphs_jp.json', 'game/builds.py', 'game/special_edition.py')
    decoder_hashes = {path: sha((ROOT / path).read_bytes()) for path in decoder_paths if (ROOT / path).exists()}
    report['method']['text_banks'] = ('formats.text.export.collect: every LDAR, standalone and valid embedded WFM bank; '
                                      'one record per source/offset, including retained English and appended Japanese menus.')
    for name, relative in IMAGES.items():
        print(f'Collecting embedded text: {relative}', flush=True)
        project = Project(rom_root / relative)
        with project.disc.path.open('rb') as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as raw:
            if sha(raw) != report['images'][name]['image_sha256']:
                raise ValueError(f'{relative}: image changed since file audit')
        items = []
        for bank in collect(project):
            wfm = bank.wfm
            items.append(dict(source=bank.source, offset=bank.offset, version=bank.version,
                              table=bank.table, dialogue_count=len(wfm.dialogues),
                              glyph_count=len(wfm.glyphs), unknown_used_glyphs=bank.unknown,
                              dialogue_tokens_sha256=sha(json.dumps([d.tokens for d in wfm.dialogues]).encode()),
                              decoded_text_sha256=sha(json.dumps([plain(d) for d in wfm.dialogues],
                                                                 ensure_ascii=False).encode('utf8'))))
        report['images'][name]['text_banks'] = items
        report['images'][name]['text_bank_versions'] = dict(Counter(item['version'] for item in items))
    if decoder_hashes != {path: sha((ROOT / path).read_bytes()) for path in decoder_hashes}:
        raise ValueError('Text decoder files changed during text collection; rerun the text inventory.')
    report['text_decoder_inputs_sha256'] = decoder_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-root', type=Path, default=ROOT / 'rom')
    parser.add_argument('--output', type=Path, default=ROOT / 'work/special-edition-comparison.json')
    parser.add_argument('--text-only-update', action='store_true',
                        help='Append/refresh embedded text inventory in an existing hash-checked report.')
    args = parser.parse_args()
    report = json.loads(args.output.read_text(encoding='utf8')) if args.text_only_update else audit(args.rom_root)
    add_text_inventory(report, args.rom_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    print(f'Wrote {args.output}')
    for name, comparisons in report['comparisons'].items():
        nearest = 'retail-eu' if name == 'special-e' else 'retail-us'
        files = comparisons[nearest]['files']
        print(name, 'vs', nearest, 'identical', files['identical'], 'changed', len(files['changed']),
              'added', len(files['added']), 'removed', len(files['removed']),
              'asset changes', comparisons[nearest]['assets']['changed_by_kind'])


if __name__ == '__main__':
    main()
