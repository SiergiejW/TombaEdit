"""Possible argument values at call sites of MIPS code, over every path of the function.

A forward pass over a function's control flow (delay slots included) keeps, for
each register, the set of constants it can hold, or "unknown" with a note of what
it was last loaded from. Values merge by union; a set that grows past `LIMIT`
becomes unknown. Calls clobber the caller-saved registers. This is an upper
bound on what a register can hold, not a statement about which paths run.
"""
import struct

LIMIT = 48
CALLER_SAVED = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25)


class Value:
    """A set of possible constants, or unknown (`consts` is None) with a note."""
    __slots__ = ('consts', 'note')

    def __init__(self, consts=None, note=''):
        self.consts, self.note = consts, note

    def __eq__(self, other):
        return self.consts == other.consts and self.note == other.note

    def __repr__(self):
        return f'{sorted(self.consts)}' if self.consts is not None else f'?{self.note}'


ZERO = Value(frozenset({0}))
UNKNOWN = Value(None, '')


def const(n):
    return Value(frozenset({n & 0xFFFFFFFF}))


def join(a, b):
    if a.consts is not None and b.consts is not None:
        merged = a.consts | b.consts
        return Value(merged) if len(merged) <= LIMIT else Value(None, 'many')
    return Value(None, a.note if a.consts is None else b.note)


def signed16(n):
    return (n & 0xFFFF) - 0x10000 if n & 0x8000 else n & 0xFFFF


def apply(op, a, b):
    """The values `op` gives for every pair of constants, or unknown."""
    if a.consts is None or b.consts is None:
        if a.consts is None and b.consts is None and a.note and b.note and a.note != b.note:
            return Value(None, f'{a.note}+{b.note}')
        return Value(None, a.note or b.note)
    out = {op(x, y) & 0xFFFFFFFF for x in a.consts for y in b.consts}
    return Value(frozenset(out)) if len(out) <= LIMIT else Value(None, 'many')


def add_values(a, b):
    """a + b; a constant address plus an unknown index stays known as a table base."""
    for known, other in ((a, b), (b, a)):
        if known.consts is not None and len(known.consts) == 1 and other.consts is None:
            address = next(iter(known.consts))
            if address >= 0x10000 and not other.note.startswith('idx+'):
                return Value(None, f'idx+{address:08X}')
            if other.note.startswith('idx+'):
                return Value(None, f'idx+{(int(other.note[4:12], 16) + address) & 0xFFFFFFFF:08X}')
    return apply(lambda x, y: x + y, a, b)


def prologues(words):
    """Word indexes where a function starts: an `addiu sp, sp, -N`."""
    return [i for i, w in enumerate(words) if w >> 16 == 0x27BD and w & 0x8000]


