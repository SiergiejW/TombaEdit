"""The cut top-down villages, read from the INFO2 overlay.

Three villages of the Land of Civilization exist only as data: the Wood People's
village (AREA11), Stonetown (AREA16) and Iron Town (AREA17) each have a section 0
whose load list is empty and which no exit leads into. What survives is in the
INFO2 overlay: a list of residents and a list of props for each village, and a
list of house rectangles for those that have houses. The same bytes are in the
European and the Japanese disc, so they are found by their shape and not by
address.

Residents are 28-byte records, props 16-byte ones, all 16-bit words. A list of
residents ends with the record whose last word is 255, a list of props with a record
whose first word is 255. The fields of a record are split across
the row they are written in: a record begins partway through the row that holds
the previous one's position, so a resident's position is 18 bytes into its
record and a prop's 8.
"""
import struct
from dataclasses import dataclass, field

# Set number: (area, name, residents, first resident's position, props, first prop's position).
# The count and the first position tell one list from another.
VILLAGES = {
    0x0C: (8, 'Baccus Lake', 4, (61, 478), 0, None),
    0x0D: (11, "Wood People's village", 12, (88, 240), 14, (50, 224)),
    0x0E: (16, 'Stonetown', 13, (86, 460), 7, (160, 380)),
    0x0F: (17, "Iron Men's town", 16, (7, 152), 35, (437, 122)),
    0x10: (18, 'Civilization Town', 10, (417, 544), 0, None),
    0x11: (19, 'Factory approach', 10, (0, 452), 14, (-28, 342)),
}
CUT = (0x0D, 0x0E, 0x0F, 0x10)  # the villages no section loads (0x10, AREA18's, was never finished: it has no routines)

# The exits of each village, from the rectangles in the section's step routine (topdownSectionStepC, D, E; the
# Tombi-Decomp notes give them for the PAL disc, where the overlay is the same bytes): world rectangle
# (left, top, right, bottom) with None where the rectangle is open to the edge of the map, and where it leads.
# No exit of any area leads into these sections.
EXITS = {
    0x0D: [((556, 361, None, 460), 'Civilization Town (AREA18 section 1), spawn 1'),
           ((199, None, 263, 78), 'the Factory (AREA11 section 1), spawn 0')],
    0x0E: [((None, 520, -117, 529), 'Civilization Town (AREA18 section 1), spawn 3'),
           ((107, 319, 114, 320), 'the dried wishing well (AREA11 section 2), spawn 0'),
           ((148, None, None, 73), 'the rest of Stonetown (AREA16 section 1, also cut), spawn 0')],
    0x0F: [((167, 571, 279, None), 'Civilization Town (AREA18 section 1), spawn 2'),
           ((176, None, 271, 79), 'the Iron Castle (AREA17 section 1), spawn 0')],
}
BEHAVIOURS = {0: 'stands still', 1: 'patrols up and down', 2: 'patrols left and right',
              3: 'patrols a diagonal', 4: 'patrols a diagonal'}


@dataclass
class Resident:
    index: int
    subtype: int            # which drawing: residents with the same subtype share one
    dialogue: int           # the case the village's dialogue routine switches on
    behaviour: int
    room: int               # 0 outdoors; n inside house n; 255 special
    frame: int              # the way the figure faces, 0 to 3
    animation: int
    gate: int               # when the resident appears (Stonetown: a row of its dialogue table)
    x: int
    y: int
    box: tuple              # patrol box (x0, y0, x1, y1); Stonetown's is relative to the resident

    @property
    def behaviour_name(self):
        return BEHAVIOURS.get(self.behaviour, f'behaviour {self.behaviour}')


@dataclass
class Prop:
    index: int
    subtype: int
    animation: int
    room: int
    kind: int
    x: int
    y: int


@dataclass
class Village:
    set_number: int
    area: int
    name: str
    residents: list = field(default_factory=list)
    props: list = field(default_factory=list)
    alternate_props: list = field(default_factory=list)     # Stonetown has a second list
    houses: list = field(default_factory=list)              # [(x0, y0, x1, y1)]; house n is entry n - 1

    @property
    def cut(self):
        return self.set_number in CUT


def _words(data, at, count):
    return struct.unpack_from(f'<{count}h', data, at)


def _residents(data, start):
    out = []
    while start + 28 <= len(data) and len(out) < 64:
        w = _words(data, start, 14)
        out.append(Resident(len(out), w[11], w[7], w[8], w[0], w[1], w[2], w[12], w[9], w[10], (w[3], w[4], w[5], w[6])))
        if w[13] == 255:            # the last resident carries the end flag
            break
        start += 28
    return out


def _props(data, start):
    out = []
    while start + 16 <= len(data) and len(out) < 64:
        w = _words(data, start, 8)
        if w[0] == 255:
            break
        out.append(Prop(len(out), w[6], w[3], w[1], w[0], w[4], w[5]))
        start += 16
    return out


def _find_all(data, point, offset):
    """Offsets of every record whose (x, y) at `offset` is `point`, as the offset of its start."""
    needle = struct.pack('<hh', *point)
    at = data.find(needle)
    while at >= 0:
        if at - offset >= 0:
            yield at - offset
        at = data.find(needle, at + 1)


