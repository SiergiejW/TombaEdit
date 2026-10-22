"""Frames of a sprite bank that only other areas show.

Many banks are loaded with the same bytes by more than one area: the
effects of every area's base group, characters met in several places. An
area whose objects never show some frames says nothing about their texture
page; an area that loads the same bank may place the objects that do, or
run the routines that spawn them. The page, palette and textures are taken
from there.
"""
from formats.level.scene import (area_of, bank_copies, loaded_resources, sprite_pages, sprite_coded,
                                 sprite_cluts, sprite_owners, sprite_routines)
from psx.graphics import same_texels

# Sections searched per bank: those with a record of their own for the bank
# first, then the first section of each area whose base group has it.
# Placements are cheap to read; routines are run on a few sections only.
PLACEMENT_SECTIONS = 16
ROUTINE_SECTIONS = 3


def sections_elsewhere(project, node, data):
    """[(load table, section, slot)] of other areas' sections that have
    this bank loaded, in the order they are searched."""
    here = area_of(node.ldar)
    copies = [copy for copy in bank_copies(project, data) if area_of(copy[0]) != here]
    order = [(path, group, asset) for path, group, asset in copies if group]
    order += [(path, 1 if len(project.ldars[path]) > 1 else 0, asset) for path, group, asset in copies if not group]
    return list(dict.fromkeys((path, section, asset.slot) for path, section, asset in order
                              if loaded_resources(project, path, section).get(('SPR', asset.slot)) is asset))


def other_areas(project, node, data, frames, wanted, vram, own_pixels=()):
    """{frame: (page base, CLUT word or None, VRAM or None, origin, [names])}
    for the frames in `wanted` that another area shows. The VRAM is None
    when `vram` holds the same pixels and palettes as that area's.

    Areas can draw one bank with different art, so where several show a
    frame the one whose page holds the same pixels here wins, and after
    that the one that shows the most of the bank. Frames in `own_pixels`
    take only such a page, never another area's textures. Routines are
    only run for frames no placed object shows."""
    wanted, own_pixels = set(wanted), set(own_pixels)
    order = sections_elsewhere(project, node, data)
    vrams, offers = {}, {}
    for routines, limit in ((False, PLACEMENT_SECTIONS), (True, ROUTINE_SECTIONS)):
        for rank, (path, section, slot) in enumerate(order[:limit]):
            open_frames = wanted - set(offers) if routines else wanted
            if not open_frames:
                break
            if routines:
                traced = sprite_routines(project, path, section).get(slot, {})
                pages = {frame: page for frame, (page, _) in traced.items()}
                words = {frame: word for frame, (_, word) in traced.items() if word is not None}
                coded = ()
            else:
                pages = sprite_pages(project, path, section).get(slot, {})
                words = sprite_cluts(project, path, section).get(slot, {})
                coded = sprite_coded(project, path, section).get(slot, ())
            shown = open_frames & set(pages)
            if not shown:
                continue
            if (path, section) not in vrams:
                vrams[path, section] = project.vram(path, section)
            theirs = vrams[path, section]
            owners = sprite_owners(project, path, section).get(slot, {})
            area = f'area {area_of(path):02d}'
            for frame in shown:
                page, word = pages[frame], words.get(frame)
                same = same_texels(vram, theirs, frames[frame], page, word)
                if not same and frame in own_pixels:
                    continue
                offers.setdefault(frame, []).append((
                    (not same, -len(shown), routines, rank),
                    (page, word, None if same else theirs,
                     area + (' routine' if routines else ' code' if frame in coded else ''),
                     [f'{name} ({area})' for name in owners.get(frame, ())])))
            if all(any(not key[0] for key, _ in offers.get(frame, ())) for frame in wanted):
                break
    return {frame: min(choices, key=lambda choice: choice[0])[1] for frame, choices in offers.items()}
