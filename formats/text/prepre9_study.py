"""Reproducible static selector coverage for the two verified Pure Pure 09 builds.

This closes the native/script *selection* inventory, not game-state reachability.
An unmatched stream is Possibly unused. A retained script bound can include
unreachable branches, so it must never be called proof that an entry is used.
The builder takes an already hash-verified native reference profile and returns
an enriched copy. Nothing here edits a disc or changes Japanese decoding.
"""
import copy
import hashlib
import struct
from collections import defaultdict
from pathlib import PurePosixPath

from formats.script.wss import Wss
from formats.script.text_references import selectors


SCRIPTS = {
    '0000.WSS': 'e0979ab250f876b514c6c3a6daebfaf5ea49b8a6',
    '0120.WSS': 'a44a10fa8dcc55ee32970da5b51d515c2643dfb4',
    '0130.WSS': '35758f6629a417e653ca837281c8c9f5a13f7041',
    '0140.WSS': '7bba701cad8341da4dc27740e40774686709cf8b',
    '0200.WSS': 'fe21467cc8fa8a72fdd898a098488d3d98e6c84f',
    '0210.WSS': 'fb12da720cbad211bc83599da2d6e77e950b01a9',
    'SCR0100.WSS': '15699fff737464c83ea84aebb69ba3ac0315cfcc',
}
WINDOWS = {0x80031060, 0x80031098, 0x800310D8, 0x80031100, 0x8003112C}
CALLS = {
    'MAIN': {0x80032BB4, 0x8003BB80},
    'X01.BIN': {0x801137F4, 0x80113F3C, 0x8011417C, 0x801321D0, 0x8013848C, 0x80138A54},
    'X02.BIN': {0x801137F4, 0x80113F3C, 0x8011417C},
    'INFO.BIN': {0x800F2B88, 0x800F313C, 0x800F4010},
    'DSPSUB.BIN': set(), 'DSPSUB3.BIN': set(),
}


def direct_calls(base, data, targets):
    out = set()
    for offset in range(0, len(data) - 3, 4):
        word = struct.unpack_from('<I', data, offset)[0]
        if word >> 26 in (2, 3) and (0x80000000 | (word & 0x3FFFFFF) << 2) in targets:
            out.add(base + offset)
    return out


