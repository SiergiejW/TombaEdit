"""Read-only JP retail checks for remnants outside the cut towns.

Run with an unmodified SLPS_011.44 CUE. Optional previews are decoded from
that disc, never shipped artwork. Native checks execute bounded routines;
they do not simulate a quest or establish full game-state reachability.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_cut_resident_orphans import Retail
from audit_cut_village_state import Native, OBJ
from formats.level.scene import loaded_resources
from formats.sprites.animations import Memory, player_scripts, read_script
from formats.text.export import collect, plain
from psx.graphics import palette_missing, render_sprite, sprite_frames


X10_SHA1 = 'e9280e20362a1be59df924bc4be2f769438d6ae7'
DSPSUB_SHA1 = '985875ab8ac54dc43f5ed88cfef75bfdf9608fc0'
SPR_SHA1 = '53c337d8a72ac14b0386dd7702e16b0da821f02e'
TEXT_SHA1 = '233a07817e1b1d903219130c8ae168220b93ac84'
EEL_CELL, EEL_SCRIPT = 0x8012DEB8, 0x8012E0E0
INITIALIZER = (0x8003D740, 0x8003D9A4)
ANIMATION = (0x80020DE4, 0x80020F1C)
ITEMS = {
    2: 'Lost Dwarf', 25: 'Map', 52: 'Rain Essence',
    57: 'Torn Map 1', 58: 'Torn Map 2', 59: 'Rubber Gloves',
    61: 'Iron lump', 62: 'Iron Wheel', 64: 'Valve / Pipe',
    **{n: f'Math Bead {n-66}' for n in range(77, 82)},
    **{n: f'Community Number Ball {n-66} slot (name needs separate verification)' for n in range(82, 87)},
    90: 'Letter', 91: 'Wood', 97: 'Shovel', 101: 'Mighty Fish',
    107: "10,000 Year Old Man's Letter / flower mismatch",
    108: 'Electric Eel', 109: 'Black Water', 110: 'Red Candy',
    111: 'Blue Candy', 112: 'Green Candy', 113: 'Black Candy',
    114: 'Silver Candy', 116: 'Forbidden Mushroom', 118: 'Coconuts',
    119: 'Funga Leather', 120: "Grandpa's Bracelet", 122: 'Funga Tree',
    123: 'Funga Sap', 125: 'Funga Drum', 127: 'Unusual Key',
    128: 'Chuckling Mushroom', 129: 'Weeping Mushroom', 131: 'Map of the Underground Labyrinth',
    133: 'Community Chick placeholder; JP use message says 1UP',
    134: 'Community Chick placeholder; JP use message says Gauge MAX +1', 135: 'Golden Bowl',
    136: 'Flower Tears', 137: 'Small Drum', 140: "Chief's Spear",
    147: 'Coal (JP text; PAL enum calls this TRASHCAN)',
}


def digest(data):
    return hashlib.sha1(data).hexdigest()


def script_record(memory, address, count):
    script = read_script(memory, address, count)
    assert script is not None, f'Invalid script {address:08X}'
    return dict(address=f'{address:08X}', frames=script.frames,
        steps=[dict(address=f'{s.address:08X}', frame=s.frame, box=s.box,
                    argument=s.arg, ticks=s.ticks, flags=f'{s.flags:04X}') for s in script.steps],
        terminal='hold' if script.loop is None else 'loop')


def references(regions, low, high):
    """Literal words and a deliberately broad, eight-instruction split scan.

    Split candidates need no register agreement. Zero hits is a bounded
    negative result, never a general proof against computed addressing.
    """
    literal, split = [], []
    for name, base, data in regions:
        for offset in range(0, len(data)-3, 4):
            word = struct.unpack_from('<I', data, offset)[0]
            if low <= word < high:
                literal.append(dict(file=name, address=f'{base+offset:08X}', value=f'{word:08X}'))
            if word >> 26 != 15:
                continue
            upper = (word & 0xFFFF) << 16
            for at in range(offset+4, min(offset+36, len(data)-3), 4):
                other = struct.unpack_from('<I', data, at)[0]
                op = other >> 26
                if op not in (8, 9, 13, 32, 33, 35, 36, 37, 40, 41, 43):
                    continue
                imm = other & 0xFFFF
                if op != 13 and imm & 0x8000:
                    imm -= 0x10000
                target = (upper | imm) if op == 13 else (upper+imm) & 0xFFFFFFFF
                if low <= target < high:
                    split.append(dict(file=name, lui=f'{base+offset:08X}',
                                      low_half=f'{base+at:08X}', value=f'{target:08X}'))
    return dict(aligned_words=literal, split_address_candidates=split)


def initialize(retail, overlay, item):
    vm = Native(retail, overlay)
    vm.allowed = [INITIALIZER, (0x80020DE4, 0x80020E00),
                  (retail.exe.build.get_clut, retail.exe.build.get_clut+0x18)]
    vm.write(OBJ, bytes(0x200))
    vm.integer(OBJ+3, item, 1)
    # Distinct synthetic bank pointers identify the native slot selection.
    # The initializer does not dereference SPR data or draw the object.
    for slot in range(16):
        vm.integer(0x1F8002C8+4*slot, 0x801D0000+slot*0x100)
    vm.call(INITIALIZER[0])
    assert not vm.calls, 'Initializer reached a service outside the allowed native routines'
    pointer = vm.integer(OBJ+0x24)
    return dict(page=vm.integer(OBJ+0x1E, size=2),
        sprite_slot=(vm.integer(OBJ+0x3C)-0x801D0000)//0x100,
        script=f'{pointer:08X}', frame=vm.integer(pointer, size=2),
        clut=f'{vm.integer(OBJ+8, size=2):04X}', box_words=list(struct.unpack('<4H', vm.read(OBJ+0x6C, 8))))


def eel_playback(retail, overlay):
    vm = Native(retail, overlay)
    vm.allowed = [ANIMATION]
    vm.write(OBJ, bytes(0x200))
    vm.integer(OBJ+0x24, EEL_SCRIPT)
    vm.call(0x80020DE4)
    transitions, finished, previous = [], [], None
    for tick in range(33):
        pointer = vm.integer(OBJ+0x24)
        current = pointer, vm.integer(pointer, size=2)
        if current != previous:
            transitions.append(dict(tick=tick, script=f'{pointer:08X}', frame=current[1]))
            previous = current
        if tick == 32:
            break
        vm.call(0x80020E38)
        if vm.u.reg_read(vm.reg.UC_MIPS_REG_V0):
            finished.append(tick+1)
    assert not vm.calls
    assert [(v['tick'], v['frame']) for v in transitions] == [(0, 33), (8, 34), (16, 35)]
    assert finished == [24, 32] and vm.integer(OBJ+0x24) == EEL_SCRIPT+16
    return dict(transitions=transitions, finished_updates=finished,
                terminal='holds frame 35; does not loop to frame 33')


def jp_hurt_control(retail, overlay):
    results = []
    for reason in (0, 1, 3):
        vm = Native(retail, overlay)
        vm.allowed = [(0x800FCE48, 0x800FD41C), (0x800EFD70, 0x800EFDF8), ANIMATION]
        vm.write(OBJ, bytes(0x200))
        vm.write(OBJ+0x1000, bytes(0x200))
        vm.integer(0x8009DEE0, OBJ+0x1000)
        for offset, value, width in ((0, 1, 1), (4, 2, 1), (6, 1, 1),
                                     (0x98, 8, 2), (0x9A, 8, 2), (0xD1, reason, 1)):
            vm.integer(OBJ+offset, value, width)
        vm.call(0x800FCE48)
        selected = vm.integer(OBJ+0x102C, size=2)
        pointer = vm.integer(OBJ+0x24)
        assert selected == 57 and pointer == 0x80011470
        assert {c['target'] for c in vm.calls} == {'8001E388', '8001E2D4'}
        results.append(dict(synthetic_pal_reason_byte=reason, selected_animation=selected,
            script=f'{pointer:08X}', next_state=vm.integer(OBJ+6, size=1), stubbed_calls=vm.calls))
    return results


def audit(cue, image_dir=None):
    retail = Retail(cue)
    project, exe, base = retail.project, retail.exe, retail.base
    resources = loaded_resources(project, 'SYS/LDAR10.BIN', 1)
    overlay = bytes(project.asset_data(resources['INS', 0]))
    assert digest(overlay) == X10_SHA1
    sub = project.disc.read('SYSTEM/DSPSUB.BIN')
    assert digest(sub) == DSPSUB_SHA1
    spr_asset = resources['SPR', 3]
    spr_data = bytes(project.asset_data(spr_asset))
    assert digest(spr_data) == SPR_SHA1
    frames = sprite_frames(spr_data)
    assert len(frames) == 196
    regions = [('SLPS_011.44', exe.base, exe.data[0x800:]), ('AREA10/X10.BIN', base, overlay)]
    memory = Memory(regions)
    assert memory.u32(EEL_CELL) == EEL_SCRIPT
    eel_script = script_record(memory, EEL_SCRIPT, len(frames))
    assert eel_script['frames'] == [33, 34, 35]
    assert [s['ticks'] for s in eel_script['steps']] == [8, 8, 8]
    assert [s['flags'] for s in eel_script['steps']] == ['0000', '0000', '8000']
    cell_refs = references(regions, EEL_CELL, EEL_CELL+4)
    script_refs = references(regions, EEL_SCRIPT, EEL_SCRIPT+24)
    assert not cell_refs['aligned_words'] and not cell_refs['split_address_candidates']
    assert [(a['file'], a['address']) for a in script_refs['aligned_words']] == [('AREA10/X10.BIN', '8012DEB8')]
    assert not script_refs['split_address_candidates']

    vram = project.vram('SYS/LDAR10.BIN', 1)
    frame_records, pictures = [], []
    for number in (33, 34, 35):
        parts = frames[number]
        assert len(parts) == 1 and parts[0][2] == 0x7B0C
        assert not palette_missing(vram, parts[0][2])
        picture = render_sprite(parts, vram, tpage=12)
        assert picture.size == (32, 16) and picture.getbbox() is not None
        pictures.append(picture)
        frame_records.append(dict(number=number, parts=[list(p) for p in parts], page_base=12,
            clut='7B0C', decoded_size=list(picture.size), rgba_sha256=hashlib.sha256(picture.tobytes()).hexdigest()))
    uploads = [a for g in project.ldars['SYS/LDAR10.BIN'][:2] for a in g.assets if a.rect]
    texture = next(a for a in uploads if a.source.path == 'AREA10/B003.GAM')
    palette = next(a for a in uploads if a.rect == (128, 480, 256, 32))
    assert digest(project.asset_data(texture)) == '648fac83861c8018bbf3556d619a2d1410c8e865'
    assert digest(project.asset_data(palette)) == 'c3a9f7e76057f4e7cfa41ed511e49f0faf915124'

    bank = next(b for b in collect(project, area=10) if b.source == 'AREA10/A003.GAM' and b.offset == 0xBA94)
    text_asset = next(a for g in project.ldars['SYS/LDAR10.BIN'] for a in g.assets
                      if a.kind == 'WFM' and a.source.path == bank.source and a.offset == bank.offset)
    assert digest(project.asset_data(text_asset)) == TEXT_SHA1
    condition_indices = sub[0x8010472C-base:0x8010472C-base+200]
    condition_pointers = struct.unpack_from('<45I', sub, 0x80105514-base)
    item_index, descriptors, _ = exe.build.items
    item_rows = []
    for item, label in ITEMS.items():
        number = exe.data[item_index-exe.base+0x800+item]
        address = exe.word(descriptors+number*4)
        desc = exe.unpack('<8Bhh4sI', address)
        item_rows.append(dict(id=item, label=label, use_message=plain(bank.wfm.dialogues[item]),
            descriptor_index=number, descriptor_address=f'{address:08X}',
            descriptor_hex=memory.read(address, 20).hex(),
            page=desc[2], sprite_slot=desc[4], palette_mode=desc[6], animation_mode=desc[7],
            palette_xy=list(desc[8:10]), animation_table=f'{desc[-1]:08X}',
            condition_index=condition_indices[item],
            condition_address=f'{condition_pointers[condition_indices[item]]:08X}'))
    messages = {row['id']: row['use_message'] for row in item_rows}
    assert messages[131] == '地下迷路の地図をつかった'
    assert messages[133] == '1UPをつかった' and messages[134] == 'ゲージMAX +1をつかった'
    assert all(condition_indices[item] == 0 for item in (131, 133, 134, 147))
    native_items = {item: initialize(retail, overlay, item) for item in (59, 77, 78, 108, 109, 91, 119, 122, 123, 125, 137, 140)}
    for item in (59, 108, 109, 119):
        assert native_items[item]['sprite_slot'] == 4 and native_items[item]['frame'] == 0
    for item in (125, 137):
        assert (native_items[item]['sprite_slot'], native_items[item]['frame'], native_items[item]['clut']) == (4, 197, '7D12')
    assert native_items[125]['box_words'] == [8, 16, 8, 16]
    assert native_items[137]['box_words'] == [12, 12, 12, 12]
    all_indices = exe.data[item_index-exe.base+0x800:descriptors-exe.base+0x800]
    all_descriptors = {exe.word(descriptors+4*n) for n in set(all_indices)}
    assert len(all_indices) == 200 and len(all_descriptors) == 97
    assert all(exe.word(address+16) != EEL_CELL for address in all_descriptors)
    assert all(exe.word(address+16) != 0x8012DEC4 for address in all_descriptors)
    assert memory.u32(0x8012DEC4) == 0x8012E110
    assert memory.read(0x8012E108, 8) == memory.read(0x8012E110, 8)
    assert native_items[77]['script'] != native_items[78]['script'] == '80011F64'

    false_op = struct.unpack_from('<I', sub, 0x801055C8-base)[0]
    assert false_op == 0x800F26DC and sub[false_op-base:false_op-base+8] == bytes.fromhex('0800e00321100000')
    assert sub[0x801047F4-base:0x801047FC-base] == bytes.fromhex('ffff00ff00000000')

    player_count = len(sprite_frames(project.asset_data(resources['SPR', 0])))
    player_regions = [('executable', exe.base, exe.data[0x800:]), ('overlay', base, overlay)]
    players = player_scripts(player_regions, player_count)
    assert player_count == 366 and sum(map(len, players.values())) == 74
    pointers = struct.unpack_from('<74I', overlay, 0x800E9E40-base)
    assert all(read_script(memory, p, player_count) for p in pointers)
    assert memory.u32(0x800FD01C) == 0x24060039

    result = dict(format=1, scope='JP retail, bounded native routines and retained metadata; not a playable restoration',
        main_sha1=digest(exe.data), info2_sha1=digest(retail.overlay), x10_sha1=digest(overlay), dspsub_sha1=digest(sub),
        sprite_bank=dict(file=spr_asset.source.path, offset=f'{spr_asset.offset:X}', sha1=digest(spr_data), slot=3, frames=len(frames)),
        eel=dict(pointer_cell=f'{EEL_CELL:08X}', script=eel_script, cell_references=cell_refs,
                 script_references=script_refs, native_playback=eel_playback(retail, overlay), frames=frame_records,
                 texture=dict(file=texture.source.path, rect=list(texture.rect), sha1=digest(project.asset_data(texture))),
                 palette=dict(file=palette.source.path, rect=list(palette.rect), clut_xy=[192, 492], sha1=digest(project.asset_data(palette)))),
        item_table=dict(index=f'{item_index:08X}', pointers=f'{descriptors:08X}', initializer='8003D740',
                        ids_checked=len(all_indices), descriptors_checked=len(all_descriptors), entries=item_rows),
        native_item_initialization=native_items,
        player=dict(sprite_frames=player_count, animation_table='800E9E40', animation_count=74,
                    selector='800EFD70', hurt_routine='800FCE48', hurt_size=1492,
                    ordinary_animation_literal='800FD01C', animation_store='800FD050',
                    controls=jp_hurt_control(retail, overlay)),
        unbound_duplicate_wood=dict(pointer_cell='8012DEC4', script='8012E110',
            frame=38, selected_item_descriptors=[], duplicate_of='8012E108'),
        chief_text=dict(file=bank.source, wfm_offset=f'{bank.offset:X}', sha1=TEXT_SHA1,
            entries=[dict(index=i, group=2, line=i-177, japanese=plain(bank.wfm.dialogues[i])) for i in range(188,196)]))
    if image_dir is not None:
        from PIL import Image, ImageDraw
        image_dir.mkdir(parents=True, exist_ok=True)
        sheet = Image.new('RGB', (450, 104), '#606068')
        draw = ImageDraw.Draw(sheet)
        for i, picture in enumerate(pictures):
            image = picture.resize((128, 64), Image.Resampling.NEAREST)
            sheet.paste(image, (i*150+4, 30), image)
            draw.text((i*150+4, 7), f'JP eel: frame {i+33}', fill='white')
        target = image_dir/'eel-native-jp.png'
        sheet.save(target)
        result['eel']['local_preview'] = str(target.resolve())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cue')
    parser.add_argument('--output', type=Path, default=Path('work/non_village_research/jp_unused_content.json'))
    parser.add_argument('--images', action='store_true', help='Decode a local eel preview from the supplied ROM')
    args = parser.parse_args()
    result = audit(args.cue, args.output.parent if args.images else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('Passed JP checks: eel graphics/script and native hold, item descriptor gaps, '
          'drum sprite alias, 74-entry player table and JP hurt controls.')
    print('Evidence:', args.output)


if __name__ == '__main__':
    main()
