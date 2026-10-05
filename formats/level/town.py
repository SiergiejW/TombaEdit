"""Town drawing settings decoded from the retail INFO overlays.

The village's scenery and NPCs share SPR slot 11, but use different page
bases. The cutaway houses are scenery sprites, not separate LDAR sections.
"""
from dataclasses import dataclass, field
import hashlib
import struct
from formats.level.runtime import US_SHA1


@dataclass
class TownGraphics:
    pages: dict = field(default_factory=dict)
    cluts: dict = field(default_factory=dict)
    houses: list = field(default_factory=list)
    bank: int = 11
    name: str = 'Dwarf Village'


def town_graphics(project, resources, area, section):
    """Cutaway artwork in the current town's loaded bank.

    Only verified retail contexts are interpreted. Baccus Pier also uses
    INFO2, but its bank 13 contains fences, not the village's house frames.
    Loading a common overlay or an NPC bank does not imply rooms exist.
    """
    if (area, section) in ((2, 0), (19, 0)):
        return dwarf_graphics(project, resources, area, section)
    if not ((area == 5 and section in (0, 2)) or (area == 19 and section == 2)):
        return None
    if ('SPR', 13) not in resources or ('INS', 0) not in resources:
        return None
    executable = next((e for e in project.disc.files if e.path == 'SCUS_942.36'), None)
    if executable is None or hashlib.sha1(project.disc.read(executable)).hexdigest() != US_SHA1:
        return None
    data = project.asset_data(resources['INS', 0])
    if hashlib.sha1(data).hexdigest() != '9e19f8b912ab0fd1ea4050e8a2c51e6b8e533c5b':
        return None
    from psx.graphics import sprite_frames
    frames = sprite_frames(project.asset_data(resources['SPR', 13]))
    baccus = area == 5
    table, scripts, count = ((0x800FDDC4, 0x80102004, 12) if baccus
                            else (0x800FDE34, 0x80102930, 11))
    if len(frames) != (12 if baccus else 23):
        return None
    base = 0x800E7388

    def unpack(fmt, address):
        if not base <= address <= base + len(data) - struct.calcsize(fmt):
            raise IndexError('Town table pointer outside INFO2 overlay')
        return struct.unpack_from(fmt, data, address - base)

    try:
        page, _, bank, _, animation = unpack('<4HI', table)
        if (page, bank, animation) != (2, 13, scripts):
            return None
        profile = TownGraphics(bank=bank, name='Baccus Village' if baccus else 'Hidden Village')
        for index in range(count):
            frame, _, _, control = unpack('<4H', unpack('<I', scripts + index * 4)[0])
            if frame != index or control != 0x803C:
                return None
            profile.pages[frame] = page
            # Baccus interiors use the alternate object palette (+B6 = 1).
            # Initializer 800EF658 supplies 7F48 in that state. Hidden's
            # house art uses the 7FC8 state of initializer 800F03E0.
            profile.cluts[frame] = 0x7F48 if baccus and frame >= 9 else 0x7FC8
        profile.houses = ([('Bar room', 9), ('House interior (stove)', 11)] if baccus else
                          [('House interior 1', 0), ('House interior 2', 1), ('House interior 3', 2)])
        return profile
    except (struct.error, IndexError):
        return None


def dwarf_graphics(project, resources, area, section):
    """Return verified frame settings, or None for a different load context.

    INFO routines 800E7780 and 800E9EB8 use the scenery table at 800EDAB8
    and always supply the object's CLUT. NPC initializer 800EC9CC instead
    reads its page base from 800EDB28. Animation word +2 selects the scenery
    style. The ordinary world-sprite CLUT flag is not used by this renderer.
    """
    if area not in (2, 19) or section != 0 or ('SPR', 11) not in resources or ('INS', 0) not in resources:
        return None
    executable = next((e for e in project.disc.files if e.path == 'SCUS_942.36'), None)
    if executable is None or hashlib.sha1(project.disc.read(executable)).hexdigest() != US_SHA1:
        return None
    data = project.asset_data(resources['INS', 0])
    base = 0x800E7388

    def unpack(fmt, address):
        if not base <= address <= base + len(data) - struct.calcsize(fmt):
            raise IndexError('Town table pointer outside INFO overlay')
        return struct.unpack_from(fmt, data, address - base)

    try:
        styles = [unpack('<4HI', 0x800EDAB8 + n * 12) for n in range(3)]
        # Check the overlay before interpreting absolute pointers.
        if styles[0][:3] != (2, 0x7FC8, 11):
            return None
        npc_page, npc_bank = unpack('<HH', 0x800EDB2C)
        if npc_bank != 11:
            return None
        profile = TownGraphics()

        def steps(script):
            seen = set()
            while script not in seen and len(seen) < 64:
                seen.add(script)
                frame, style, _, control = unpack('<4H', script)
                if frame >= 437:
                    raise IndexError('Town animation frame outside bank')
                yield frame, style
                mode = control & 0xC000
                if mode == 0x8000:
                    break
                script = unpack('<I', script + 8)[0] if mode in (0x4000, 0xC000) else script + 8

        # The NPC table includes frames 425 to 430 as well as 0 to 403.
        # These scripts sit between scenery scripts in memory, so contiguous
        # frame ranges or a sequential script scan would misclassify them.
        npc_scripts = unpack('<I', 0x800EDB30)[0]
        if npc_scripts != 0x800F00C0:
            return None
        for n in range(216):
            for frame, _ in steps(unpack('<I', npc_scripts + n * 4)[0]):
                profile.pages[frame] = npc_page
        for n in range(24):
            for frame, style in steps(unpack('<I', styles[0][4] + n * 4)[0]):
                if style >= len(styles):
                    return None
                page, clut, bank, _, _ = styles[style]
                if bank != 11:
                    return None
                profile.pages[frame], profile.cluts[frame] = page, clut
        if any(profile.pages.get(frame) != 2 or profile.cluts.get(frame) != 0x7FC8
               for frame in (404, 405, 406)):
            return None
        profile.houses = [('House interior 1 (fireplace)', 404),
                          ('House interior 2', 405), ('House interior 3', 406)]
        return profile
    except (struct.error, IndexError):
        return None
