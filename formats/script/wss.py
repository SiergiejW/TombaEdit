"""WSS event scripts: the byte code that runs a section's scenes.

A file starts `W\\0S\\0`, its size as a word, and a table of sixty-four
sixteen-bit entry points that fills the header to byte 88; the code follows. An entry
is one more than the offset of its first instruction from the start of the
code, and zero where there is none. The game starts an entry by its place
in the table (routine 80037FBC in the European build) and keeps running
until an instruction that waits.

Instructions below 80 are the machine's own (routine 80038CD0): moves,
arithmetic, comparisons, jumps, and the one that loads arguments. Those
from 80 up are the game's (routine 8003AFB4): one byte each, taking what
the argument instruction left and putting what they find back in the same
places. An operand is a variable, numbered from 0, or a 32-bit number; the
variables from 40 on are those argument and result places, shown as r0,
r1 and so on. Jump targets are offsets from the start of the code.

The machine's instructions are named for what the decompiled routines do.
The game's are named where a routine's effect is plain and numbered where
it is not.
"""
from dataclasses import dataclass
import struct
from disc.reader import FormatError

MAGIC = b'W\x00S\x00'
TABLE = 8               # where the table of entry points starts
CODE = 0x88             # and where the code does

JUMPS = {0x08: 'JMP', 0x09: 'JEQ', 0x0A: 'JNE', 0x0B: 'JEQ', 0x0C: 'JNE', 0x0D: 'JLT', 0x0E: 'JGT',
         0x0F: 'JLE', 0x10: 'JGE'}
