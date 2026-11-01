"""Read-only JP retail audit of orphan cut-town resident animation data.

Uses the supplied retail bytes, not reconstructed port assets. The selector
probe executes native MIPS only as far as its first animation-pointer store.
It is an isolated selector check, not a restored-town/game-state simulation.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formats.archive.ldar import Project
from formats.level.apd import parse_apd
from formats.level.cut_towns import JP_INFO2_SHA1, villages
from formats.level.cut_village_view import _overlay
from formats.text.mips_args import analyse, region_words
from game.builds import executable


MAIN_SHA1 = '07d577698ad31ec1a69b9d7b80a7c3f90b650888'
# Exact physical windows, bounded by the next definition's pointer or script.
# The 12-pointer tail of Wood subtype 3 is deliberately retained separately.
TOWNS = {
    13: dict(area=11, defs=0x800FFFFC, tables=(
        (0x80106224, 17), (0x80106268, 18), (0x801062B0, 16),
        (0x801062F0, 28), (0x80106360, 12)),
        init=0x800F3EC8, step=0x800F3D0C, talk=0x800F321C, setter=0x800F31C0),
    14: dict(area=16, defs=0x80100038, tables=(
        (0x80107800, 16), (0x80107840, 16), (0x80107880, 24), (0x801078E0, 16)),
        init=0x800F4FA0, step=0x800F4DE4, talk=0x800F43D0, setter=0x800F40C8),
    15: dict(area=17, defs=0x801000A8, tables=(
        (0x80107070, 17), (0x801070B4, 17), (0x801070F8, 16),
        (0x80107138, 16), (0x8010854C, 24)),
        init=0x800F64AC, step=0x800F62E8, talk=0x800F60B4, setter=0x800F51A4),
}


class Retail:
    def __init__(self, cue):
        self.project = Project(cue)
        self.exe = executable(self.project)
        self.overlay = bytes(_overlay(self.project))
        if (self.exe is None or hashlib.sha1(self.exe.data).hexdigest() != MAIN_SHA1
                or hashlib.sha1(self.overlay).hexdigest() != JP_INFO2_SHA1):
            raise ValueError('Supply the audited, unmodified SLPS_011.44 JP retail disc.')
        self.base = self.exe.build.overlay
        self.regions = [('SLPS_011.44', self.exe.base, self.exe.data[0x800:], 0x800),
                        ('SYSTEM/INFO2.BIN', self.base, self.overlay, 0)]
        self.pointers = defaultdict(list)
        for name, base, data, header in self.regions:
            for offset in range(0, len(data)-3, 4):
                value = struct.unpack_from('<I', data, offset)[0]
                self.pointers[value].append(dict(file=name, address=f'{base+offset:08X}',
                                                 offset=f'{offset+header:X}'))

    def read(self, address, size):
        for _name, base, data, _header in reversed(self.regions):
            if base <= address and address+size <= base+len(data):
                return data[address-base:address-base+size]
        raise ValueError(f'Address outside audited MAIN/INFO2: {address:08X}')

    def u32(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def where(self, address):
        for name, base, data, header in reversed(self.regions):
            if base <= address < base+len(data):
                return dict(file=name, address=f'{address:08X}', offset=f'{address-base+header:X}')
        raise ValueError(hex(address))

    def script(self, address):
        steps, seen = [], set()
        pc = address
        for _ in range(256):
            if pc in seen:
                return dict(start=self.where(address), steps=steps, terminal='loop',
                            payload_sha256=hashlib.sha256(self.read(address, max(seen)+12-address)).hexdigest())
            seen.add(pc)
            frame, box, argument, control = struct.unpack('<HHhH', self.read(pc, 8))
            step = dict(**self.where(pc), frame=frame, box=box, argument=argument,
                        control=f'{control:04X}', ticks=control & 0x3FFF)
            steps.append(step)
            if control & 0xC000 == 0x8000:
                return dict(start=self.where(address), steps=steps, terminal='hold',
                            payload_sha256=hashlib.sha256(self.read(address, pc+8-address)).hexdigest())
            if control & 0x4000:
                step['jump'] = f'{self.u32(pc+8):08X}'
                pc = self.u32(pc+8)
            else:
                pc += 8
        raise ValueError('Animation does not terminate or loop within the bounded decoder.')


class SelectorProbe:
    """Execute selectors until o->anim is assigned; no drawing/services run."""
    OBJ, RETURN = 0x801E0000, 0x80001000

    def __init__(self, retail):
        from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
        from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
        from unicorn import mips_const
        self.reg = mips_const
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0, 0x400000)
        self.u.mem_map(0x1F800000, 0x1000)
        for _name, base, data, _header in retail.regions:
            self.write(base, data)
        self.context = self.u.context_save()
        self.table, self.count = 0, 0
        self.cell = self.selected = self.store_pc = None
        self.capture_store = True

        def read(uc, access, address, size, value, user):
            address |= 0x80000000
            if size == 4 and self.table <= address < self.table+self.count*4:
                self.cell = address

        def store(uc, access, address, size, value, user):
            if (self.capture_store and address & 0x1FFFFFFF == (self.OBJ+0x24) & 0x1FFFFFFF
                    and size == 4):
                self.selected = value & 0xFFFFFFFF
                self.store_pc = self.u.reg_read(self.reg.UC_MIPS_REG_PC)
                uc.emu_stop()

        self.u.hook_add(UC_HOOK_MEM_READ, read)
        self.u.hook_add(UC_HOOK_MEM_WRITE, store)

    def write(self, address, data):
        self.u.mem_write(address & 0x1FFFFFFF, data)

    def run(self, pc, table, count, subtype, frame=0, behaviour=0, direction=1,
            animation=0, offset=0):
        obj = bytearray(0x200)
        obj[0] = 1
        obj[2:4] = bytes((0x30, subtype))
        obj[0x69] = direction
        struct.pack_into('<H', obj, 0x2E, frame)
        struct.pack_into('<I', obj, 0x40, self.OBJ+0x10)
        struct.pack_into('<H', obj, 0xB4, animation)
        struct.pack_into('<H', obj, 0xB8, behaviour)
        self.write(self.OBJ, bytes(obj))
        self.table, self.count = table, count
        self.cell = self.selected = self.store_pc = None
        self.capture_store = True
        self.u.context_restore(self.context)
        for reg, value in ((self.reg.UC_MIPS_REG_SP, 0x803F0000),
                           (self.reg.UC_MIPS_REG_RA, self.RETURN),
                           (self.reg.UC_MIPS_REG_A0, self.OBJ),
                           (self.reg.UC_MIPS_REG_A1, offset),
                           (self.reg.UC_MIPS_REG_A2, 0)):
            self.u.reg_write(reg, value)
        self.u.emu_start(pc, self.RETURN, count=1000)
        if self.cell is None or self.selected is None:
            raise AssertionError(f'No native animation selection at {pc:08X}, subtype {subtype}')
        return dict(routine=f'{pc:08X}', subtype=subtype, facing=frame, behaviour=behaviour,
                    contact_direction=direction, selector_argument=offset,
                    pointer_cell=f'{self.cell:08X}', index=(self.cell-table)//4,
                    script=f'{self.selected:08X}', store_pc=f'{self.store_pc:08X}')

    def play(self, script):
        """Check one full pass using the retail AnimLoadDuration/AnimAdvance."""
        self.capture_store = False
        self.table = self.count = 0
        start = int(script['start']['address'], 16)
        self.write(self.OBJ, bytes(0x200))
        self.write(self.OBJ+0x24, struct.pack('<I', start))

        def call(pc):
            self.u.context_restore(self.context)
            self.u.reg_write(self.reg.UC_MIPS_REG_SP, 0x803F0000)
            self.u.reg_write(self.reg.UC_MIPS_REG_RA, self.RETURN)
            self.u.reg_write(self.reg.UC_MIPS_REG_A0, self.OBJ)
            self.u.emu_start(pc, self.RETURN, count=1000)
            assert self.u.reg_read(self.reg.UC_MIPS_REG_PC) == self.RETURN
            return self.u.reg_read(self.reg.UC_MIPS_REG_V0)

        call(0x80020DE4)  # JP AnimLoadDuration
        total = sum(s['ticks'] for s in script['steps'])
        for _ in range(total):
            returned = call(0x80020E38)  # JP AnimAdvance
        pointer = struct.unpack('<I', bytes(self.u.mem_read((self.OBJ+0x24) & 0x1FFFFFFF, 4)))[0]
        expected = start if script['terminal'] == 'loop' else int(script['steps'][-1]['address'], 16)
        assert pointer == expected
        assert returned == (script['terminal'] == 'hold')
        return dict(script=f'{start:08X}', first_pass_ticks=total,
                    after_first_pass=f'{pointer:08X}', terminal=script['terminal'],
                    native_advance_return=returned)


def tunnel_comparison(retail, orphan, green):
    """Compare the cut fragments with the JP retail tunnel teller's 15 slots."""
    asset = next(a for groups in retail.project.ldars.values() for group in groups for a in group.assets
                 if a.kind == 'INS' and a.source and a.source.path == 'SYSTEM/INFO3.BIN')
    data = bytes(retail.project.asset_data(asset))
    digest = hashlib.sha1(data).hexdigest()
    assert digest == 'c5284a56eaa9846752d8ade2a37b2dacbd3842a5'
    base, definition, table = retail.base, 0x800F033C, 0x800F068C
    assert struct.unpack_from('<4BHhI', data, definition-base) == (2, 4, 2, 4, 3, 3, table)
    # Four-way tunnel tables alias slots 0/2, 4/6 and 8/10. The compact cut
    # copies retain three distinct orientations, without those alias entries.
    mapping = (1, 0, 3, 5, 4, 7, 9, 8, 11, 12, 13, 14)
    compared, changed = [], []
    for compact_index, tunnel_index in enumerate(mapping):
        ptr = struct.unpack_from('<I', data, table-base+tunnel_index*4)[0]
        pc, steps = ptr, []
        for _ in range(64):
            frame, box, argument, control = struct.unpack_from('<HHhH', data, pc-base)
            steps.append((frame, box, argument, control))
            if control & 0xC000:
                if control & 0x4000:
                    assert struct.unpack_from('<I', data, pc-base+8)[0] == ptr
                break
            pc += 8
        else:
            raise AssertionError('Unbounded teller comparison')
        for copy, delta in ((orphan, 157), (green, 194)):
            current = copy[compact_index]['steps']
            assert len(current) == len(steps)
            for cut, (frame, box, argument, control) in zip(current, steps, strict=True):
                assert cut['frame'] == frame+delta
                assert (cut['box'], cut['argument'], cut['ticks']) == (box, argument, control & 0x3FFF)
        cut_control = int(orphan[compact_index]['steps'][-1]['control'], 16)
        if cut_control != steps[-1][3]:
            assert cut_control & 0xC000 == 0x8000 and steps[-1][3] & 0xC000 == 0x4000
            changed.append(compact_index)
        compared.append(dict(compact_index=compact_index, tunnel_index=tunnel_index,
            tunnel_script=f'{ptr:08X}', tunnel_final_control=f'{steps[-1][3]:04X}',
            cut_final_control=f'{cut_control:04X}'))
    assert changed == [3, 4, 5, 6, 7, 8, 10, 11]
    return dict(file=asset.source.path, sha1=digest, definition=f'{definition:08X}',
        definition_offset=f'{definition-base:X}', table=f'{table:08X}', table_offset=f'{table-base:X}',
        compact_to_tunnel_slots=list(mapping), comparisons=compared,
        frame_delta_orphan=157, frame_delta_green=194,
        same_frames_relative_to_origin_boxes_arguments_and_ticks=True,
        cut_hold_replaces_tunnel_loop_in_compact_slots=changed,
        exact_binary_copy=False)


