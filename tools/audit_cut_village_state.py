"""JP-only cut-village state/consumer checks, using original MIPS in memory.

No ROM is edited. External engine services are recorded and stubbed unless
explicitly included; this is a bounded routine experiment, not a PSX game run.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_cut_resident_orphans import Retail
from formats.level.cut_towns import villages
from formats.text.export import collect, plain
from formats.text.mips_args import region_words


PHASE = 0x8009EB50
OBJ, CTRL, NPC = 0x801E0000, 0x801E1000, 0x801E2000
RETURN = 0x80001000
OVERLAYS = {
    'SYSTEM/X11.BIN': '9ec2628e76ff4689408ed19400ec0851637e665f',
    'SYSTEM/X16.BIN': 'b43230d3a7a49203207f6068eb6dc437d305f12b',
}


class Native:
    def __init__(self, retail, overlay=None):
        from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
        from unicorn import UC_HOOK_CODE
        from unicorn import mips_const
        self.reg = mips_const
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0, 0x400000)
        self.u.mem_map(0x1F800000, 0x1000)
        for _name, base, data, _header in retail.regions:
            self.write(base, data)
        if overlay is not None:
            self.write(retail.base, overlay)
        self.context = self.u.context_save()
        self.allowed = []
        self.calls, self.reads, self.writes = [], [], []
        self.watch = []
        self.stop_calls = set()

        def code(uc, address, size, user):
            if address == RETURN:
                return
            if any(start <= address < end for start, end in self.allowed):
                # Trace effective addresses from the instruction and register
                # values. Global Unicorn MIPS memory hooks break the return of
                # this leaf on the installed backend; no guest bytes are patched.
                word = self.integer(address)
                op = word >> 26
                if op in (32, 33, 34, 35, 36, 37, 38, 40, 41, 42, 43, 46):
                    width = {32:1,33:2,34:4,35:4,36:1,37:2,38:4,40:1,41:2,42:4,43:4,46:4}[op]
                    rs, rt = word >> 21 & 31, word >> 16 & 31
                    imm = word & 0xFFFF
                    if imm & 0x8000:
                        imm -= 0x10000
                    target = (uc.reg_read(self.reg.UC_MIPS_REG_0+rs)+imm) & 0xFFFFFFFF
                    if any(start <= target < end for start, end in self.watch):
                        item = dict(pc=f'{address:08X}', address=f'{target:08X}', size=width)
                        if op >= 40:
                            value = uc.reg_read(self.reg.UC_MIPS_REG_0+rt)
                            item['value'] = f'{value & ((1 << (width*8))-1):0{width*2}X}'
                            self.writes.append(item)
                        else:
                            self.reads.append(item)
                return
            args = [uc.reg_read(getattr(self.reg, f'UC_MIPS_REG_A{i}')) for i in range(4)]
            call = dict(target=f'{address:08X}', return_address=f'{uc.reg_read(self.reg.UC_MIPS_REG_RA):08X}',
                        args=[f'{a:08X}' for a in args])
            if address == 0x8002E42C:
                call['position_hex'] = self.read(args[2], 12).hex()
            self.calls.append(call)
            if address in self.stop_calls:
                uc.emu_stop()
            else:
                uc.reg_write(self.reg.UC_MIPS_REG_V0, 0)
                uc.reg_write(self.reg.UC_MIPS_REG_PC, uc.reg_read(self.reg.UC_MIPS_REG_RA))

        self.u.hook_add(UC_HOOK_CODE, code)

    def write(self, address, data):
        self.u.mem_write(address & 0x1FFFFFFF, bytes(data))

    def read(self, address, size):
        return bytes(self.u.mem_read(address & 0x1FFFFFFF, size))

    def integer(self, address, value=None, size=4):
        if value is None:
            return int.from_bytes(self.read(address, size), 'little')
        self.write(address, int(value & ((1 << (size*8))-1)).to_bytes(size, 'little'))

    def call(self, pc, obj=OBJ, incoming_s0=0):
        self.u.context_restore(self.context)
        for register, value in ((self.reg.UC_MIPS_REG_SP, 0x803F0000),
                                (self.reg.UC_MIPS_REG_RA, RETURN),
                                (self.reg.UC_MIPS_REG_A0, obj),
                                (self.reg.UC_MIPS_REG_S0, incoming_s0)):
            self.u.reg_write(register, value)
        self.u.emu_start(pc, RETURN, count=20000)
        final = self.u.reg_read(self.reg.UC_MIPS_REG_PC)
        assert final == RETURN or final in self.stop_calls, f'Instruction bound reached at {final:08X}'


def asset_code(retail, source):
    asset = next(a for groups in retail.project.ldars.values() for group in groups for a in group.assets
                 if a.kind == 'INS' and a.source and a.source.path == source)
    data = bytes(retail.project.asset_data(asset))
    assert hashlib.sha1(data).hexdigest() == OVERLAYS[source]
    return data


def prop_object(prop):
    data = bytearray(0x200)
    data[0:4] = bytes((1, 0, 0x1D, prop.subtype))
    data[0xA] = 0xD
    data[0xE] = prop.kind
    struct.pack_into('<h', data, 0x12, prop.x)
    struct.pack_into('<h', data, 0x16, prop.y)
    struct.pack_into('<H', data, 0xB4, prop.animation)
    struct.pack_into('<H', data, 0xB6, prop.room)
    struct.pack_into('<H', data, 0xB8, prop.index)
    return data


def scenery_state(vm):
    pointer = vm.integer(OBJ+0x24)
    return dict(phase=vm.integer(PHASE, size=1), requested_animation=vm.integer(OBJ+0xB4, size=2),
        script=f'{pointer:08X}', drawn_frame=vm.integer(pointer, size=2),
        x=int.from_bytes(vm.read(OBJ+0x12, 2), 'little', signed=True),
        y=int.from_bytes(vm.read(OBJ+0x16, 2), 'little', signed=True),
        sorting_kind=vm.integer(OBJ+0xE, size=1))


def stone_repair(retail):
    town = villages(retail.overlay, retail.base)[14]
    vm = Native(retail)
    # The complete native update chain, plus the pure duration loader. Drawing
    # queue registration is a service stub; no renderer or sprite bank is used.
    vm.allowed = [(0x800F1CFC, 0x800F1F84+372), (0x800FCD78, 0x800FCEB0),
                  (0x800FD194, 0x800FD194+368), (0x80020DE4, 0x80020E00)]
    vm.watch = [(PHASE, PHASE+1), (OBJ+0x24, OBJ+0x28)]
    vm.write(OBJ, prop_object(town.props[5]))
    vm.call(0x800F1F84)
    initial = scenery_state(vm)
    assert initial['requested_animation'] == initial['drawn_frame'] == 10
    vm.write(CTRL, bytes(0x200))
    vm.integer(CTRL+4, 1, 1)
    # No phase-1 seed: idle controller and prop updates leave phase zero.
    for _ in range(90):
        vm.call(0x800FD194, CTRL)
        vm.call(0x800F1F84)
    idle = scenery_state(vm)
    assert idle == initial and vm.integer(CTRL+5, size=1) == 0
    vm.integer(PHASE, 1, 1)  # Explicit synthetic seed, not an original trigger.
    transitions = []
    previous = 1
    for tick in range(1, 65):
        vm.call(0x800FD194, CTRL)
        vm.call(0x800F1F84)
        current = scenery_state(vm)
        if current['phase'] != previous:
            transitions.append(dict(tick=tick, **current))
            previous = current['phase']
    assert [s['phase'] for s in transitions] == [2, 3, 4]
    assert [s['tick'] for s in transitions] == [32, 62, 63]
    assert [s['requested_animation'] for s in transitions] == [11, 12, 12]
    assert all(s['drawn_frame'] == 10 and s['script'] == initial['script'] for s in transitions)
    continuous = scenery_state(vm)
    pointer_writes = [w for w in vm.writes if w['address'] == f'{OBJ+0x24:08X}']
    assert len(pointer_writes) == 1  # The initializer, never the repair updater.
    vm.write(OBJ, prop_object(town.alternate_props[5]))
    vm.call(0x800F1F84)
    reloaded = scenery_state(vm)
    assert reloaded['phase'] == 4 and reloaded['requested_animation'] == 12 and reloaded['drawn_frame'] == 15
    assert reloaded['script'] != continuous['script']
    return dict(phase_address=f'{PHASE:08X}', controller='800FD194', scene='800FCD78',
        scenery_handler='800F1F84', updater='800F1E88', normal_prop=asdict(town.props[5]),
        alternate_prop=asdict(town.alternate_props[5]), initializer=initial, idle_90_updates=idle,
        after_synthetic_phase_1=transitions, continuous_result=continuous,
        reinitialized_phase_4_result=reloaded, animation_pointer_writes_before_reinitialization=pointer_writes,
        watched_instruction_stores=vm.writes, external_services=sorted({c['target'] for c in vm.calls}))


def stale_craftsman_position(retail):
    results = []
    for poison, marker in ((0x80330000, bytes(range(12))), (0x80340000, bytes(range(0x40, 0x4C)))):
        vm = Native(retail)
        vm.allowed = [(0x800FCEB0, 0x800FCEB0+496)]
        vm.watch = [(poison, poison+0x20), (NPC, NPC+0xA0)]
        vm.stop_calls = {0x8002E42C}
        vm.write(CTRL, bytes(0x200))
        vm.write(NPC, bytes(0x200))
        vm.write(poison+0x10, marker)
        vm.write(NPC+0x10, bytes([0xCC])*12)
        vm.integer(0x800A0E88, NPC)  # SCRIPT_OBJECTS[8], resident #9.
        vm.call(0x800FCEB0, CTRL, incoming_s0=poison)
        message = vm.calls[0]
        assert int(message['args'][0], 16) == 2 and int(message['args'][1], 16) == 1
        assert message['position_hex'] == marker.hex()
        assert vm.integer(NPC+5, size=1) == 2
        results.append(dict(incoming_s0=f'{poison:08X}', actual_resident=f'{NPC:08X}',
            message=message, watched_reads=vm.reads, watched_writes=vm.writes))
    # The actual caller keeps its own controller in s0. Demonstrate the concrete
    # caller-chain consequence, not just sensitivity to arbitrary register data.
    vm = Native(retail)
    vm.allowed = [(0x800FCEB0, 0x800FCEB0+496), (0x800FD194, 0x800FD194+368)]
    vm.watch = [(CTRL+0x10, CTRL+0x1C), (NPC, NPC+0xA0)]
    vm.stop_calls = {0x8002E42C}
    vm.write(CTRL, bytes(0x200))
    vm.write(CTRL+4, bytes((1,3,0)))
    marker = bytes(range(0x80, 0x8C))
    vm.write(CTRL+0x10, marker)
    vm.write(NPC, bytes(0x200))
    vm.write(NPC+0x10, bytes([0xCC])*12)
    vm.integer(0x800A0E88, NPC)
    vm.call(0x800FD194, CTRL)
    assert vm.calls[-1]['position_hex'] == marker.hex()
    return dict(routine='800FCEB0', resident=9, resident_pointer='800A0E88', trials=results,
        actual_controller_dispatch=dict(controller=f'{CTRL:08X}', resident=f'{NPC:08X}',
            controller_position=marker.hex(), resident_position=(bytes([0xCC])*12).hex(),
            message=vm.calls[-1], reads=vm.reads))


def sorting_kinds(retail):
    trials = []
    for ys in ((10, 100), (100, 10)):
        vm = Native(retail)
        vm.allowed = [(0x800EE910, 0x800EEDD4)]
        objects = [OBJ+i*0x200 for i in range(4)]
        for address, kind, y in zip(objects, (0, 0, 1, 2), (*ys, 300, -300), strict=True):
            data = bytearray(0x200)
            data[2], data[0xE] = 0x1D, kind
            struct.pack_into('<h', data, 0x16, y)
            vm.write(address, data)
        vm.integer(0x1F800246, 0, 2)
        vm.integer(0x1F80024A, 4, 2)
        vm.integer(0x1F800220, 0x80370000)
        vm.write(0x80370000, struct.pack('<4I', *objects))
        vm.call(0x800EE910)
        depths = [int.from_bytes(vm.read(a+0xF, 1), 'little', signed=True) for a in objects]
        assert depths[2:] == [-12, 12]
        assert depths[:2] == ([-9, -10] if ys[0] < ys[1] else [-10, -9])
        trials.append(dict(kind_0_y=list(ys), kind_0_depth=depths[:2], kind_1_depth=depths[2], kind_2_depth=depths[3]))
    return dict(routine='800EE910', field_offset='0E', depth_field_offset='0F', trials=trials)


def direct_memory_scan(retail):
    """Conservative straight-line constant tracking; not complete alias analysis."""
    regions = [('SLPS_011.44', retail.exe.base, retail.exe.data[0x800:])]
    seen = set()
    for groups in retail.project.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind != 'INS' or not asset.source:
                    continue
                data = bytes(retail.project.asset_data(asset))
                digest = hashlib.sha1(data).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                regions.append((asset.source.path, retail.base, data))
    accesses, pointers = [], []
    for name, base, data in regions:
        regs = [None]*32
        regs[0] = 0
        clear_after = -1
        words = region_words(data)
        for i, word in enumerate(words):
            pc = base+i*4
            if word == PHASE:
                pointers.append(dict(source=name, pc=f'{pc:08X}'))
            op, rs, rt, rd = word >> 26, word >> 21 & 31, word >> 16 & 31, word >> 11 & 31
            low = word & 0xFFFF
            signed = low if low < 0x8000 else low-0x10000
            if op in (32, 33, 35, 36, 37, 40, 41, 43):
                width = {32:1, 33:2, 35:4, 36:1, 37:2, 40:1, 41:2, 43:4}[op]
                address = None if regs[rs] is None else (regs[rs]+signed) & 0xFFFFFFFF
                if address is not None and address <= PHASE < address+width:
                    accesses.append(dict(source=name, pc=f'{pc:08X}', operation=op,
                        address=f'{address:08X}', width=width, write=op >= 40,
                        value=None if op < 40 or regs[rt] is None else f'{regs[rt]:08X}'))
                if op < 40:
                    regs[rt] = None
            elif op == 15:
                regs[rt] = low << 16
            elif op in (8, 9, 13):
                regs[rt] = None if regs[rs] is None else ((regs[rs]+signed) if op in (8,9) else regs[rs] | low) & 0xFFFFFFFF
            elif op == 0:
                fn = word & 63
                if fn in (32, 33, 37):
                    a, b = regs[rs], regs[rt]
                    regs[rd] = None if a is None or b is None else ((a | b) if fn == 37 else a+b) & 0xFFFFFFFF
                elif fn == 0:
                    regs[rd] = None if regs[rt] is None else regs[rt] << (word >> 6 & 31) & 0xFFFFFFFF
                elif fn not in (8, 9, 12, 13, 24, 25, 26, 27):
                    regs[rd] = None
            elif op not in (1, 2, 3, 4, 5, 6, 7, 40, 41, 42, 43, 46):
                regs[rt] = None
            regs[0] = 0
            if i == clear_after:
                regs = [None]*32
                regs[0] = 0
            if op in (1, 2, 3, 4, 5, 6, 7) or op == 0 and word & 63 in (8, 9):
                clear_after = i+1
    writes = [a for a in accesses if a['write']]
    assert not any(a['value'] == '00000001' for a in writes)
    assert all('INFO2' in a['source'] for a in writes)
    return dict(scope='MAIN plus each unique loaded INS payload; straight-line register constants '
        'reset after branches/calls and their delay slot; misses indirect/indexed/computed aliases.',
        region_count=len(regions), regions=[dict(source=n, bytes=len(d), sha1=hashlib.sha1(d).hexdigest())
                                         for n, _b, d in regions],
        accesses=accesses, literal_phase_pointers=pointers, direct_constant_1_store_found=False)


def retail_clock_control(retail, x16):
    vm = Native(retail, x16)
    vm.allowed = [(0x80116A2C, 0x80116A2C+308), (0x8001C988, 0x8001C988+188)]
    vm.watch = [(PHASE, PHASE+1), (0x8009E9AD, 0x8009E9AE)]  # event 0x61
    vm.write(OBJ, bytes(0x200))
    vm.integer(OBJ+6, 1, 1)
    vm.integer(PHASE, 0x55, 1)
    vm.call(0x80116A2C)
    assert vm.integer(PHASE, size=1) == 0x55
    assert vm.integer(0x8009E9AD, size=1) == 255
    return dict(routine='80116A2C', executed_event_complete='8001C988',
        cut_scenery_phase_before='55', cut_scenery_phase_after='55',
        event_61_address='8009E9AD', event_61_after='FF',
        native_writes=vm.writes, external_services=vm.calls)


def wood_hint_text(retail, x11):
    bank = next(b for b in collect(retail.project, area=11) if b.offset == 0x86E0)
    # JP side-view control: selector calls and the event request in the retained
    # thanks routine. Its entry is confirmed by its native dispatcher below.
    words = region_words(x11)
    from formats.text.mips_args import Function, prologues
    matches = []
    starts = prologues(words)+[len(words)]
    for start, end in zip(starts, starts[1:]):
        f = Function(words, retail.base, start, end, lambda a: retail.u32(a)
                     if a < retail.base else struct.unpack_from('<I', x11, a-retail.base)[0]
                     if 0 <= a-retail.base <= len(x11)-4 else None)
        found = f.calls({0x8002E42C, 0x8001C88C})
        calls = []
        for pc, args in sorted(found.items()):
            target = 0x80000000 | (words[(pc-retail.base)//4] & 0x3FFFFFF) << 2
            calls.append(dict(pc=f'{pc:08X}', target=f'{target:08X}',
                args=[sorted(a.consts) if a.consts is not None else None for a in args]))
        if any(c['target'] == '8001C88C' and c['args'][0] == [0x4F] for c in calls):
            pairs = [(g, line) for c in calls if c['target'] == '8002E42C'
                     for g in c['args'][0] or [] for line in c['args'][1] or []]
            if (2,4) in pairs and (2,5) in pairs:
                matches.append(dict(routine=f'{retail.base+start*4:08X}', calls=calls))
    assert len(matches) == 1
    assert matches[0]['routine'] == '80117AFC'
    dispatcher_calls = []
    for pc, target in ((0x801183A4,0x80117AFC), (0x801183B4,0x80117D08)):
        assert struct.unpack_from('<I',x11,pc-retail.base)[0] == 0x0C000000 | (target & 0x0FFFFFFF) >> 2
        dispatcher_calls.append(dict(pc=f'{pc:08X}', target=f'{target:08X}'))
    trials = []
    for state, expected_line in ((0,4),(1,5)):
        vm = Native(retail,x11)
        vm.allowed = [(0x80117AFC,0x80117D08)]
        vm.stop_calls = {0x8002E42C}
        vm.write(OBJ,bytes(0x200))
        vm.integer(OBJ+3,2,1)
        vm.integer(OBJ+6,state,1)
        vm.integer(OBJ+0x68,1,1)
        vm.integer(OBJ+0x90,NPC)
        vm.integer(NPC+4,2,1)
        vm.call(0x80117AFC)
        message = next(c for c in vm.calls if c['target'] == '8002E42C')
        assert [int(a,16) for a in message['args'][:2]] == [2,expected_line]
        trials.append(dict(state=state,message=message))
    wfm_asset = next(a for groups in retail.project.ldars.values() for group in groups for a in group.assets
                     if a.kind == 'WFM' and a.source and a.source.path == bank.source and a.offset == bank.offset)
    wfm_sha1 = hashlib.sha1(retail.project.asset_data(wfm_asset)).hexdigest()
    assert wfm_sha1 == '3eaa362d4c39bc8048deebdde12a031bdb9d05ee'
    return dict(orphan_info2_helper='800F2F24', source=bank.source, wfm_offset=f'{bank.offset:X}',
        wfm_sha1=wfm_sha1,
        entries=[dict(index=i, group=2, line=i-191, japanese=plain(bank.wfm.dialogues[i])) for i in (195,196)],
        event=0x4F, live_x11_thanks=matches[0],
        dispatcher='80118104', dispatcher_calls=dispatcher_calls, native_message_trials=trials,
        separate_raft_entries=[dict(index=i,group=3,line=i-210,japanese=plain(bank.wfm.dialogues[i]))
                               for i in range(220,225)],
        correction='Generator thanks and Watchtower underground-elevator hint; not raft crafting.')


def stone_craftsman_text(retail):
    bank = next(b for b in collect(retail.project,area=16) if b.offset == 0x6CA8)
    asset = next(a for groups in retail.project.ldars.values() for group in groups for a in group.assets
                 if a.kind == 'WFM' and a.source and a.source.path == bank.source and a.offset == bank.offset)
    digest = hashlib.sha1(retail.project.asset_data(asset)).hexdigest()
    assert digest == 'b70c77d7534df6745263a2df1b7baacb22a78f6d'
    return dict(source=bank.source,wfm_offset=f'{bank.offset:X}',sha1=digest,
        entries=[dict(index=i,group=2,line=i-185,japanese=plain(bank.wfm.dialogues[i])) for i in (185,186,187)],
        dialogue_case=8,resident=9,room=4,position=[26,174],scene='800FCEB0',
        context='Funga drum materials and the Tree of Knowledge hint; no drum-grant call in this scene.')


def audit(cue):
    retail = Retail(cue)
    x11, x16 = (asset_code(retail, path) for path in OVERLAYS)
    assert retail.u32(0x80043A04) == 0x0C011F20  # draw kind 13 -> 80047C80
    assert retail.u32(0x80047D60) == 0x8E220024  # lw v0, actor+24
    assert retail.u32(0x80047D68) == 0x94420000  # lhu frame, script+0
    return dict(format=1, main_sha1=hashlib.sha1(retail.exe.data).hexdigest(),
        info2_sha1=hashlib.sha1(retail.overlay).hexdigest(), overlay_sha1=OVERLAYS,
        draw_consumer=dict(dispatcher='80043728', kind_13_call='80043A04', routine='80047C80',
                           script_pointer_load='80047D60', script_frame_load='80047D68'),
        stone_repair=stone_repair(retail), stone_craftsman=stale_craftsman_position(retail),
        prop_sorting=sorting_kinds(retail), phase_references=direct_memory_scan(retail),
        stone_craftsman_text=stone_craftsman_text(retail),
        retail_clock_control=retail_clock_control(retail,x16), wood_hint=wood_hint_text(retail,x11))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cue')
    parser.add_argument('--output', type=Path, default=Path('work/cut_village_research/state_consumers_jp.json'))
    args = parser.parse_args()
    result = audit(args.cue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf8')
    print('Passed JP native checks: Stone stale animation pointer and unseeded phase candidate, '
          'craftsman stale position, prop sorting kinds, retail repair control, Wood hint correction.')
    print('Decoded evidence:',args.output)


if __name__ == '__main__':
    main()
