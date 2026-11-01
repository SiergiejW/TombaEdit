"""Verified cut-section NPC references, separate from native selector status."""
import hashlib

from game.builds import executable
from formats.level.cut_towns import (JP_INFO2_SHA1, WINDOWS, dialogue_routines,
                                     resident_dialogue_pairs, villages)

AVAILABILITY = 'confirmed_unused_cut_village'
LABEL = 'Confirmed unused — cut-village dialogue'
MAIN_SHA1 = '07d577698ad31ec1a69b9d7b80a7c3f90b650888'


def bindings(project):
    found = executable(project)
    if found is None or hashlib.sha1(found.data).hexdigest() != MAIN_SHA1:
        return {}
    from formats.level.cut_village_view import _overlay
    overlay = bytes(_overlay(project))
    digest = hashlib.sha1(overlay).hexdigest()
    if digest != JP_INFO2_SHA1:
        return {}
    cache = project.__dict__.get('_cut_village_text_bindings')
    if cache is not None:
        return cache
    routines = dialogue_routines(overlay, found.build.overlay, found.word, WINDOWS[found.build.name])
    towns = villages(overlay, found.build.overlay)
    result = {}
    for number in (0x0D, 0x0E, 0x0F):
        town = towns[number]
        path = f'SYS/LDAR{town.area:02d}.BIN'
        groups = project.ldars.get(path, ())
        if len(groups) < 2 or groups[1].assets:
            continue
        address, cases = routines[number]
        pairs = {}
        for resident in town.residents:
            for pair in resident_dialogue_pairs(overlay, found.build.overlay, number, resident, cases) or ():
                pairs.setdefault(pair, []).append(resident.index+1)
        result[town.area] = dict(name=town.name, area=town.area, section=0,
                                routine=f'{address:08X}', pairs=pairs)
    project._cut_village_text_bindings = result
    return result


def entries(project, assets, wfm):
    """Annotations only for the area's slot-0 bank and actually placed NPCs."""
    from formats.archive.ldar import area_number
    areas = {area_number(a.ldar) for a in assets if a.slot == 0}
    result = {}
    for area, town in bindings(project).items():
        if area not in areas:
            continue
        for (group, line), residents in town['pairs'].items():
            if not 0 <= group < len(wfm.groups):
                continue
            index = wfm.groups[group]+line
            if not 0 <= index < len(wfm.dialogues):
                continue
            result.setdefault(index, []).append(dict(
                area=area, section=0, town=town['name'], routine=town['routine'],
                group=group, line=line, residents=residents,
                evidence='Confirmed unused NPC path in unmodified JP retail: the section load list is empty '
                         'and normal retail exits do not enter it. The retained dialogue code still references '
                         'this entry. This classification concerns that cut-village path; identical wording '
                         'or another reference elsewhere does not become unused by association.'))
    return result