def split_address_candidates(retail, ranges):
    """Overinclusive LUI/low pairs within eight instructions, not a CFG proof."""
    found = []
    for name, base, data, _header in retail.regions:
        words = region_words(data)
        for i, word in enumerate(words):
            op = word >> 26
            if op not in (8, 9, 13, 32, 33, 35, 36, 37, 40, 41, 43):
                continue
            imm = word & 0xFFFF
            low = imm if op == 13 or imm < 0x8000 else imm-0x10000
            for j in range(max(0, i-8), i):
                if words[j] >> 26 != 15:
                    continue
                address = ((words[j] & 0xFFFF) << 16)+low
                if any(start <= address < end for start, end in ranges):
                    found.append(dict(file=name, lui_pc=f'{base+j*4:08X}',
                                      low_pc=f'{base+i*4:08X}', candidate=f'{address:08X}'))
    return found


def audit(cue):
    retail = Retail(cue)
    towns = villages(retail.overlay, retail.base)
    result = dict(format=1, main_sha1=MAIN_SHA1, info2_sha1=JP_INFO2_SHA1,
                  reference_scope='Aligned full 32-bit pointers in resident MAIN and INFO2. '
                  'Native selector replay and direct setter call analysis are recorded separately; '
                  'no proof against arbitrary computed/modified execution.',
                  actor_tables=[], orphan_candidates=[], native_selector_probes=[], controls={})
    for number, info in TOWNS.items():
        definitions = []
        for subtype, (table, count) in enumerate(info['tables']):
            address = info['defs']+subtype*12
            box0, box1, box2, box3, page, slot, pointer = struct.unpack('<4BHhI', retail.read(address, 12))
            assert pointer == table and slot == 11
            scripts = []
            for index in range(count):
                cell = table+index*4
                ptr = retail.u32(cell)
                scripts.append(dict(index=index, pointer_cell=retail.where(cell),
                                    literal_users=retail.pointers[ptr], **retail.script(ptr)))
            definitions.append(dict(subtype=subtype, **retail.where(address),
                box=[box0, box1, box2, box3], page_offset=page, spr_slot=slot,
                table=retail.where(table), pointer_count=count, scripts=scripts,
                residents=[r.index+1 for r in towns[number].residents if r.subtype == subtype]))
        result['actor_tables'].append(dict(area=info['area'], set=number, definitions=definitions))

    definitions = {a['area']: a['definitions'] for a in result['actor_tables']}
    # New candidates: beyond the native 0..11 idle/move/talk selector range.
    # Stone's lifting scripts are already described upstream and stay a control.
    for area, subtype, indexes, classification in (
            (11, 0, [16], 'unselected short actor action'),
            (11, 1, [16, 17], 'unselected short actor actions'),
            (11, 3, list(range(16, 28)), 'unselected 12-script tail; no definition points to its start'),
            (17, 0, [16], 'unselected repeating actor action'),
            (17, 1, [16], 'unselected repeating actor action')):
        definition = definitions[area][subtype]
        scripts = [definition['scripts'][i] for i in indexes]
        result['orphan_candidates'].append(dict(area=area, subtype=subtype,
            classification=classification, table=definition['table'],
            residents_using_table_prefix=definition['residents'],
            scripts=scripts, frames=sorted({s['frame'] for script in scripts for s in script['steps']})))

    orphan = definitions[11][3]['scripts'][16:28]
    green = definitions[11][4]['scripts']
    for a, b in zip(orphan, green, strict=True):
        assert a['terminal'] == b['terminal'] == 'hold'
        assert len(a['steps']) == len(b['steps'])
        for x, y in zip(a['steps'], b['steps'], strict=True):
            assert y['frame']-x['frame'] == 37
            assert all(x[k] == y[k] for k in ('box', 'argument', 'control', 'ticks'))
    assert {s['frame'] for a in orphan for s in a['steps']} == set(range(167, 204))
    assert not retail.pointers[0x80106330]
    assert all(len(a['literal_users']) == 1 for a in orphan)
    result['wood_teller_template_comparison'] = dict(
        orphan_pointer_window=retail.where(0x80106330), end_exclusive='80106360',
        orphan_payload_start=retail.where(0x80106AB0), payload_end_exclusive='80106D00',
        payload_bytes=0x250, scripts=12, distinct_frames=37,
        declared_green_table=retail.where(0x80106360), frame_delta_to_green=37,
        all_nonframe_fields_and_terminal_modes_equal=True,
        literal_references_to_orphan_window_start=retail.pointers[0x80106330],
        identity='Animation-template correspondence, not recovered pixels/palette or a named extra resident.')
    result['jp_tunnel_teller_comparison'] = tunnel_comparison(retail, orphan, green)
    ranges = [(0x80106330, 0x80106360)]
    for candidate in result['orphan_candidates']:
        scripts = candidate['scripts']
        start = min(int(s['start']['address'], 16) for s in scripts)
        end = max(int(s['address'], 16)+8+(4 if int(s['control'], 16) & 0x4000 else 0)
                  for script in scripts for s in script['steps'])
        ranges.append((start, end))
        candidate['payload_start'] = retail.where(start)
        candidate['payload_end_exclusive'] = f'{end:08X}'
        candidate['payload_bytes'] = end-start
        candidate['all_literal_references_into_payload'] = [
            dict(target=f'{target:08X}', users=users)
            for target, users in sorted(retail.pointers.items()) if start <= target < end]
        normal_frames = {s['frame'] for definition in definitions[candidate['area']]
                         for script in definition['scripts'][:12] for s in script['steps']}
        assert not normal_frames.intersection(candidate['frames'])
    result['bounded_split_address_check'] = dict(
        scope='Any LUI within eight preceding instructions plus ADDI(U)/ORI/load/store low half; '
              'register agreement is deliberately not required, giving an overinclusive candidate set.',
        candidates=split_address_candidates(retail, ranges))
    assert not result['bounded_split_address_check']['candidates']
    assert sum(c['payload_bytes'] for c in result['orphan_candidates']) == 840

    # Execute native selectors over every defined subtype and ordinary facing,
    # behaviour and contact-direction value; stop before animation services.
    probe = SelectorProbe(retail)
    for number, info in TOWNS.items():
        for resident in towns[number].residents:
            table, count = info['tables'][resident.subtype]
            result['native_selector_probes'].append(dict(area=info['area'], kind='preserved initializer',
                resident=resident.index+1, **probe.run(info['init'], table, count, resident.subtype,
                    frame=resident.frame, animation=resident.animation)))
        for subtype, (table, count) in enumerate(info['tables']):
            for frame in range(4):
                for behaviour in range(5):
                    result['native_selector_probes'].append(dict(area=info['area'], kind='normal actor step',
                        **probe.run(info['step'], table, count, subtype, frame, behaviour)))
                result['native_selector_probes'].append(dict(area=info['area'], kind='talk entry',
                    **probe.run(info['talk'], table, count, subtype, direction=frame+1)))
    assert len(result['native_selector_probes']) == 377
    assert all(p['index'] < 12 for p in result['native_selector_probes'])
    result['green_teller_selector_layout'] = dict(
        initializer=next(p for p in result['native_selector_probes']
            if p['area'] == 11 and p['kind'] == 'preserved initializer' and p['resident'] == 12),
        preserved_idle_facing=next(p for p in result['native_selector_probes']
            if p['area'] == 11 and p['kind'] == 'normal actor step' and p['subtype'] == 4
            and p['facing'] == 3 and p['behaviour'] == 0),
        talk_directions=[p for p in result['native_selector_probes']
            if p['area'] == 11 and p['kind'] == 'talk entry' and p['subtype'] == 4])
    result['native_animation_playback'] = [dict(area=c['area'], subtype=c['subtype'], index=s['index'],
        **probe.play(s)) for c in result['orphan_candidates'] for s in c['scripts']]

    # Follow every direct call of the exported direction setters, including the
    # town scene functions. Inlined patrol/talk selectors are covered above.
    words = region_words(retail.overlay)
    setters = {info['setter']: info['area'] for info in TOWNS.values()}
    sites, _jumps, owners = analyse(words, retail.base, setters,
        lambda a: retail.u32(a) if any(base <= a <= base+len(data)-4
            for _name, base, data, _header in retail.regions) else None)
    calls = []
    for pc, args in sorted(sites.items()):
        target = 0x80000000 | (retail.u32(pc) & 0x3FFFFFF) << 2
        values = sorted(args[1].consts) if args[1].consts is not None else None
        assert values is not None and set(values) <= {0, 4, 8}
        calls.append(dict(area=setters[target], **retail.where(pc),
                          target=f'{target:08X}', owner=f'{owners[pc]:08X}', offsets=values))
    result['native_scene_setter_calls'] = calls
    result['controls']['already_documented_stone_lifting'] = definitions[16][2]['scripts'][16:24]
    result['controls']['known_iron_main_animation_bank'] = dict(
        definition=definitions[17][4]['address'], table=definitions[17][4]['table'],
        pointer_count=24, frames=sorted({s['frame'] for a in definitions[17][4]['scripts'] for s in a['steps']}))
    # Forcing a high selector is a positive decoder/probe control; it is not an
    # original game path and is kept out of the ordinary selector count.
    result['controls']['forced_high_selectors'] = []
    for number, subtype in ((13, 3), (14, 2), (15, 1)):
        info = TOWNS[number]
        table, count = info['tables'][subtype]
        trace = probe.run(info['setter'], table, count, subtype, offset=16)
        assert trace['index'] == 16
        result['controls']['forced_high_selectors'].append(dict(area=info['area'], **trace))

    # New-list checks: the complete 28-byte resident terminators contain no
    # trailing actor; the APD assets also have no post-terminator payload.
    result['controls']['resident_terminators'] = []
    for number in (13, 14, 15, 16):
        town = towns[number]
        first = town.residents[0]
        needle = struct.pack('<hh', first.x, first.y)
        starts = [at-20 for at in range(20, len(retail.overlay)-3, 2)
                  if retail.overlay[at:at+4] == needle]
        start = next(at for at in starts if struct.unpack_from('<h', retail.overlay, at+24)[0] == first.subtype)
        end = retail.base+start+len(town.residents)*28
        assert retail.read(end, 28) == b'\xff\0'+bytes(26)
        result['controls']['resident_terminators'].append(dict(area=town.area,
            **retail.where(end), bytes=28, zero_after_type=True))
    seen, apd_banks = set(), 0
    for groups in retail.project.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind != 'APD':
                    continue
                data = retail.project.asset_data(asset)
                key = hashlib.sha1(data).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                parsed = parse_apd(data)
                assert len(data) == (len(parsed)+1)*16
                assert data[len(parsed)*16+2] == 255
                apd_banks += 1
    result['controls']['unique_apd_banks_without_post_terminator_data'] = apd_banks
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cue')
    parser.add_argument('--output', type=Path,
                        default=Path('work/cut_village_research/resident_orphans_jp.json'))
    args = parser.parse_args()
    result = audit(args.cue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    print('JP MAIN/INFO2 verified. 17 high-slot script candidates; Wood 37-frame template delta verified.')
    print('377 native normal selector probes chose slots 0..11; scene setter calls:',
          len(result['native_scene_setter_calls']))
    print('APD tail controls:', result['controls']['unique_apd_banks_without_post_terminator_data'])
    print('Decoded evidence:', args.output)


if __name__ == '__main__':
    main()
