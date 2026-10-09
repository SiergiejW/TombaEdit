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

    @property
    def layer(self):
        return CLASSES[self.kind][0]

    @property
    def raw(self):
        """The object as a placement record would describe it."""
        layer, kind, mode = CLASSES[self.kind]
        raw = bytearray(16)
        raw[1], raw[2], raw[3], raw[4], raw[12] = layer, kind, self.slot & 255, self.subtype & 255, mode
        return bytes(raw)


def section_scripts(project, area, section):
    """[(file name, Wss)] for the scripts a section can run."""
    out = []
    files = {Path(entry.path).name.upper(): entry for entry in project.disc.files
             if entry.path.upper().endswith('.WSS')}
    for name in SCRIPTS.get((area, section), ()):
        entry = files.get(name + '.WSS')
        if entry is None:
            continue
        try:
            out.append((Path(entry.path).name, Wss(project.disc.read(entry))))
        except FormatError:
            continue
    return out


def numbers(operands):
    """An instruction's arguments as numbers, or None where one is a variable."""
    try:
        return [int(text) for text in operands]
    except ValueError:
        return None


def script_objects(name, script):
    """The objects a script creates with fixed arguments, in the order of
    its code."""
    found, last = [], {}
    code = script.instructions
    for index, instruction in enumerate(code[:-1]):
        if instruction.name != 'ARGS':
            continue
        call, values = code[index + 1], numbers(instruction.operands)
        if values is None or call.offset != instruction.offset + instruction.size:
            continue
        if call.name == 'CreateObject' and len(values) >= 6 and values[1] in CLASSES:
            slot, kind, subtype, x, y, z = values[:6]
            if all(-32768 <= v <= 32767 for v in (x, y, z)):
                created = ScriptObject(name, instruction.offset, slot, kind, subtype, (x, y, z))
                found.append(created)
                last[slot] = [created, False]
        elif call.name == 'SetObjAnim' and len(values) >= 3 and values[0] in last and not last[values[0]][1]:
            # The first animation given to an object after it is made.
            last[values[0]][0].animation, last[values[0]][0].frame = values[1], values[2]
            last[values[0]][1] = True
    return found
