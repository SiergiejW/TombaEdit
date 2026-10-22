"""Town drawing settings decoded from the INFO overlays.

The village's scenery and NPCs share SPR slot 11, but use different page
bases. The cutaway houses are scenery sprites, not separate LDAR sections.

The tables are found by their content, so a build that moves them is read
the same way; addresses in the comments are the US retail ones. Every value
is checked against the bank it describes before it is used.
"""
from dataclasses import dataclass, field
import struct
from game.builds import executable


@dataclass
class TownGraphics:
    pages: dict = field(default_factory=dict)
    cluts: dict = field(default_factory=dict)
    houses: list = field(default_factory=list)
    bank: int = 11
    name: str = 'Dwarf Village'
    animations: dict = field(default_factory=dict)


def town_graphics(project, resources, area, section):
    """Cutaway artwork in the current town's loaded bank.

    Only the sections known to have rooms are interpreted. Baccus Pier also
    uses INFO2, but its bank 13 contains fences, not the village's house
    frames. Loading a common overlay or an NPC bank does not imply rooms exist.
    """
    if (area, section) in ((2, 0), (19, 0)):
        return dwarf_graphics(project, resources, area, section)
    if not ((area == 5 and section in (0, 2)) or (area == 19 and section == 2)):
        return None
    if ('SPR', 13) not in resources or ('INS', 0) not in resources:
        return None
    found = executable(project, resources['INS', 0].ldar)
    if found is None or found.build.early:
        return None
    data = project.asset_data(resources['INS', 0])
    from psx.graphics import sprite_frames
    frames = sprite_frames(project.asset_data(resources['SPR', 13]))
    baccus = area == 5
    count = 12 if baccus else 11
    if len(frames) != (12 if baccus else 23):
        return None
    base = found.build.overlay

    def unpack(fmt, address):
        if not base <= address <= base + len(data) - struct.calcsize(fmt):
            raise IndexError('Town table pointer outside INFO2 overlay')
        return struct.unpack_from(fmt, data, address - base)

    def house_scripts(table):
        """The script list of an object record that shows one frame of bank
        13 per script, in order, each held for 60 ticks: the houses."""
        page, _, bank, _, animation = unpack('<4HI', table)
        if (page, bank) != (2, 13):
            return None
        for index in range(count):
            frame, _, _, control = unpack('<4H', unpack('<I', animation + index * 4)[0])
            if frame != index or control != 0x803C:
                return None
        return animation

    # Baccus Village's record is at 800FDDC4 and Hidden Village's at
    # 800FDE34. Both hold frames 0 up, so the one with a script per frame
    # of the loaded bank and no more is the section's.
    table = scripts = None
    for at in range(0, len(data) - 12, 4):
        if data[at:at + 2] != b'\x02\0' or data[at + 4:at + 6] != b'\x0d\0':
            continue
        try:
            found_scripts = house_scripts(base + at)
        except (struct.error, IndexError):
            continue
        if found_scripts is None:
            continue
        try:
            extra = unpack('<4H', unpack('<I', found_scripts + count * 4)[0])
            if extra[0] == count and extra[3] == 0x803C:
                continue            # a longer list: the other village's record
        except (struct.error, IndexError):
            pass
        table, scripts = base + at, found_scripts
        break
    if table is None:
        return None

    try:
        page, _, bank, _, animation = unpack('<4HI', table)
        profile = TownGraphics(bank=bank, name='Baccus Village' if baccus else 'Hidden Village')
        for index in range(count):
            script = unpack('<I', scripts + index * 4)[0]
            profile.animations[script] = [f'{profile.name} scenery {index:02d}']
            frame, _, _, control = unpack('<4H', script)
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


def character_pages(data, base, slot, count):
    """{frame: texture page base} for a bank of town characters, read from
    the overlay that spawns them, or {} if it does not say.

    A town's characters are not placed by APD records. The overlay keeps a
    run of twelve-byte records for them, one per character: four size
    bytes, a page base, the SPR slot and a pointer to a list of animation
    scripts (800FDD80 for Baccus Village). A bank holds several characters
    whose art sits on different pages, so each record's scripts say which
    frames go with its page.

    One overlay serves several towns, each with a bank of its own in the
    same slot. The run that belongs to this bank is the one whose frames
    reach exactly its last frame and never give one frame two pages, or
    failing that the one that reaches furthest; a run that gives only one
    page is not taken. Frames no script shows take the page of the
    character before them."""
    data = bytes(data)
    end = base + len(data)
    tails = []
    for at in range(4, len(data) - 8, 4):
        page, bank, table = struct.unpack_from('<HHI', data, at)
        if page < 32 and bank < 16 and base <= table < end - 4 and table % 4 == 0:
            tails.append((at, page, bank, table))
    starts = sorted({tail[3] for tail in tails})
    runs, last = [], None
    for at, page, bank, table in tails:
        if bank != slot:
            continue
        # A list ends where the next record's begins, or at the first entry
        # that is not a script of this bank.
        frames, stop = set(), next((start for start in starts if start > table), end)
        for entry in range(table, stop, 4):
            script, seen, steps = struct.unpack_from('<I', data, entry - base)[0], set(), []
            while script not in seen and len(seen) < 64 and base <= script <= end - 12 and script % 4 == 0:
                seen.add(script)
                frame, _, _, control = struct.unpack_from('<4H', data, script - base)
                if frame >= count:
                    steps = []
                    break
                steps.append(frame)
                mode = control & 0xC000
                if mode == 0x8000:
                    break
                script = struct.unpack_from('<I', data, script + 8 - base)[0] if mode else script + 8
            if not steps:
                break
            frames.update(steps)
        if not frames:
            continue
        if last is None or at - last > 0x40:
            runs.append([])
        runs[-1].append((page, frames))
        last = at
    fits = []
    for run in runs:
        pages, clash = {}, False
        for page, frames in run:
            for frame in frames:
                clash = clash or pages.setdefault(frame, page) != page
        if not clash and len(set(pages.values())) > 1:
            fits.append(pages)
    # Failing a run that reaches the last frame, the one that reaches
    # furthest: the last frames can be ones no script shows. A run of
    # another town's larger bank names frames past this one's and is not
    # among them.
    ending = [pages for pages in fits if max(pages) == count - 1]
    pages = ending[0] if ending else max(fits, key=max, default=None)
    if pages is None:
        return {}
    current = pages[min(pages)]
    for frame in range(count):
        current = pages.setdefault(frame, current)
    return pages


