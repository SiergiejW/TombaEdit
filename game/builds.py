"""Where each known executable keeps what the level code reads.

Every build of the game shares one engine: an object is created from an APD
record and handed to a routine picked from a table by its layer and kind.
The routines and tables sit at different addresses in each executable, and
the area overlays load at a different address after it. A `Build` lists
those addresses for one executable, identified by its SHA-1.

The scratchpad layout (1F800000 to 1F8003FF) is the same in all of them and
is not repeated here.
"""
from dataclasses import dataclass, replace
import hashlib
from game.areas import language_name
import struct


@dataclass(frozen=True)
class Build:
    name: str
    overlay: int            # load address of the area overlays
    area: int               # current area word; the section word follows it
    variant: tuple | None   # (variant word, flag byte) of areas that reuse another's code
    tables: dict            # APD layer -> table of object routines
    set_animation: int
    visibility: tuple       # the six "is it on screen" tests
    get_clut: int
    draw_queues: tuple      # routines that append an object to a draw list
    silent: tuple           # sound and flag queries, answered with zero
    slot_tables: int        # per area: scratchpad slots of the APD banks
    common: int             # per area: slot of the bank every section shares
    pictures: int | None    # fixed pictures of layer 7 objects in draw mode 2
    entrances: int          # per area, per section: entrance records
    origins: int            # per area, per section: collision origin
    wall_origins: int       # origins of the mansion's four outer walls
    alternate_origin: int | None
    # Deepest collision plane of a section. A stride of 0 is a table of
    # per-area pointers to bytes; otherwise the entries are stored in place,
    # `stride` bytes an area and `width` bytes a section.
    plane_limits: tuple
    pages: int | None       # object records naming a texture page per SPR slot
    early: bool = False     # a 1997 build: no area variants
    picture_record: int = 18    # bytes a rectangle of a fixed picture takes
    # Layout of a `pages` record, ending in the SPR slot and a pointer to
    # the object's scripts, with the page base first of the named fields.
    # Twelve bytes from the Japanese demo on; the sampler's are twenty,
    # with four size words in front.
    page_record: str = '<BBhI4x'
    # Rows a fixed picture is drawn below its object: the European build
    # has a taller screen and moves them down.
    picture_top: int = 0
    # Items: the table of descriptor numbers by item type, the table of
    # pointers to the descriptors, and the palettes of the items that take
    # one by variant.
    items: tuple | None = None
    # Names of the script's game instructions from A6 on, where they differ
    # from the released game's (formats.script.wss.game_ops).
    script_tail: tuple | None = None
    # Section controllers: per area, per section, a list of four-byte
    # records (type, variant, -, start now) ending in FF, and the table of
    # their routines by type (routine 8004BFE4 of the European build).
    controllers: tuple | None = None

    @property
    def event(self):
        """Event bytes read by the first area's overlay."""
        return None if self.early else self.area - 0x20


US_RETAIL = '81cbc79f0230aeb4252e058039f47ac95a777f5a'