UNARY = {0x18: 'INC', 0x19: 'DEC', 0x1A: 'NOT', 0x1B: 'NEG'}
BINARY = ('ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'AND', 'OR', 'XOR')
GAME = {
    0x80: 'CreateObject', 0x81: 'SetObjAnim', 0x82: 'RemoveObj', 0x83: 'SetPlayerPosition',
    0x84: 'GetPlayerPosition', 0x85: 'ObjAction', 0x86: 'GetObjField6A', 0x87: 'SetObjPosition', 0x88: 'GetObjPosition',
    0x89: 'SetObjFrame', 0x8A: 'GetObjFrame', 0x8B: 'IsObjInState2', 0x8C: 'SetObjEnabled',
    0x8D: 'GetObjVisible', 0x8E: 'ReadFlag', 0x8F: 'WriteFlag', 0x90: 'GetObjField68', 0x91: 'ReadGlobal',
    0x92: 'WriteGlobal', 0x93: 'GetPlayerFlagA0', 0x94: 'SetObjShade', 0x95: 'SetObjDrawOrder',
    0x96: 'SetPlayerControl', 0x97: 'SetPlayerState', 0x98: 'GetPlayerFlagD6',
    0x99: 'SetPlayerFacing', 0x9A: 'AwardEvent', 0x9B: 'GetPlayerFlagA1', 0x9C: 'SetDialogId', 0x9D: 'ShowInfo',
    0x9E: 'PlaySound', 0x9F: 'ReleaseObjLink', 0xA0: 'SetFadeEffect', 0xA1: 'ShowInfo', 0xA2: 'GiveItem', 0xA3: 'GetObjTouchFlag',
    0xA4: 'SetObjTouchFlag', 0xA5: 'SetObjParam', 0xA6: 'SetPlayerAnim', 0xA7: 'GetAreaId',
    0xA8: 'GetPlayerFieldE2', 0xA9: 'AddVitality', 0xAA: 'GetCounter', 0xAB: 'Yield',
}
# The 1997 builds have the same instructions up to A5 and fewer after it.
TAIL = 0xA6

# What ObjAction (85) has a script object do, by its second argument
# (routine 80039E54 of the European build, scriptOpShowMessageBox in
# Tombi-Decomp). It sets the object's step; the object's routine does the
# rest. {n} are the instruction's arguments.
ACTIONS = {
    0: 'stand', 9: 'stand',
    1: 'wait {2} updates',
    2: 'walk at speed {3} for {2} updates',
    3: 'go towards ({3}, {4}) in {2} updates ({5}, {6})',
    4: 'talk: message {2}/{3}, animation {4}',
    5: 'set its speed to ({2}, {3})',
    6: 'stop',
    7: 'set its speed to ({2}, {3}), {4}',
    8: 'talk at ({5}, {6}, {7}): message {2}/{3}, animation {4}',
}


def action_note(operands, messages=None):
    """What an ObjAction does, from its arguments; None when the action is
    a variable. `messages(group, line)` gives a talk action's text."""
    try:
        action = int(operands[1])
    except (IndexError, ValueError):
        return None
    form = ACTIONS.get(action)
    if form is None:
        return f'action {action}'
    padded = list(operands) + ['?'] * 8
    note = form.format(*padded)
    if action in (4, 8) and messages is not None:
        try:
            line = messages(int(operands[2]), int(operands[3]))
        except (ValueError, IndexError):
            line = None
        if line:
            note += ': "' + ' / '.join(part for part in line.split('\n') if part)[:120] + '"'
    return note


def game_ops(tail=None):
    """Names of the game instructions of a build: those of the released
    game, or, with `tail`, the names of a build's own instructions from A6
    on (game.builds.Build.script_tail)."""
    if tail is None:
        return GAME
    ops = {op: name for op, name in GAME.items() if op < TAIL}
    ops.update({TAIL + i: name for i, name in enumerate(tail)})
    return ops


@dataclass
class Instruction:
    offset: int         # from the start of the code
    size: int
    name: str
    operands: tuple     # texts
    target: int = -1    # where a jump goes, or -1

    @property
    def text(self):
        return self.name + (' ' + ', '.join(self.operands) if self.operands else '')


def variable(number):
    return f'v{number:02X}' if number < 0x40 else f'r{number - 0x40}'


class Wss:
    def __init__(self, data, ops=None):
        """`ops` names the game instructions (game_ops); the released
        game's by default."""
        self.ops = ops or GAME
        data = bytes(data)
        if data[:4] != MAGIC or len(data) < CODE:
            raise FormatError('Not a WSS script')
        self.size = struct.unpack_from('<I', data, 4)[0]
        self.data = data
        self.code = data[CODE:]
        words = struct.unpack_from(f'<{(CODE - TABLE) // 2}H', data, TABLE)
        # entry number -> code offset
        self.entries = {i: word - 1 for i, word in enumerate(words) if 0 < word <= len(self.code)}
        self.instructions = self.disassemble()

    def decode(self, at):
        """The instruction at a code offset, or None where the bytes do not read as one."""
        code = self.code
        if at >= len(code):
            return None
        op = code[at]

        def need(count):
            if at + count > len(code):
                raise IndexError

        def imm(where):
            return struct.unpack_from('<i', code, where)[0]

        try:
            if op >= 0x80:
                return Instruction(at, 1, self.ops.get(op, f'GAME_{op:02X}'), ())
            if op == 0x01:
                return Instruction(at, 1, 'END', ())
            if op in (0x02, 0x04, 0x16):
                need(3)
                return Instruction(at, 3, {0x02: 'MOV', 0x04: 'SWAP', 0x16: 'CMP'}[op],
                                   (variable(code[at + 1]), variable(code[at + 2])))
            if op in (0x03, 0x17):
                need(6)
                return Instruction(at, 6, 'MOV' if op == 0x03 else 'CMP', (variable(code[at + 1]), str(imm(at + 2))))
            if op == 0x05:
                need(2)
                count, pos, args = code[at + 1], at + 2, []
                if count > 16:
                    return None
                for _ in range(count):
                    need(pos - at + 2)
                    if code[pos] == 0:
                        args.append(variable(code[pos + 1]))
                        pos += 2
                    else:
                        need(pos - at + 5)
                        args.append(str(imm(pos + 1)))
                        pos += 5
                return Instruction(at, pos - at, 'ARGS', tuple(args))
            if op == 0x06:
                need(2)
                return Instruction(at, 2, 'RAND', (variable(code[at + 1]),))
            if op in JUMPS:
                need(3)
                target = struct.unpack_from('<H', code, at + 1)[0]
                return Instruction(at, 3, JUMPS[op], (f'{target:04X}',), target)
            if op == 0x11:
                need(4)
                target = struct.unpack_from('<H', code, at + 2)[0]
                return Instruction(at, 4, 'LOOP', (variable(code[at + 1]), f'{target:04X}'), target)
            if op == 0x12:
                need(2)
                entry = code[at + 1]
                target = self.entries.get(entry, -1)
                return Instruction(at, 2, 'CALL', (f'entry {entry}',), target)
            if op in (0x13, 0x14, 0x15):
                return Instruction(at, 1, {0x13: 'RET', 0x14: 'PUSHVARS', 0x15: 'POPVARS'}[op], ())
            if op in UNARY:
                need(2)
                return Instruction(at, 2, UNARY[op], (variable(code[at + 1]),))
            if 0x1C <= op <= 0x2B:
                name = BINARY[(op - 0x1C) // 2]
                if op & 1:
                    need(6)
                    return Instruction(at, 6, name, (variable(code[at + 1]), str(imm(at + 2))))
                need(3)
                return Instruction(at, 3, name, (variable(code[at + 1]), variable(code[at + 2])))
            if op == 0x2C:
                need(2)
                return Instruction(at, 2, 'WAIT', (str(code[at + 1]),))
        except IndexError:
            return None
        return None

    def disassemble(self):
        """Every instruction reached from an entry, in the order of the file."""
        found, work = {}, sorted(set(self.entries.values()))
        while work:
            at = work.pop()
            while at not in found:
                ins = self.decode(at)
                if ins is None:
                    break
                found[at] = ins
                if ins.target >= 0:
                    work.append(ins.target)
                if ins.name in ('END', 'RET', 'JMP'):
                    break
                at += ins.size
        return [found[at] for at in sorted(found)]

    def listing(self, messages=None):
        """The script as text: entries, then the code with labels.
        `messages(group, line)` gives the text of a message box, to show
        with the actions that open one."""
        labels = {}
        for entry, at in sorted(self.entries.items()):
            labels.setdefault(at, []).append(f'entry {entry}')
        for ins in self.instructions:
            if ins.target >= 0 and ins.name != 'CALL':
                labels.setdefault(ins.target, []).append(f'L{ins.target:04X}')
        covered = sum(ins.size for ins in self.instructions)
        lines = [f'WSS script | {len(self.data):,} bytes | {len(self.entries)} entries | '
                 f'{len(self.instructions)} instructions, {covered:,} of {len(self.code):,} code bytes reached', '']
        lines.append('Entries: ' + (', '.join(f'{entry} at {at:04X}' for entry, at in sorted(self.entries.items())) or 'none'))
        end, held = None, None
        for ins in self.instructions:
            if end is not None and ins.offset != end:
                lines.append(f'        ; {ins.offset - end} bytes not reached' if ins.offset > end else '')
            if ins.offset in labels:
                lines.append('')
                lines.append(f'{" / ".join(dict.fromkeys(labels[ins.offset]))}:')
            raw = self.code[ins.offset:ins.offset + ins.size].hex(' ').upper()
            text = ins.text
            if held is not None:
                # The arguments loaded just before are written with the
                # instruction that takes them.
                last = lines.pop()
                if self.code[ins.offset] >= 0x80 and ins.offset not in labels and held.offset + held.size == ins.offset:
                    text = f'{ins.name}({", ".join(held.operands)})'
                    raw = self.code[held.offset:ins.offset + ins.size].hex(' ').upper()
                    lines.append(f'  {held.offset:04X}  {text:<44} ; {raw[:47]}')
                    if ins.name == 'ObjAction':
                        note = action_note(held.operands, messages)
                        if note:
                            lines.append(f'{"":8}; {note}')
                    held, end = None, ins.offset + ins.size
                    continue
                lines.append(last)
            held = ins if ins.name == 'ARGS' else None
            lines.append(f'  {ins.offset:04X}  {text:<44} ; {raw[:47]}')
            end = ins.offset + ins.size
        return '\n'.join(lines)