def complete(project, profile):
    """Finish all four banks, or fail without producing negative classifications."""
    from game.builds import executable
    from formats.sprites.animations import code_constants
    from formats.text.usage import PREPRE9_CODE, PREPRE9_EXES, _bank_study
    found = executable(project)
    if found is None or hashlib.sha1(found.data).hexdigest() not in PREPRE9_EXES:
        raise ValueError('Not a verified Pure Pure 09 executable')
    regions = {'MAIN': (found.base, found.data[0x800:])}
    hashes, seen = set(), set()
    for groups in project.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind != 'INS' or not asset.source:
                    continue
                data = project.asset_data(asset)
                digest = hashlib.sha1(data).hexdigest()
                hashes.add(digest)
                if digest not in seen:
                    regions[PurePosixPath(asset.source.path).name] = (found.build.overlay, data)
                    seen.add(digest)
    if hashes != PREPRE9_CODE or set(regions) != set(CALLS):
        raise ValueError('Loaded overlays differ from the checked selector inventory')
    for name, (base, data) in regions.items():
        calls = {pc for pc in direct_calls(base, data, WINDOWS) if not 0x80031060 <= pc < 0x8003112C}
        if calls != CALLS[name]:
            raise ValueError(f'Unaccounted native window call in {name}')
        constants = code_constants(base, data)
        if any(constants.get(target) or struct.pack('<I', target) in data for target in WINDOWS):
            raise ValueError('An indirect window constructor reference needs tracing')
        # The orphan INFO helper is not wired into a caller or dispatch table.
        orphan = 0x800F2B0C
        # Other overlays occupy this same RAM range; a menu's identical
        # numeric address names its own function, not the INFO helper.
        if name in ('MAIN', 'INFO.BIN') and (direct_calls(base, data, {orphan}) or constants.get(orphan)
                or struct.pack('<I', orphan) in data):
            raise ValueError('The previously orphaned INFO selector has an incoming reference')

    # INFO's other computed selector is action 3 of its script-actor machine.
    # Its helpers only reset the action byte to zero; they never advance to 3.
    info_base, info = regions['INFO.BIN']
    writes = []
    for pc in range(0x800F2948, 0x800F327C, 4):
        word = struct.unpack_from('<I', info, pc - info_base)[0]
        if word >> 26 == 40 and word & 0xFFFF == 5:
            writes.append(pc)
            if word >> 16 & 31:
                raise ValueError('The INFO actor can change to an untraced action')
    if len(writes) != 7:
        raise ValueError('Unexpected INFO actor action stores')
    if struct.unpack_from('<I', info, 0x800ED7A0 - info_base)[0] != 0x800F30B8:
        raise ValueError('INFO action 3 dispatch changed')

    possible = defaultdict(list)
    scripts, script_hashes = {}, {}
    for item in project.disc.files:
        if not item.path.upper().endswith('.WSS'):
            continue
        name = PurePosixPath(item.path).name
        data = project.payload(item)
        digest = hashlib.sha1(data).hexdigest()
        if SCRIPTS.get(name) != digest:
            raise ValueError('A script differs from the checked conversation program')
        script = Wss(data)
        # Action 3 alone sets object +98/+9A before INFO's computed window.
        # All local action operands are literals; none supplies action 3.
        for i, ins in enumerate(script.instructions[:-1]):
            call = script.instructions[i + 1]
            if ins.name == 'ARGS' and call.name == 'ObjAction' and call.offset == ins.offset + ins.size:
                if len(ins.operands) < 2 or not ins.operands[1].lstrip('-').isdigit() or int(ins.operands[1]) == 3:
                    raise ValueError('An object-supplied dialogue path needs further analysis')
        for selection in selectors(script):
            if not selection['bounded']:
                raise ValueError('A script talk selector has unbounded inputs')
            for base in selection['bases']:
                for line in selection['lines']:
                    # Native openMessageBox truncates its selected ID to u16.
                    index = (base + line) & 0xFFFF
                    possible[index].append(f'{item.path} +{selection["offset"]:X}: ({base}, {line}).')
        scripts[name] = script
        script_hashes[item.path] = digest
    if set(scripts) != set(SCRIPTS) or script_hashes != profile.get('scripts_sha1'):
        raise ValueError('The script inventory is incomplete')

    # Use a conservative union of all loaded script/overlay contexts. This
    # retains more entries than a scene-specific reachability analysis could;
    # a future context restriction must not create a false unused candidate.
    native = {(13, 2), (56, 1), (59, 0), (59, 1), (59, 2),
              (62, 10), (62, 11), (62, 12), (62, 32), (62, 33)}
    # All 19 signpost/savepoint records, not just the first area's ten.
    # The following word is already a function pointer, not another record.
    for variant in range(19):
        base, line, z0, z1 = found.unpack('<4h', 0x80072DE0 + variant * 8)
        if base not in (14, 20, 56, 62) or not 0 <= line < 128 or z0 or z1:
            raise ValueError('The native signpost selector table changed')
        native.add((base, line))

    result = copy.deepcopy(profile)
    for key, bank in result['banks'].items():
        source, offset = key.rsplit('@', 1)
        if _bank_study(project, profile, source, int(offset, 16)) is None:
            raise ValueError('Text bank content or its loaded bindings changed')
        slots = {slot for table, slot in bank['contexts']}
        if slots == {1}:
            # Every title has a mapping, including CLEAR!'s direct glyph path.
            if len(bank['text']) != bank['entries'] or any(v['status'] != 'referenced' for v in bank['text'].values()):
                raise ValueError('Event title or fixed completion-banner selection is unresolved')
        elif slots == {0}:
            for index in range(bank['entries']):
                item = bank['text'].get(str(index))
                if item and item['status'] in ('referenced', 'dynamic'):
                    continue
                pairs = [(base, line) for base, line in native if (base + line) & 0xFFFF == index]
                candidates = possible.get(index, [])
                if candidates or pairs:
                    bank['text'][str(index)] = dict(status='dynamic', method='pure9-complete-selector-bound', evidence=[
                        'Retained by the conservative union of native/script selectors across all loaded contexts.',
                        *(candidates[:2] or [f'Native signpost/branch arguments: {sorted(pairs)}.']),
                        'This is a possible selection; its scene binding and trigger reachability are not proven.'])
                else:
                    bank['text'][str(index)] = dict(status='not_found', method='pure9-complete-selector-audit-v2', evidence=[
                        'Possibly unused: no selection in the complete static native/script selector inventory for this exact build.',
                        'Checked: native window calls and branches, all 19 signpost/savepoint pairs, item/event notice tables, and all seven WSS programs with variable-definition bounds.',
                        'INFO 800F2B88 belongs to an unreferenced helper; 800F313C requires actor action 3, which no local script requests and no actor helper advances into.',
                        'A static unused candidate, not proof about every hypothetical game state. Glyph recognition and translation are not used to decide this.'])
        else:
            raise ValueError('Unexpected WFM slot binding')
        bank['coverage_complete'] = True
        bank['computed_calls'] = 0
        bank['coverage'] = ('Complete static selector audit for this exact Pure Pure 09 build: all native window, '
            'signpost, item/event, script and event-title paths accounted for. Dynamic bounds are conservative. '
            'Possibly unused does not prove game-state unreachability.')
    result['audit_revision'] = 'pure9-complete-selector-audit-v2'
    return result


def main():
    """python -m formats.text.prepre9_study IMAGE.cue [--write-index]."""
    import argparse
    import json
    from collections import Counter
    from pathlib import Path
    from formats.archive.ldar import Project
    from game.builds import executable
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', help='Pure Pure 09 CUE/BIN image, read only')
    parser.add_argument('--write-index', action='store_true', help='Update this exact build in native_text_usage.json')
    args = parser.parse_args()
    path = Path(__file__).with_name('native_text_usage.json')
    document = json.loads(path.read_text(encoding='utf8'))
    project = Project(args.image)
    found = executable(project)
    digest = hashlib.sha1(found.data).hexdigest() if found else ''
    profile = document['builds'].get(digest)
    if profile is None:
        parser.error('No verified reference profile for this image')
    result = complete(project, profile)
    for name, bank in result['banks'].items():
        print(name, dict(Counter(item['status'] for item in bank['text'].values())))
    if args.write_index:
        document['builds'][digest] = result
        path.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
