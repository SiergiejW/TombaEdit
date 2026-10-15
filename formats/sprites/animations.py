"""Animation scripts: what decides which frame of a sprite bank shows when.

An object's word +24 points at its current step. A step is eight bytes:
the frame number in the object's SPR bank, a hit box number, a signed
argument some routines read (a speed, for instance), and a word whose low
fourteen bits are how many updates the frame stays. Its top two bits say
what follows: 0 the next step, 8000 the end (the frame is held), 4000 a
jump through the pointer stored right after the step, C000 a jump that
also reports the end to the object's routine. The object routines step it
once per update (routines AnimAdvance and AnimJump of the decomp; the
format is described in its include/tomba/anim.h).

Scripts live in the code that uses them: an area overlay (Xnn.BIN, or
INFO.BIN for the towns) for its objects, the executable for Tomba's.
Nothing lists them, so they are found here the way the code reaches them:
from tables of pointers, from addresses built in the code, and from any
other word that points at a run of valid steps. A run counts as a script
only if every frame it names exists in the bank.
"""
import struct
from dataclasses import dataclass, field

import numpy as np

HOLD, JUMP = 0x8000, 0x4000
MAX_STEPS = 256
MAX_TICKS = 20000


@dataclass
class Step:
    frame: int
    box: int
    arg: int
    ticks: int          # updates the frame stays
    flags: int          # 0, HOLD, JUMP or both
    address: int = 0


@dataclass
class Script:
    address: int
    steps: list
    loop: int | None = None     # step the script goes back to, if it loops
    found: set = field(default_factory=set)     # 'table', 'code', 'pointer'
    tables: list = field(default_factory=list)  # [(table address, index)]
    # SPR slots loaded by the routines that name the script or its table:
    # the banks it is most likely drawn from.
    slots: set = field(default_factory=set)
    users: set = field(default_factory=set)     # addresses of those routines

    @property
    def ticks(self):
        return sum(max(1, step.ticks) for step in self.steps)

    @property
    def frames(self):
        return [step.frame for step in self.steps]

    @property
    def ending(self):
        if self.loop is not None:
            return f'loops to step {self.loop + 1}'
        return 'holds its last frame'


class Memory:
    """Code and data images at their load addresses: [(name, base, bytes)]."""

    def __init__(self, regions):
        self.regions = [(name, base, bytes(data)) for name, base, data in regions if data]

    def find(self, address, count=1):
        for name, base, data in self.regions:
            if base <= address and address + count <= base + len(data):
                return data, address - base
        return None, 0

    def inside(self, address, count=1):
        return self.find(address, count)[0] is not None

    def read(self, address, count):
        data, at = self.find(address, count)
        return data[at:at + count]

    def u16(self, address):
        data, at = self.find(address, 2)
        return struct.unpack_from('<H', data, at)[0]

    def u32(self, address):
        data, at = self.find(address, 4)
        return struct.unpack_from('<I', data, at)[0]

    def region(self, address):
        for name, base, data in self.regions:
            if base <= address < base + len(data):
                return name
        return ''


def read_script(memory, address, frame_count=None):
    """The script that starts at `address`, or None where the bytes are not
    one: a step past the bank's frames, a jump outside the code, no end
    within MAX_STEPS steps."""
    steps, seen, loop = [], {}, None
    at = address
    while True:
        if at & 3 or not memory.inside(at, 8) or len(steps) >= MAX_STEPS:
            return None
        if at in seen:
            loop = seen[at]
            break
        frame, box, arg, control = struct.unpack('<HHhH', memory.read(at, 8))
        if (frame_count is not None and frame >= frame_count) or frame >= 0x1000 or box >= 0x100:
            return None
        seen[at] = len(steps)
        steps.append(Step(frame, box, arg, control & 0x3FFF, control & 0xC000, at))
        if not control & 0xC000:
            at += 8
            continue
        if control & 0xC000 == HOLD:
            break
        if not memory.inside(at + 8, 4):
            return None
        target = memory.u32(at + 8)
        if target in seen:
            loop = seen[target]
            break
        at = target
    total = sum(step.ticks for step in steps)
    if not total or total > MAX_TICKS:
        return None
    return Script(address, steps, loop)


# Scratchpad words holding the loaded SPR banks by slot.
SPR_SLOTS = 0x1F8002C8