BUILDS = {
    US_RETAIL: Build(
        name='US retail', overlay=0x800E7388, area=0x8009BCC8, variant=(0x8009EBA0, 0x8009C62B),
        tables={2: 0x800772BC, 3: 0x8007C6B0, 4: 0x8007D30C, 5: 0x8007E8A8, 7: 0x8007D57C, 8: 0x8007C68C},
        set_animation=0x800229FC,
        visibility=(0x80022E44, 0x80022C08, 0x80022D3C, 0x80022F6C, 0x80023020, 0x800230BC),
        get_clut=0x8005DE78,
        draw_queues=(0x80018BC8, 0x80018C04, 0x80018C40, 0x80018C8C, 0x80018CC8, 0x80018D04, 0x80018D40),
        silent=(0x8001FFE8, 0x80023608, 0x800236F4),
        slot_tables=0x8007F0C8, common=0x8007B294, pictures=0x8007EBEC, entrances=0x8007BF78,
        origins=0x8007E9F8, wall_origins=0x8007E9E8, alternate_origin=0x8007E9E4,
        plane_limits=(0x8007EAF4, 0, 1), pages=0x8007D6E4,
        items=(0x8007E61C, 0x8007E6E4, 0x8007E86C), controllers=(0x8007F6A4, 0x8007F6F4)),
    '3810c960ec624c19f1fb047df506ee64b65aa77a': Build(
        name='US demo', overlay=0x800DDCA0, area=0x80092640, variant=(0x80095520, 0x80092FA3),
        tables={2: 0x800705EC, 3: 0x800730B0, 4: 0x80073D00, 5: 0x800752A0, 7: 0x80073F74, 8: 0x8007308C},
        set_animation=0x8002194C,
        visibility=(0x80021D94, 0x80021B58, 0x80021C8C, 0x80021EBC, 0x80021F70, 0x8002200C),
        get_clut=0x8005762C,
        draw_queues=(0x800184F0, 0x8001852C, 0x80018568, 0x800185B4, 0x800185F0, 0x8001862C, 0x80018668),
        silent=(0x8001EF48, 0x80022558, 0x80022644),
        slot_tables=0x80075AB0, common=0x80071C94, pictures=0x800755E4, entrances=0x80072978,
        origins=0x800753F0, wall_origins=0x800753E0, alternate_origin=0x800753DC,
        plane_limits=(0x800754EC, 0, 1), pages=0x800740DC,
        items=(0x80075014, 0x800750DC, 0x80075264), controllers=(0x8007608C, 0x800760DC)),
    '1e69d1414dcca09fe360fe69337fc8e62968fda7': Build(
        name='February 1998 preview', overlay=0x800EDAA8, area=0x800A2440, variant=(0x800A5318, 0x800A2DA3),
        tables={2: 0x800758D0, 3: 0x80079B0C, 4: 0x8007A748, 5: 0x8007BCE8, 7: 0x8007A9BC, 8: 0x80079AE8},
        set_animation=0x800222FC,
        visibility=(0x80022744, 0x80022508, 0x8002263C, 0x8002286C, 0x80022920, 0x800229BC),
        get_clut=0x8005C5CC,
        draw_queues=(0x80018824, 0x80018860, 0x8001889C, 0x800188E8, 0x80018924, 0x80018960, 0x8001899C),
        silent=(0x8001F678, 0x80022F08, 0x80022FF4),
        slot_tables=0x8007C4F8, common=0x800786F0, pictures=0x8007C02C, entrances=0x800793D4,
        origins=0x8007BE38, wall_origins=0x8007BE28, alternate_origin=0x8007BE24,
        plane_limits=(0x8007BF34, 0, 1), pages=0x8007AB24,
        items=(0x8007BA5C, 0x8007BB24, 0x8007BCAC), controllers=(0x8007CAD4, 0x8007CB24)),
    '44360f12e7bd9449a7d46deb412d6a9499b6c94c': Build(
        name='Japanese demo', overlay=0x800E7698, area=0x8009A810, variant=None,
        tables={2: 0x8006A230, 3: 0x8006CE80, 4: 0x8006D504, 5: 0x8006E01C, 7: 0x8006D660, 8: 0x8006CE64},
        set_animation=0x80020554,
        visibility=(0x8002099C, 0x80020760, 0x80020894, 0x80020AC4, 0x80020B78, 0x80020C14),
        get_clut=0x80053978,
        draw_queues=(0x80017874, 0x800178B0, 0x800178EC, 0x80017928, 0x80017964, 0x800179A0, 0x800179DC),
        silent=(0x8001E3D8, 0x80021160, 0x80021204),
        slot_tables=0x8006E66C, common=0x8006C0E4, pictures=0x8006E348, entrances=0x8006C824,
        origins=0x8006E168, wall_origins=0x8006E158, alternate_origin=None,
        plane_limits=(0x8006E1A8, 16, 1), pages=0x8006D75C, early=True,
        script_tail=('SetPlayerAnim', 'Yield'), controllers=(0x8006E864, 0x8006E8A0)),
    '72988193d496a3a9402399d04291997d57b4be45': Build(
        name='Pure Pure 09 sampler', overlay=0x800ED548, area=0x800A2248, variant=None,
        tables={2: 0x8007041C, 3: 0x800725D8, 4: 0x80072D2C, 5: 0x80073850, 7: 0x80072E78, 8: 0x800725BC},
        set_animation=0x800236B4,
        visibility=(0x80023C68, 0x80023A2C, 0x80023B60, 0x80023D90, 0x80023E44, 0x80023EE0),
        get_clut=0x8005953C,
        draw_queues=(0x800198D0, 0x8001990C, 0x80019948, 0x80019984, 0x800199C0, 0x800199FC, 0x80019A38),
        silent=(0x80021568, 0x80024418, 0x800244BC),
        slot_tables=0x80073F14, common=0x80071BCC, pictures=0x80073CC4, entrances=0x80072110,
        origins=0x80073994, wall_origins=0x80073984, alternate_origin=None,
        plane_limits=(0x800739B4, 24, 2), pages=0x80072F74, early=True, picture_record=16,
        page_record='<8xHHiI', script_tail=('Yield',), controllers=(0x8007408C, 0x800740B0)),
}


