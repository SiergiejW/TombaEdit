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
from psx.graphics import same_texels, part_page

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


def showing_area(project, node, data):
    """(asset, load group) of another area's section that loads this bank
    and whose objects or routines show the most of it, or None."""
    best, most = None, 0
    for rank, (path, section, slot) in enumerate(sections_elsewhere(project, node, data)):
        shown = set(sprite_pages(project, path, section).get(slot, {}))
        if rank < ROUTINE_SECTIONS:
            shown |= set(sprite_routines(project, path, section).get(slot, {}))
        if len(shown) > most:
            best, most = (loaded_resources(project, path, section)[('SPR', slot)], section), len(shown)
    return best


def texels(vram, parts, base, clut=None):
    """The pixels and palettes these parts read when drawn with page base
    `base`, as bytes."""
    out = []
    for part in parts:
        page = part_page(part, base)
        depth = page >> 7 & 3
        per_word = 4 if depth == 0 else 2 if depth == 1 else 1
        x, y = (page & 15) * 64, (page >> 4 & 1) * 256
        us, vs = (part[0], part[3], part[7], part[11]), (part[1], part[4], part[8], part[12])
        out.append(vram[y + min(vs):y + max(vs) + 1, x + min(us) // per_word:x + max(us) // per_word + 1].tobytes())
        if depth < 2:
            word = (part[2] if clut is None else clut) & 0x7FFF
            cx, cy = (word & 63) * 16, (word >> 6) & 511
            out.append(vram[cy, cx:cx + (16 if depth == 0 else 256)].tobytes())
    return b''.join(out)


def common_textures(project, node, data, frames, pages, cluts, vram):
    """{frame: (VRAM, area)} for frames of a bank most areas load whose page
    holds other pixels here than in most of those areas: this area has put
    its own art over the bank's, as area 19's scenery covers the effects of
    the base groups' bank. Such frames are drawn with the textures most
    areas have."""
    order = [(path, section) for path, section, _ in sections_elsewhere(project, node, data)]
    firsts = list(dict.fromkeys(path for path, _ in order))
    if len(firsts) < 3:
        return {}
    others = [(path, project.vram(path, next(s for p, s in order if p == path))) for path in firsts]
    found = {}
    for frame, page in pages.items():
        parts = frames[frame] if frame < len(frames) else None
        if not parts:
            continue
        mine = texels(vram, parts, page, cluts.get(frame))
        seen = {}
        for path, theirs in others:
            seen.setdefault(texels(theirs, parts, page, cluts.get(frame)), []).append((path, theirs))
        best = max(seen.values(), key=len)
        if texels(best[0][1], parts, page, cluts.get(frame)) != mine and len(best) * 2 >= len(others) \
                and len(best) > len(seen.get(mine, ())):
            found[frame] = (best[0][1], area_of(best[0][0]))
    return found


def same_sheet(project, node, data, frames, shown, wanted, pages, cluts, vram):
    """{frame: (VRAM, area)} for the frames in `wanted` (frame: page base)
    drawn with the textures of another area that loads the same sheet as
    this one: whose pixels match this area's for every frame in `shown`
    (frame: page base), the frames objects here show. A bank can lay its
    characters over several pages, of which an area loads only those of the
    characters it uses."""
    mine = {frame: texels(vram, frames[frame], page, cluts.get(frame)) for frame, page in shown.items()}
    found = {}
    if not mine:
        return found
    for path, section, slot in sections_elsewhere(project, node, data):
        open_frames = set(wanted) - set(found)
        if not open_frames:
            break
        # Only what that section's objects are placed showing, on the page
        # they show it on, is taken.
        theirs_shown = sprite_pages(project, path, section).get(slot, {})
        coded = sprite_coded(project, path, section).get(slot, ())
        # The parts of the sheet, by page word and base, its objects show.
        used = {(part[5] | part[6] << 8, page) for frame, page in theirs_shown.items()
                if frame not in coded and frame < len(frames) for part in frames[frame]}
        eligible = [frame for frame in open_frames
                    if {(part[5] | part[6] << 8, wanted[frame]) for part in frames[frame]} <= used]
        if not eligible:
            continue
        theirs = project.vram(path, section)
        if any(texels(theirs, frames[frame], shown[frame], cluts.get(frame)) != pixels
               for frame, pixels in mine.items()):
            continue
        for frame in eligible:
            if texels(theirs, frames[frame], wanted[frame], cluts.get(frame)) != texels(
                    vram, frames[frame], wanted[frame], cluts.get(frame)):
                found[frame] = (theirs, area_of(path))
    return found


def other_areas(project, node, data, frames, wanted, vram, own_pixels=(), own_pages=()):
    """{frame: (page base, CLUT word or None, VRAM or None, origin, [names])}
    for the frames in `wanted` that another area shows. The VRAM is None
    when `vram` holds the same pixels and palettes as that area's.

    Areas can draw one bank with different art, so where several show a
    frame the one whose page holds the same pixels here wins, and after
    that the one that shows the most of the bank. Frames in `own_pixels`,
    and pages whose every part lands in one of `own_pages` (texture page
    numbers 0-31), take only such a page, never another area's textures.
    Routines are only run for frames no placed object shows."""
    wanted, own_pixels, own_pages = set(wanted), set(own_pixels), set(own_pages)
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
                if not same and (frame in own_pixels or own_pages and all(
                        part_page(part, page) & 31 in own_pages for part in frames[frame])):
                    continue
                offers.setdefault(frame, []).append((
                    (not same, -len(shown), routines, rank),
                    (page, word, None if same else theirs,
                     area + (' routine' if routines else ' code' if frame in coded else ''),
                     [f'{name} ({area})' for name in owners.get(frame, ())])))
            if all(any(not key[0] for key, _ in offers.get(frame, ())) for frame in wanted):
                break
    return {frame: min(choices, key=lambda choice: choice[0])[1] for frame, choices in offers.items()}
