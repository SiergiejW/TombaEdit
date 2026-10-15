"""Follow object code stores to TObj.anim, rather than matching frame ranges.

The layout comes from TObj and AnimLoadDuration in Tombi-Decomp. A script
belongs to a bank only through its handler, or an explicitly loaded table.
Addresses are read from the current executable, so regional builds do not
borrow PAL addresses. Indexed animation arrays stop at another named table.
"""
import bisect
import struct
from formats.sprites.animations import Memory, read_script, code_constants, routines, SPR_SLOTS


class Ownership:
    def __init__(self, regions, sprite_slots=SPR_SLOTS):
        self.memory = Memory(regions)
        self.sprite_slots = sprite_slots
        self.starts, self.references = set(), set()
        self.scans = {}
        self.resolved = {}
        for _, base, data in self.memory.regions:
            self.starts.update(routines(base, data))
            self.references.update(code_constants(base, data))
        self.starts = sorted(self.starts)
        self.references = sorted(self.references)

    def scan(self, pc):
        if pc in self.scans:
            return self.scans[pc]
        k = bisect.bisect_right(self.starts, pc)
        end = min(pc + 0x1800, self.starts[k] if k < len(self.starts) else pc + 0x1800)
        # (kind, address, indexed): addresses and values loaded through them.
        regs, calls, stores, slots = {0: ('address', 0, False)}, set(), set(), set()
        for at in range(pc, end, 4):
            if not self.memory.inside(at, 4):
                break
            w = self.memory.u32(at)
            op, rs, rt, rd = w >> 26, w >> 21 & 31, w >> 16 & 31, w >> 11 & 31
            imm = (w & 0xFFFF ^ 0x8000) - 0x8000
            a, b = regs.get(rs), regs.get(rt)
            if op == 15:
                regs[rt] = ('address', (w & 0xFFFF) << 16, False)
            elif op in (8, 9, 13):
                if a and a[0] == 'address':
                    value = a[1] | (w & 0xFFFF) if op == 13 else (a[1] + imm) & 0xFFFFFFFF
                    regs[rt] = ('address', value, a[2])
                else:
                    regs.pop(rt, None)
            elif op == 0 and w & 63 in (33, 37):
                if rs == 0 or rt == 0:
                    value = b if rs == 0 else a
                    if value:
                        regs[rd] = value
                    else:
                        regs.pop(rd, None)
                elif a and b and a[0] == b[0] == 'address':
                    regs[rd] = ('address', (a[1] + b[1]) & 0xFFFFFFFF, a[2] or b[2])
                elif a and a[0] == 'address' or b and b[0] == 'address':
                    value = a if a and a[0] == 'address' else b
                    regs[rd] = ('address', value[1], True)
                else:
                    regs.pop(rd, None)
            elif op == 35:
                if a and a[0] == 'address':
                    cell = (a[1] + imm) & 0xFFFFFFFF
                    regs[rt] = ('load', cell, a[2])
                    if self.sprite_slots <= cell < self.sprite_slots + 64 and not cell & 3:
                        slots.add((cell - self.sprite_slots) // 4)
                else:
                    regs.pop(rt, None)
            elif op == 43 and imm == 0x24 and b:
                stores.add(b)
            elif op == 3:
                calls.add((at + 4) & 0xF0000000 | (w & 0x3FFFFFF) << 2)
            elif op == 2:
                target = (at + 4) & 0xF0000000 | (w & 0x3FFFFFF) << 2
                if not pc <= target < end:
                    calls.add(target)
            elif op == 0 and w & 63 not in (8, 9, 24, 25, 26, 27):
                regs.pop(rd, None)
            elif op not in (0, 1, 2, 3, 4, 5, 6, 7, 40, 41, 43):
                regs.pop(rt, None)
            regs[0] = ('address', 0, False)
        self.scans[pc] = (stores, calls, slots)
        return self.scans[pc]

    def scripts(self, pc, slot, count):
        key = (pc, slot, count)
        if key in self.resolved:
            return self.resolved[key]
        memory, result, seen, queue = self.memory, {}, set(), [(pc, 0)]
        while queue and len(seen) < 128:
            routine, depth = queue.pop()
            if routine in seen or not memory.inside(routine, 4):
                continue
            seen.add(routine)
            stores, calls, slots = self.scan(routine)
            if slots and slot not in slots:
                continue
            for kind, address, indexed in stores:
                if kind == 'address' and not indexed:
                    script = read_script(memory, address, count)
                    if script:
                        result[address] = script
                elif kind == 'load':
                    k = bisect.bisect_right(self.references, address)
                    end = min(address + (256 if indexed else 4),
                              self.references[k] if k < len(self.references) else address + 256)
                    for cell in range(address, end, 4):
                        if not memory.inside(cell, 4):
                            break
                        pointer = memory.u32(cell)
                        script = read_script(memory, pointer, count)
                        if script is None:
                            break
                        script.tables.append((address, (cell - address) // 4))
                        result[pointer] = script
            if depth < 6:
                queue.extend((call, depth + 1) for call in calls
                             if memory.region(call) == memory.region(pc))
        for script in result.values():
            script.found.add('handler')
            script.users.add(pc)
            script.slots.add(slot)
        self.resolved[key] = result
        return result