class Function:
    def __init__(self, words, base, start, end, read_word):
        self.words, self.base, self.start, self.end = words, base, start, end
        self.read_word = read_word

    def address(self, i):
        return self.base + i * 4

    def switch_targets(self, i):
        """Targets of a `jr` through a jump table, found from the load before it, or None."""
        w = self.words[i]
        reg = w >> 21 & 31
        for j in range(i - 1, max(self.start, i - 10) - 1, -1):
            x = self.words[j]
            if x >> 26 == 35 and x >> 16 & 31 == reg:      # lw reg, off(rs)
                offset = signed16(x)
                source = x >> 21 & 31
                for k in range(j - 1, max(self.start, j - 8) - 1, -1):
                    y = self.words[k]
                    if y >> 26 == 15 and y >> 16 & 31 in (source, 1):       # lui
                        table = ((y & 0xFFFF) << 16) + offset
                        found = []
                        while len(found) < 512:
                            target = self.read_word(table + 4 * len(found))
                            if target is None or not self.address(self.start) <= target < self.address(self.end) or target & 3:
                                break
                            found.append(target)
                        return found or None
                return None
        return None

    def switches(self):
        """[(address of the jr, [case addresses])] for each jump table in the function."""
        found = []
        for i in range(self.start, self.end):
            w = self.words[i]
            if w >> 26 == 0 and w & 63 == 8 and w >> 21 & 31 != 31:
                targets = self.switch_targets(i)
                if targets:
                    found.append((self.address(i), targets))
        return found

    def calls(self, targets, at=None):
        """{call address: (a0, a1, a2, a3)} to any address in `targets`, over all paths
        from the start of the function, or from the instruction index `at`."""
        words, start, end = self.words, self.start, self.end
        entry = [UNKNOWN] * 32
        entry[0] = ZERO
        for n in range(4, 8):
            entry[n] = Value(None, f'param a{n - 4}')
        begin = start if at is None else at
        self.called = set()         # every routine the paths from `begin` call
        states = {begin: entry}
        sp = Value(None, 'stack')
        work = [begin]
        result = {}
        unreached_jr = []

        def push(index, state):
            if not start <= index < end:
                return
            old = states.get(index)
            if old is None:
                states[index] = list(state)
                work.append(index)
                return
            merged = [join(x, y) for x, y in zip(old, state)]
            if any(m != o for m, o in zip(merged, old)):
                states[index] = merged
                work.append(index)

        def step(state, w, pc):
            """Execute a straight-line instruction, returning the new register state."""
            state = list(state)
            op = w >> 26; rs = w >> 21 & 31; rt = w >> 16 & 31; rd = w >> 11 & 31; imm = w & 0xFFFF
            if op == 0:
                fn = w & 63; sh = w >> 6 & 31
                if fn == 0:   state[rd] = apply(lambda x, y: x << y, state[rt], const(sh)) if w else state[rd]
                elif fn == 2: state[rd] = apply(lambda x, y: x >> y, state[rt], const(sh))
                elif fn == 3: state[rd] = apply(lambda x, y: (x - (1 << 32) if x & 0x80000000 else x) >> y, state[rt], const(sh))
                elif fn in (33, 32): state[rd] = add_values(state[rs], state[rt])
                elif fn in (35, 34): state[rd] = apply(lambda x, y: x - y, state[rs], state[rt])
                elif fn == 37: state[rd] = apply(lambda x, y: x | y, state[rs], state[rt])
                elif fn == 36: state[rd] = apply(lambda x, y: x & y, state[rs], state[rt])
                elif fn in (16, 18): state[rd] = Value(None, 'hi/lo')
                elif fn in (42, 43): state[rd] = Value(frozenset({0, 1}))
                elif fn in (24, 25, 26, 27): pass
                elif fn in (8, 9, 12, 13): pass
                else: state[rd] = Value(None, f'special{fn}')
            elif op in (8, 9):  state[rt] = add_values(state[rs], const(signed16(imm)))
            elif op == 10 or op == 11: state[rt] = Value(frozenset({0, 1}))
            elif op == 12: state[rt] = apply(lambda x, y: x & y, state[rs], const(imm))
            elif op == 13: state[rt] = apply(lambda x, y: x | y, state[rs], const(imm))
            elif op == 14: state[rt] = apply(lambda x, y: x ^ y, state[rs], const(imm))
            elif op == 15: state[rt] = const(imm << 16)
            elif op in (32, 33, 34, 35, 36, 37, 38):
                name = {32: 'lb', 33: 'lh', 34: 'lwl', 35: 'lw', 36: 'lbu', 37: 'lhu', 38: 'lwr'}[op]
                base = state[rs]
                note = f'{name} {signed16(imm):#x}(r{rs})'
                if base.consts is None and base.note.startswith('idx+'):
                    note = f'{name} table[{(int(base.note[4:12], 16) + signed16(imm)) & 0xFFFFFFFF:08X}]'
                if base.consts is not None and len(base.consts) == 1:
                    note = f'{name} [{(next(iter(base.consts)) + signed16(imm)) & 0xFFFFFFFF:08X}]'
                state[rt] = Value(None, note)
            elif op in (16, 17, 18, 19):
                if op == 16 and rs in (0, 2): state[rt] = Value(None, 'cop')
            # stores, others: no register result
            state[0] = ZERO
            return state

        while work:
            i = work.pop()
            state = states[i]
            w = words[i]
            op = w >> 26
            pc = self.address(i)
            is_branch = op in (4, 5, 6, 7, 20, 21, 22, 23) or (op == 1 and (w >> 16 & 31) in (0, 1, 16, 17))
            is_jump = op == 2
            is_jal = op == 3
            is_jr = op == 0 and (w & 63) in (8, 9)
            if is_branch or is_jump or is_jal or is_jr:
                slot = step(state, words[i + 1], pc + 4) if i + 1 < end else state
                if is_jal:
                    target = 0x80000000 | (w & 0x3FFFFFF) << 2
                    self.called.add(target)
                    if target in targets:
                        result[pc] = tuple(slot[4:8])
                    after = list(slot)
                    for r in CALLER_SAVED:
                        after[r] = Value(None, f'result of call {target:08X}')
                    after[2] = Value(None, f'result of call {target:08X}')
                    push(i + 2, after)
                elif is_jr and (w & 63) == 9:
                    after = list(slot)
                    for r in CALLER_SAVED:
                        after[r] = Value(None, 'result of indirect call')
                    push(i + 2, after)
                elif is_jr:
                    if w >> 21 & 31 == 31:
                        continue            # return
                    targets_jr = self.switch_targets(i)
                    if targets_jr is None:
                        unreached_jr.append(pc)
                        continue
                    for target in targets_jr:
                        push((target - self.base) // 4, slot)
                elif is_jump:
                    push(((0x80000000 | (w & 0x3FFFFFF) << 2) - self.base) // 4, slot)
                else:
                    offset = signed16(w)
                    push(i + 1 + offset, slot)
                    push(i + 2, slot)
            else:
                if i + 1 < end:
                    push(i + 1, step(state, w, pc))
        self.unresolved_jumps = unreached_jr
        return result


def analyse(words, base, targets, read_word):
    """({call address: (a0, a1, a2, a3)} for calls to `targets` in a code region,
    the addresses of indirect jumps whose targets were not found, and the
    address of the function each call is in)."""
    starts = prologues(words) + [len(words)]
    found, jumps, owner = {}, [], {}
    for k in range(len(starts) - 1):
        function = Function(words, base, starts[k], starts[k + 1], read_word)
        # Skip functions with no call to a target.
        if not any(w >> 26 == 3 and (0x80000000 | (w & 0x3FFFFFF) << 2) in targets for w in words[starts[k]:starts[k + 1]]):
            continue
        for pc, args in function.calls(targets).items():
            found[pc] = args
            owner[pc] = function.address(function.start)
        jumps += function.unresolved_jumps
    return found, jumps, owner


def region_words(data):
    return struct.unpack('<%dI' % (len(data) // 4), data[:len(data) // 4 * 4])
