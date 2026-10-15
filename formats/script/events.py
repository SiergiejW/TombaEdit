"""What a section's event script puts into the level.

Only three areas have scripts, and the game picks one by area and section
(routine 80039338 of the European build): it loads a group of area 15's
load table, whose one resource is the script, and starts entry 0. The
groups follow the disc's file links, so a script is found here by name.

A script makes its own objects. `CreateObject` takes a slot to remember the
object by, a class, a subtype and a position (routine 800399C4). The class
picks the kind of object and how it is drawn; the subtype picks its sprite
bank, texture page and list of animations from a table in the area overlay;
`SetObjAnim` then picks the animation and the frame it starts on. These are
the people and props of a scene that no placement list holds.
"""
import struct
from dataclasses import dataclass
from pathlib import Path
from disc.reader import FormatError
from formats.script.wss import Wss

# (area, section) -> names of the scripts it can run; the second of two is
# the one used once an event has changed the section.
SCRIPTS = {
    (0, 0): ('0000',), (0, 1): ('0000',), (0, 2): ('0000',),
    (1, 0): ('SCR0100',), (1, 1): ('SCR0100',), (1, 2): ('0120',), (1, 3): ('0130',), (1, 4): ('0140',),
    (2, 0): ('0200', '0201'), (2, 1): ('0210',), (2, 2): ('0220',),
    (19, 0): ('0200', '0201'), (19, 1): ('0210',),
}
SCRIPTS.update({(7, section): names for (area, section), names in list(SCRIPTS.items()) if area == 1})

# CreateObject's class -> (object layer, type, draw mode). Classes 5 to 8
# create nothing.
CLASSES = {2: (2, 0x18, 2), 3: (3, 0x2E, 0x10), 4: (4, 0x1E, 2), 9: (2, 0x19, 0x0D), 10: (2, 0x18, 0x10)}


@dataclass
class ScriptObject:
    script: str         # the script's file name
    offset: int         # of the instruction that creates it, in the script's code
    slot: int           # the number the script knows it by
    kind: int           # CreateObject's class
    subtype: int
    position: tuple
    animation: int = 0  # from the first SetObjAnim for the slot, if the script has one
    frame: int = 0
    # Per axis, True where the script places the object relative to Tomba:
    # the position is then an offset from where he stands.
    from_player: tuple = (False, False, False)

    @property
    def layer(self):
        return CLASSES[self.kind][0]

    @property
    def extra(self):
        """Object fields CreateObject and the first SetObjAnim set beyond the
        record's: the shade +6B (80, or 1 for class 4) and the animation
        number and first frame at +74 and +76."""
        return ((0x6B, bytes((1 if self.kind == 4 else 0x80,))),
                (0x74, struct.pack('<hh', self.animation, self.frame)))

    @property
    def raw(self):
        """The object as a placement record would describe it."""
        layer, kind, mode = CLASSES[self.kind]
        raw = bytearray(16)
        raw[1], raw[2], raw[3], raw[4], raw[12] = layer, kind, self.slot & 255, self.subtype & 255, mode
        return bytes(raw)


def section_scripts(project, area, section):
    """[(file name, Wss)] for the scripts a section can run."""
    from game.builds import executable
    from formats.script.wss import game_ops
    found = executable(project)
    ops = game_ops(found.build.script_tail if found else None)
    out = []
    files = {Path(entry.path).name.upper(): entry for entry in project.disc.files
             if entry.path.upper().endswith('.WSS')}
    for name in SCRIPTS.get((area, section), ()):
        entry = files.get(name + '.WSS')
        if entry is None:
            continue
        try:
            out.append((Path(entry.path).name, Wss(project.disc.read(entry), ops)))
        except FormatError:
            continue
    return out


def numbers(operands):
    """An instruction's arguments as numbers, or None where one is a variable."""
    try:
        return [int(text) for text in operands]
    except ValueError:
        return None


PLAYER = 'player'


def script_objects(name, script):
    """The objects a script creates, in the order of its code.

    Arguments are numbers or variables. A variable is followed through the
    straight run of code before the call: set from a number, from the
    position GetPlayerPosition or GetObjPosition left in r0 to r2, and moved
    by ADD and SUB. Knowledge is dropped wherever a jump can land. A
    position taken from a script object made earlier is that object's; one
    taken from Tomba is kept as an offset from him (`from_player`). Entries
    do not run in the order of the file, so the objects a script makes with
    fixed arguments are known before the rest is read; an object that moves
    before another is placed by it is taken where it was made."""
    found, last, made = [], {}, {}
    code = script.instructions
    for index, instruction in enumerate(code[:-1]):
        values = numbers(instruction.operands) if instruction.name == 'ARGS' else None
        if values and len(values) >= 6 and code[index + 1].name == 'CreateObject':
            made.setdefault(values[0], tuple((None, v) for v in values[3:6]))
    landings = {i.target for i in code if i.target >= 0} | set(script.entries.values())
    known = {}                  # variable -> (base, value); base None or PLAYER

    def value(text):
        try:
            return None, int(text)
        except ValueError:
            return known.get(text)

    for index, instruction in enumerate(code):
        if instruction.offset in landings:
            known.clear()
        op, operands = instruction.name, instruction.operands
        if op in ('MOV', 'ADD', 'SUB') and len(operands) == 2:
            source = value(operands[1])
            if op == 'MOV':
                if source is None:
                    known.pop(operands[0], None)
                else:
                    known[operands[0]] = source
            else:
                target = known.get(operands[0])
                if target is None or source is None or source[0] is not None:
                    known.pop(operands[0], None)
                else:
                    known[operands[0]] = (target[0], target[1] + (source[1] if op == 'ADD' else -source[1]))
            continue
        if op == 'GetPlayerPosition':
            for axis in range(3):
                known[f'r{axis}'] = (PLAYER, 0)
            continue
        if op not in ('ARGS', 'MOV', 'ADD', 'SUB') and operands:
            # Anything else that names variables may change them.
            for text in operands:
                known.pop(text, None) if text in ('r0', 'r1', 'r2') else None
        if op != 'ARGS' or index + 1 >= len(code):
            continue
        call = code[index + 1]
        if call.offset != instruction.offset + instruction.size:
            continue
        values = [value(text) for text in operands]
        if call.name == 'GetObjPosition':
            slot = values[0] if values else None
            spot = made.get(slot[1]) if slot and slot[0] is None else None
            for axis in range(3):
                if spot is None:
                    known.pop(f'r{axis}', None)
                else:
                    known[f'r{axis}'] = spot[axis]
        elif call.name == 'CreateObject' and len(values) >= 6 and None not in values[:6]:
            (_, slot), (_, kind), (_, subtype) = values[:3]
            if values[0][0] is None and values[1][0] is None and values[2][0] is None and kind in CLASSES:
                axes = values[3:6]
                position = tuple(v for _, v in axes)
                if all(-32768 <= v <= 32767 for v in position):
                    created = ScriptObject(name, instruction.offset, slot, kind, subtype, position,
                                           from_player=tuple(base == PLAYER for base, _ in axes))
                    found.append(created)
                    last[slot] = [created, False]
        elif call.name == 'SetObjAnim' and len(values) >= 3 and None not in values[:3] \
                and all(base is None for base, _ in values[:3]):
            slot = values[0][1]
            if slot in last and not last[slot][1]:
                # The first animation given to an object after it is made.
                last[slot][0].animation, last[slot][0].frame = values[1][1], values[2][1]
                last[slot][1] = True
    return found
