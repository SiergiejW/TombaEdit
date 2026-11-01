"""Read-only, fingerprint-scoped JP cut-village orphan/reference audit.

The JSON records decoded facts, not ROM payloads. Missing literal references are
bounded static evidence, not a proof against computed calls or future spawns.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formats.archive.ldar import Project
from formats.level.cut_towns import JP_INFO2_SHA1, villages
from formats.level.cut_village_view import _overlay
from game.builds import executable

UPSTREAM = '44e814a6268f294f889ee77f5aad319f88e82a50'
JP_MAIN_SHA1 = '07d577698ad31ec1a69b9d7b80a7c3f90b650888'
FUNCTIONS = (
    ('topdownA11ActorDialogueBank2', 0x800F2F24, 0xDC, 0x800F1BAC),
    ('topdownA16ActorDialogueBank2', 0x800F413C, 0xC0, 0x800F2DC4),
    ('topdownA17ActorDialogueBank2', 0x800F5218, 0xE0, 0x800F3EA0),
    ('topdownA17ActorDialogueBank3', 0x800F52F8, 0x190, 0x800F3F80),
    ('topdownA11SceneryInit', 0x800F7F6C, 260, 0x800F6BF4),
    ('topdownA11SceneryUpdate', 0x800F8070, 100, 0x800F6CF8),
    ('topdownA16SceneryInit', 0x800F1CFC, 260, 0x800F0984),
    ('topdownA16SceneryApplyState', 0x800F1E00, 136, 0x800F0A88),
    ('topdownA17SceneryInit', 0x800F20F8, 260, 0x800F0D80),
)


def audit(cue):
    project = Project(cue)
    exe = executable(project)
    overlay = bytes(_overlay(project))
    if (exe is None or hashlib.sha1(exe.data).hexdigest() != JP_MAIN_SHA1
            or hashlib.sha1(overlay).hexdigest() != JP_INFO2_SHA1):
        raise ValueError('This audit requires the unmodified audited JP retail MAIN and INFO2.')
    base = exe.build.overlay
    regions = [('MAIN', exe.base, exe.data[0x800:]), ('INFO2', base, overlay)]

    def read(address, size):
        for _, start, data in regions:
            if start <= address and address + size <= start + len(data):
                return data[address-start:address-start+size]
        raise ValueError(f'Address outside audited regions: {address:08X}')

    def u32(address):
        return struct.unpack('<I', read(address, 4))[0]

    def location(address):
        for name, start, data in regions:
            if start <= address < start + len(data):
                return dict(file='SLPS_011.44' if name == 'MAIN' else 'SYSTEM/INFO2.BIN',
                            address=f'{address:08X}',
                            offset=f'{address-start+(0x800 if name == "MAIN" else 0):X}')
        raise ValueError(hex(address))

    def references(target):
        result = []
        for name, start, data in regions:
            for offset in range(0, len(data)-3, 4):
                value = struct.unpack_from('<I', data, offset)[0]
                kind = 'pointer' if value == target else None
                if value >> 26 in (2, 3):
                    jump = ((start+offset+4) & 0xF0000000) | ((value & 0x3FFFFFF) << 2)
                    if jump == target:
                        kind = 'JAL' if value >> 26 == 3 else 'J'
                if kind:
                    result.append(dict(region=name, kind=kind, **location(start+offset)))
        return result

    def script(address):
        steps, seen = [], set()
        cursor = address
        for _ in range(256):
            if cursor in seen:
                return dict(start=location(address), steps=steps, end='loop')
            seen.add(cursor)
            frame, box, arg, control = struct.unpack('<HHhH', read(cursor, 8))
            steps.append(dict(**location(cursor), frame=frame, box=box, argument=arg,
                              control=f'{control:04X}', ticks=control & 0x3FFF))
            if control & 0xC000 == 0x8000:
                return dict(start=location(address), steps=steps, end='hold')
            cursor = u32(cursor+8) if control & 0x4000 else cursor+8
        raise ValueError('Unbounded animation')

    towns = villages(overlay, base)
    result = dict(format=1, upstream=UPSTREAM,
                  main_sha1=JP_MAIN_SHA1, info2_sha1=JP_INFO2_SHA1,
                  reference_scope='Aligned 32-bit pointers and direct J/JAL in MAIN and INFO2 only; no computed-reference proof',
                  functions=[], scenery=[], wood_unselected_scripts=[])
    for name, address, length, pal in FUNCTIONS:
        result['functions'].append(dict(name=name, **location(address), bytes=length,
            pal_address=f'{pal:08X}', sha256=hashlib.sha256(read(address, length)).hexdigest(),
            references=references(address)))

    # Scenery windows are bounded by the next definition's animation table (Wood
    # and Stone) or by the first script (Iron), not by an arbitrary 24-read loop.
    for number, definition, count, table, end in (
            (0x0D, 0x80100198, 2, 0x801061C4, 0x80106224),
            (0x0E, 0x800FFF14, 3, 0x80101C48, 0x80101CC0),
            (0x0F, 0x800FFF48, 4, 0x80106F50, 0x80106FB0)):
        town = towns[number]
        defs = []
        for subtype in range(count):
            address = definition+subtype*12
            page, zero, slot, zero2, ptr = struct.unpack('<HhhhI', read(address, 12))
            assert zero == zero2 == 0 and slot == 13 and ptr == table
            defs.append(dict(subtype=subtype, page_offset=page, spr_slot=slot,
                             script_table=f'{ptr:08X}', **location(address),
                             placed_props=[p.index+1 for p in town.props if p.subtype == subtype]))
        scripts = [dict(index=i, **script(u32(table+i*4))) for i in range((end-table)//4)]
        props = [asdict(prop) for prop in town.props]
        selected = {p.animation for p in town.props + town.alternate_props}
        if number == 0x0E:
            selected |= {11, 12}  # explicit SceneryUpdate state 2 / 3 assignments
        if number == 0x0F:
            selected |= {13, 14, 15}  # P16 = 13 + phase; passage 8 writes phases 1 and 2
        unselected = sorted(set(range(len(scripts))) - selected)
        result['scenery'].append(dict(area=town.area, definitions=defs, props=props,
            alternate_props=[asdict(prop) for prop in town.alternate_props],
            table=location(table), table_end=f'{end:08X}', scripts=scripts,
            no_selection_in_preserved_lists_and_audited_scenery_handlers=unselected))
        if number == 0x0D:
            for index in unselected:
                entry = scripts[index].copy()
                entry['pointer_cell'] = location(table+index*4)
                entry['literal_script_users'] = references(u32(table+index*4))
                result['wood_unselected_scripts'].append(entry)

    assert result['scenery'][2]['definitions'][3]['page_offset'] == 8
    assert not result['scenery'][2]['definitions'][3]['placed_props']
    assert result['scenery'][0]['no_selection_in_preserved_lists_and_audited_scenery_handlers'] == [12, 13, 16, 17, 18, 19, 20, 21, 22, 23]
    extra = {s['index']: s for s in result['wood_unselected_scripts']}
    assert {step['frame'] for i in range(16, 24) for step in extra[i]['steps']} == set(range(141, 167))
    assert all(len(s['literal_script_users']) == 1 for s in extra.values())
    assert not result['functions'][0]['references']
    assert not result['functions'][1]['references']
    assert not result['functions'][2]['references']
    assert any(r['kind'] == 'JAL' for r in result['functions'][3]['references'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cue')
    parser.add_argument('--output', type=Path, default=Path('work/cut_village_research/orphans_deeper.json'))
    args = parser.parse_args()
    result = audit(args.cue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    print('JP fingerprints verified; Wood 10 unselected scenery slots (8 cover frames 141..166); Iron unplaced subtype 3/page 8.')
    for entry in result['functions']:
        print(entry['name'], entry['address'], 'literal/direct refs:', len(entry['references']))
    print('Decoded evidence:', args.output)


if __name__ == '__main__':
    main()