# The European release has one program for each language, started by a
# small boot executable. They are one engine built nine times: the text of a
# language makes its data a little longer or shorter, and everything after
# the data, the variables and the area overlays, moves by that much. The
# program of language 5 also has 24 bytes less in the middle of its code,
# which moves the tables and one routine down.
EUROPE = Build(
    name='European', overlay=0x800E8028, area=0x8009C960, variant=(0x8009F838, 0x8009D2C3),
    tables={2: 0x80077D9C, 3: 0x80079BAC, 4: 0x80079D74, 5: 0x8007B310, 7: 0x80079FE4, 8: 0x80079B88},
    set_animation=0x8001FE6C,
    visibility=(0x800202B4, 0x80020078, 0x800201AC, 0x800203DC, 0x80020490, 0x8002052C),
    get_clut=0x8005E420,
    draw_queues=(0x80018C2C, 0x80018C68, 0x80018CA4, 0x80018CF0, 0x80018D2C, 0x80018D68, 0x80018DA4),
    silent=(0x8001E4F0, 0x80020A78, 0x80020B64),
    slot_tables=0x8007B908, common=0x80078790, pictures=0x80080258, entrances=0x80079474,
    origins=0x8007B460, wall_origins=0x8007B450, alternate_origin=0x8007B44C,
    plane_limits=(0x8007B55C, 0, 1), pages=0x8007A14C, picture_top=0x18,
    items=(0x8007B084, 0x8007B14C, 0x8007B2D4), controllers=(0x8007BEE4, 0x8007BF34))


def european(language, late, early=0):
    """The European build of one language: `late` is how far its variables
    and overlays sit from the first language's, `early` its tables."""
    e = EUROPE
    return replace(
        e, name=f'European ({language_name(language)})', overlay=e.overlay + late, area=e.area + late,
        variant=tuple(v + late for v in e.variant), tables={k: v + early for k, v in e.tables.items()},
        get_clut=e.get_clut + early, slot_tables=e.slot_tables + early, common=e.common + early,
        pictures=e.pictures + early, entrances=e.entrances + early, origins=e.origins + early,
        wall_origins=e.wall_origins + early, alternate_origin=e.alternate_origin + early,
        plane_limits=(e.plane_limits[0] + early,) + e.plane_limits[1:], pages=e.pages + early,
        items=tuple(v + early for v in e.items), controllers=tuple(v + early for v in e.controllers))


BUILDS.update({
    'bec8dc5f4116f5e497f2337eef8c523ff6dee8fc': european(0, 0),
    'c8495badb0598a81eb1da05d325ecf7a1630e5ad': european(1, 0x20),
    'a200aa54d7fd9a7313ba72b5663b475c142862e8': european(2, 0x40),
    '5bb7b780f9891a4fa12f057095efde4b50f171c5': european(3, 0x38),
    '6642d3cd2ec614a55e554aeabe8534cc79804a02': european(4, 0x40),
    '414ad24c8df853232898265bda62fcbfe708a906': european(5, 0x28, -0x18),
    '537ae3c3a6017cf90aad9dfa298920661c4d5189': european(6, 0x30),
    'b39527d5b16a1a0aa2ff94b1032c08f1cc5923c8': european(7, 0x10),
    '92511b825ea64524390c99edf43b42cf8660d794': european(8, 0x30),
})


from game.sampler_builds import SAMPLERS
BUILDS.update({digest: Build(**fields) for digest, fields in SAMPLERS.items()})


class Executable:
    """A known executable's bytes with its build description."""

    def __init__(self, data, build):
        self.data, self.build = data, build
        self.base = struct.unpack_from('<I', data, 0x18)[0]
        self.end = self.base + len(data) - 0x800

    def holds(self, address, size=1):
        return self.base <= address and address + size <= self.end

    def unpack(self, fmt, address):
        return struct.unpack_from(fmt, self.data, address - self.base + 0x800)

    def word(self, address):
        return self.unpack('<I', address)[0]


def executable(project, table=None):
    """The disc's executable if its addresses are known, else None. `table`
    is the path of the load table being read: a disc with a program for
    each language runs the one its tables belong to."""
    from formats.archive.ldar import table_name
    language = table_name(table)[0] if table else None
    cache = project.__dict__.setdefault('_executables', {})
    if language in cache:
        return cache[language]
    found = None
    try:
        entry = project.catalog.executable
        if language is not None:
            prefix = table.rsplit('SYS/', 1)[0] if table and 'SYS/' in table else ''
            entry = project.disc.entries.get(f'{prefix}EXE/MAIN{language}.EXE',
                    project.disc.entries.get(f'{prefix}MAIN{language}.EXE', entry))
        data = project.disc.read(entry)
        build = BUILDS.get(hashlib.sha1(data).hexdigest())
        if build is None:
            from game.build_signatures import SIGNATURES
            base = struct.unpack_from('<I', data, 0x18)[0]
            for digest, (addresses, signature) in SIGNATURES.items():
                chunks = [data[a - base + 0x800:a - base + 0x810] for a in addresses]
                if all(len(chunk) == 16 for chunk in chunks) and hashlib.sha256(b''.join(chunks)).hexdigest() == signature:
                    build = BUILDS[digest]
                    break
        if build is not None:
            found = Executable(data, build)
    except Exception:
        found = None
    cache[language] = found
    return found