def _rectangles(data, at):
    """The rectangles of the list at `at`: [(x0, y0, x1, y1)] up to a word of 255, or None."""
    rects = []
    while at + 8 <= len(data) and len(rects) < 8:
        x0, y0, x1, y1 = _words(data, at, 4)
        if x0 == 255:
            return rects if 2 <= len(rects) <= 6 and _words(data, at, 4) == (255, 0, 0, 0) else None
        if not (-400 <= x0 < x1 <= 1000 and -100 <= y0 < y1 <= 800):
            return None
        rects.append((x0, y0, x1, y1))
        at += 8
    return None


def house_lists(data, base):
    """The rectangle lists a table of pointers names: [[(x0, y0, x1, y1), ...], ...]."""
    for at in range(0, len(data) - 20, 4):
        lists = []
        for k in range(5):
            pointer = struct.unpack_from('<I', data, at + 4 * k)[0]
            rects = _rectangles(data, pointer - base) if base <= pointer < base + len(data) else None
            if rects is None:
                break
            lists.append(rects)
        else:
            return lists
    return []


def _fits(rects, props):
    """True when every prop that says it is in house n stands in that house's rectangle."""
    rooms = {p.room for p in props if p.room}
    if not rooms or max(rooms) != len(rects):
        return False
    return all(rects[p.room - 1][0] <= p.x <= rects[p.room - 1][2] and rects[p.room - 1][1] <= p.y <= rects[p.room - 1][3]
               for p in props if p.room)


def villages(overlay, base):
    """{set number: Village} for each village whose lists are in this INFO2 overlay, whose
    first byte is at address `base`."""
    data = bytes(overlay)
    found = {}
    for number, (area, name, count, first, prop_count, prop_first) in VILLAGES.items():
        village = None
        for start in _find_all(data, first, 18):
            residents = _residents(data, start)
            if len(residents) == count:
                village = Village(number, area, name, residents)
                break
        if village is None:
            continue
        if prop_count:
            lists = [props for start in _find_all(data, prop_first, 8)
                     if len(props := _props(data, start)) == prop_count]
            if lists:
                village.props = lists[0]
                village.alternate_props = lists[1] if len(lists) > 1 else []
        found[number] = village
    lists = house_lists(data, base)
    for village in found.values():
        village.houses = next((rects for rects in lists if _fits(rects, village.props)), [])
    return found


# A village's dialogue routine reads the resident's case from the actor (offset 0xBA), switches on it
# through a jump table and opens a message from each case. The size of the table tells the routines apart.
CASE_FIELD = 0xBA
HANDLER_CASES = {0x0D: 23, 0x0E: 11, 0x0F: 16}
# The routines that open a message window, by build: showMessageBox, its timed form, the direct form
# the dialogue routines call, and the window itself.
WINDOWS = {'Japanese retail': {0x8002E3B4, 0x8002E3EC, 0x8002E42C, 0x8002E454, 0x8002E480}}


def dialogue_routines(overlay, base, read_word, window):
    """{set number: (address of the routine, {case: [(group, line), ...]})}: the messages each case of a
    village's dialogue routine can open, by the story stage that picks one. `window` is the addresses of
    the routines that open a message window, `read_word(address)` reads memory outside the overlay. A case
    that opens nothing has no pairs."""
    from formats.text.mips_args import Function, prologues, region_words
    data = bytes(overlay)
    words = region_words(data)

    def read(address):
        offset = address - base
        if 0 <= offset <= len(data) - 4:
            return struct.unpack_from('<I', data, offset)[0]
        return read_word(address)
    starts = prologues(words) + [len(words)]
    by_size = {size: number for number, size in HANDLER_CASES.items()}
    # What each routine of the overlay opens itself, and which routines it calls: a case often hands
    # its message to a helper.
    own, calls = {}, {}
    for k in range(len(starts) - 1):
        helper = Function(words, base, starts[k], starts[k + 1], read)
        reached = helper.calls(set(window))
        address = helper.address(starts[k])
        own[address] = {(g, l) for args in reached.values() for g in (args[0].consts or ())
                        for l in (args[1].consts or ())}
        calls[address] = {t for t in helper.called if t in own or base <= t < base + len(data)}

    def reachable(roots, depth=3):
        seen, frontier = set(), set(roots)
        for _ in range(depth):
            frontier = {t for r in frontier if r not in seen for t in calls.get(r, ())} - seen
            seen |= frontier
        return seen
    found = {}
    for k in range(len(starts) - 1):
        first, end = starts[k], starts[k + 1]
        if not any(w >> 26 == 37 and w & 0xFFFF == CASE_FIELD for w in words[first:min(end, first + 24)]):
            continue
        function = Function(words, base, first, end, read)
        tables = function.switches()
        if not tables or len(tables[0][1]) not in by_size:
            continue
        cases = {}
        for case, target in enumerate(tables[0][1]):
            reached = function.calls(set(window), at=(target - base) // 4)
            pairs = {(g, l) for args in reached.values() for g in (args[0].consts or ())
                     for l in (args[1].consts or ())}
            for helper in reachable(function.called):
                pairs |= own.get(helper, set())
            cases[case] = sorted(pairs)
        found[by_size[len(tables[0][1])]] = (function.address(first), cases)
    return found


def dialogue_cases(overlay, base, read_word, window):
    """{set number: {case: [(group, line), ...]}}; see dialogue_routines."""
    return {number: cases for number, (_address, cases) in dialogue_routines(overlay, base, read_word, window).items()}