def code_constants(base, data):
    """{address: [instruction addresses]} for addresses built in MIPS code
    with lui and a following addiu, ori or load/store offset on the same
    register."""
    count = len(data) // 4
    words = np.frombuffer(data[:count * 4], '<u4')
    out = {}
    lui = np.nonzero(words >> 26 == 15)[0]
    for i in lui:
        upper = int(words[i]) & 0xFFFF
        reg = int(words[i]) >> 16 & 31
        for j in range(i + 1, min(i + 8, count)):
            w = int(words[j])
            op, rs, rt = w >> 26, w >> 21 & 31, w >> 16 & 31
            if op in (9, 13, 0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2B) and rs == reg:
                low = w & 0xFFFF
                value = (upper << 16) + (low if op == 13 else (low ^ 0x8000) - 0x8000)
                out.setdefault(value & 0xFFFFFFFF, []).append(base + 4 * j)
                if op in (9, 13) and rt == reg:
                    continue
                break
            if rt == reg and op not in (0x28, 0x29, 0x2B):
                break
    return out


def routines(base, data):
    """Sorted start addresses of the routines in code: where a stack frame
    is opened (addiu sp, sp, -n)."""
    count = len(data) // 4
    words = np.frombuffer(data[:count * 4], '<u4')
    return [base + 4 * int(i) for i in np.nonzero(((words >> 16) == 0x27BD) & ((words & 0x8000) != 0))[0]]


def routine_of(starts, address):
    import bisect
    k = bisect.bisect_right(starts, address) - 1
    return starts[k] if k >= 0 else None


def sniff(memory, frame_count=None, code=()):
    """{address: Script} of the scripts reachable in `memory`. `code` names
    the regions whose instructions are searched for addresses."""
    pointers = {}           # target -> [cells]
    for name, base, data in memory.regions:
        count = len(data) // 4
        words = np.frombuffer(data[:count * 4], '<u4')
        for lo, hi in ((b, b + len(d)) for _, b, d in memory.regions):
            hits = np.nonzero((words >= lo) & (words < hi - 8) & ((words & 3) == 0))[0]
            for i in hits:
                pointers.setdefault(int(words[i]), []).append(base + 4 * int(i))
    built, starts, slot_loads = {}, [], {}
    for name, base, data in memory.regions:
        if name in code:
            constants = code_constants(base, data)
            starts += routines(base, data)
            for value, where in constants.items():
                if memory.inside(value, 8) and not value & 3:
                    built.setdefault(value, []).extend(where)
                if SPR_SLOTS <= value < SPR_SLOTS + 64 and not (value - SPR_SLOTS) & 3:
                    for at in where:
                        slot_loads.setdefault(at, set()).add((value - SPR_SLOTS) // 4)
    starts.sort()
    slots_of = {}
    for at, slots in slot_loads.items():
        slots_of.setdefault(routine_of(starts, at), set()).update(slots)

    def used_by(address):
        return {routine_of(starts, at) for at in built.get(address, ())}
    scripts = {}
    for address in set(pointers) | set(built):
        script = read_script(memory, address, frame_count)
        if script is not None:
            scripts[address] = script
            if address in built:
                script.found.add('code')
            if address in pointers:
                script.found.add('pointer')
    # Tables: runs of pointer cells that each lead to a script.
    cells = {}
    for target, where in pointers.items():
        if target in scripts:
            for cell in where:
                cells[cell] = target
    for cell in sorted(cells):
        if cell - 4 in cells:
            continue
        run = []
        while cell + 4 * len(run) in cells:
            run.append(cells[cell + 4 * len(run)])
        if len(run) >= 2:
            for index, target in enumerate(run):
                scripts[target].tables.append((cell, index))
                scripts[target].found.add('table')
    # The banks: those loaded by the routines naming the script or its table.
    for address, script in scripts.items():
        script.users = used_by(address)
        for table, _ in script.tables:
            script.users |= used_by(table)
        script.users.discard(None)
        for routine in script.users:
            script.slots |= slots_of.get(routine, set())
    # A pointer that only follows a jump step is the script's own loop, not
    # a start of its own.
    jumps = {memory.u32(s.address + 8) for script in scripts.values() for s in script.steps
             if s.flags & JUMP and memory.inside(s.address + 8, 4)}
    for address in list(scripts):
        script = scripts[address]
        if script.found == {'pointer'} and address in jumps and len(pointers.get(address, ())) <= 1:
            del scripts[address]
    return scripts