def dwarf_graphics(project, resources, area, section):
    """Return verified frame settings, or None for a different load context.

    INFO routines 800E7780 and 800E9EB8 use the scenery table at 800EDAB8
    and always supply the object's CLUT. NPC initializer 800EC9CC instead
    reads its page base from 800EDB28. Animation word +2 selects the scenery
    style. The ordinary world-sprite CLUT flag is not used by this renderer.
    """
    if area not in (2, 19) or section != 0 or ('SPR', 11) not in resources or ('INS', 0) not in resources:
        return None
    found = executable(project, resources['INS', 0].ldar)
    if found is None:
        return None
    data = project.asset_data(resources['INS', 0])
    base = found.build.overlay
    # The scenery table opens with the style every house uses: page 2, CLUT
    # 7FC8, bank 11. The NPC record follows 0x74 bytes on (800EDB2C).
    at = bytes(data).find(struct.pack('<3H', 2, 0x7FC8, 11))
    if at < 0 or at % 4:
        return None
    scenery = base + at

    def unpack(fmt, address):
        if not base <= address <= base + len(data) - struct.calcsize(fmt):
            raise IndexError('Town table pointer outside INFO overlay')
        return struct.unpack_from(fmt, data, address - base)

    try:
        styles = [unpack('<4HI', scenery + n * 12) for n in range(3)]
        npc_page, npc_bank = unpack('<HH', scenery + 0x74)
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
        npc_scripts = unpack('<I', scenery + 0x78)[0]
        for n in range(216):
            script = unpack('<I', npc_scripts + n * 4)[0]
            profile.animations[script] = [f'Town character animation {n:03d}']
            for frame, _ in steps(script):
                profile.pages[frame] = npc_page
        for n in range(24):
            script = unpack('<I', styles[0][4] + n * 4)[0]
            profile.animations[script] = [f'Town scenery animation {n:03d}']
            for frame, style in steps(script):
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


def shared_bank_preview(project, asset, context, frames):
    """Resolve identical town banks using the context that actually draws them."""
    from formats.level.scene import loaded_resources, area_of
    from formats.archive.ldar import table_name
    from game.labels import content_key
    data = bytes(project.asset_data(asset))
    language = table_name(asset.ldar)[0]
    candidates = [(asset.ldar, context)]
    candidates += [(path, g.index) for path, groups in project.ldars.items()
                   if table_name(path)[0] == language and area_of(path) in (2, 5, 19)
                   for g in groups[1:] if g.index in (1, 3)]
    for path, group in dict.fromkeys(candidates):
        resources = loaded_resources(project, path, group)
        match = resources.get(('SPR', asset.slot))
        if match is None or bytes(project.asset_data(match)) != data:
            continue
        profile = town_graphics(project, resources, area_of(path), group - 1)
        if profile is None or profile.bank != asset.slot or not profile.pages:
            continue
        found = executable(project, path)
        code = project.asset_data(resources['INS', 0])
        vram = project.vram(path, group)
        # What the section's objects are placed showing comes first; the
        # houses' record fills in the frames nothing places.
        from formats.level.scene import sprite_pages, sprite_cluts
        placed = sprite_pages(project, path, group).get(asset.slot, {})
        placed_cluts = sprite_cluts(project, path, group).get(asset.slot, {})
        pages = {**profile.pages, **placed}
        cluts = {frame: word for frame, word in profile.cluts.items() if frame not in placed}
        cluts.update({frame: word for frame, word in placed_cluts.items() if frame in placed})
        origins = {frame: f'{path} group {group}: town code' for frame in profile.pages if frame not in placed}
        from collections import Counter
        default = Counter(pages.values()).most_common(1)[0][0]
        return dict(sprite_pages=pages, sprite_cluts=cluts, sprite_names={},
                    sprite_origins=origins, sprite_vrams={}, sprite_default=default,
                    vram=vram, animation_users=profile.animations,
                    animation_code=[('overlay', found.build.overlay, code),
                                    ('executable', found.base, found.data[0x800:])],
                    update_rate=50 if 'European' in found.build.name else 60,
                    bank_key=content_key(data),
                    context_note=f'Artwork and animation setup from the identical bank in {path}, group {group}.')
    return None
