"""Static selector audit of the dialogue banks of the Japanese retail disc (SLPS_011.44).

Every path that can pick an entry of an area's dialogue bank (text slot 0) is
accounted for from the disc's own code and data:

* the message-window routines, followed through the helpers that pass a message
  on: argument values over every path of each function (formats.text.mips_args);
* the signpost routine, bounded by the subtypes the placement lists contain;
* the scripts' talk actions, with variable operands bounded (formats.script.text_references);
* the info-notice routine's item and event tables;
* the info actors' own fields.

An entry no path selects is Possibly unused: a static candidate, not proof about
every game state. The DSPSUB menus open only text slots 2 and 3, never this bank.

    python -m formats.text.jp_retail_study "rom/Ore! Tomba (Japan).cue" [--write-index]
"""
import collections
import hashlib
import json
import re
import struct
from pathlib import Path

from formats.archive.ldar import Project, area_number
from formats.level.apd import parse_apd
from formats.script.events import SCRIPTS
from formats.script.text_references import selectors
from formats.script.wss import Wss
from formats.text.mips_args import Value, analyse, region_words
from game.builds import executable

SHA1 = '07d577698ad31ec1a69b9d7b80a7c3f90b650888'
REVISION = 'jp-retail-selector-audit-v1'
# The message-window routine (800 2E480) and the wrappers that call it.
WINDOW = {0x8002E3B4, 0x8002E3EC, 0x8002E42C, 0x8002E454, 0x8002E480}
INFO_ROUTINE = 0x8002EDB0
# printInfoMessage's tables: fallback pair per area, item pointers (a < 60),
# the event-array pointer per area (a < 160), and the group each area's events are in.
TABLES = dict(fallback=0x800765A8, items=0x800765D0, group_base=0x80076878, area_events=0x8007688C)
SIGNPOSTS = 0x80076A1C     # 8-byte (group, line) records by subtype, for the routine at 80031688
# A signpost's line is shifted at run time for subtypes below 5 and for 6.
AREAS = range(20)


class Audit:
    def __init__(self, project):
        self.project = project
        self.found = executable(project)
        if self.found is None or hashlib.sha1(self.found.data).hexdigest() != SHA1:
            raise ValueError('Not the Japanese retail executable')
        self.regions = {}
        self.add('MAIN', self.found.base, self.found.data[0x800:], -1)
        for path, groups in project.ldars.items():
            for group in groups:
                for asset in group.assets:
                    if asset.kind == 'INS' and asset.source:
                        self.add(asset.source.path, self.found.build.overlay, project.asset_data(asset), area_number(path))
        self.exact = collections.defaultdict(lambda: collections.defaultdict(list))
        self.dynamic = collections.defaultdict(lambda: collections.defaultdict(list))
        self.open = collections.defaultdict(list)

    def add(self, name, base, data, area):
        key = hashlib.sha1(data).hexdigest()
        region = self.regions.setdefault(key, dict(source=name, base=base, data=data, areas=set(), words=region_words(data)))
        if area >= 0:
            region['areas'].add(area)

    def reader(self, region):
        found = self.found

        def read_word(address):
            if region['source'] != 'MAIN' and found.holds(address, 4) and address < found.build.overlay:
                return found.word(address)
            offset = address - region['base']
            return struct.unpack_from('<I', region['data'], offset)[0] if 0 <= offset <= len(region['data']) - 4 else None
        return read_word

    # ---- the message-window calls
    def window_sites(self):
        wrappers = {target: ((0, True), (1, True)) for target in WINDOW}
        for _ in range(6):
            targets = set(wrappers) | {INFO_ROUTINE}
            raw = {}
            for region in self.regions.values():
                found, _jumps, owner = analyse(region['words'], region['base'], targets, self.reader(region))
                for pc, args in found.items():
                    target = 0x80000000 | (region['words'][(pc - region['base']) // 4] & 0x3FFFFFF) << 2
                    raw[region['source'], pc] = dict(region=region, pc=pc, target=target, args=args,
                                                     owner=owner[pc], areas=region['areas'])
            sites = []
            for site in raw.values():
                if site['target'] == INFO_ROUTINE:
                    continue
                group_source, line_source = wrappers[site['target']]
                site['g'], site['l'] = (self.effective(site, source) for source in (group_source, line_source))
                sites.append(site)
            new = {}
            for site in sites:
                sources = tuple(self.parameter(v.note) if v.consts is None else None for v in (site['g'], site['l']))
                if any(sources) and site['owner'] not in wrappers and site['owner'] not in new \
                        and not 0x8002E3B4 <= site['owner'] < 0x8002E4C0:
                    new[site['owner']] = sources
            if not new:
                break
            wrappers.update(new)
        self.raw, self.wrappers = raw, wrappers
        # a site that forwards its own parameters belongs to its caller's accounting
        return [s for s in sites if not (s['owner'] in wrappers and any(
            self.parameter(v.note) for v in (s['g'], s['l']) if v.consts is None))]

    @staticmethod
    def parameter(note):
        match = re.search(r'param a(\d)', note or '')
        return (int(match.group(1)), re.fullmatch(r'param a\d', note) is not None) if match else None

    @staticmethod
    def effective(site, source):
        if source is None:
            return Value(None, 'wrapper')
        index, exact = source
        value = site['args'][index]
        return value if exact or value.consts is None else Value(None, 'derived in a helper')

    def scan_indirect(self):
        """Other ways to reach the window routines: a tail jump or a stored address."""
        reachable = set(self.wrappers) | {INFO_ROUTINE}
        for region in self.regions.values():
            for index, word in enumerate(region['words']):
                if word >> 26 == 2 and (0x80000000 | (word & 0x3FFFFFF) << 2) in reachable or word in reachable:
                    raise ValueError(f'Indirect reference to a message routine in {region["source"]}')

    # ---- what each family selects
    def collect(self):
        sites = self.window_sites()
        self.scan_indirect()
        apd_sign = collections.defaultdict(set)
        for path, groups in self.project.ldars.items():
            for group in groups:
                for asset in group.assets:
                    if asset.kind == 'APD' and asset.source and area_number(path) >= 0:
                        for placement in parse_apd(self.project.asset_data(asset)):
                            if placement.layer == 4 and placement.kind == 0x1A:
                                apd_sign[area_number(path)].add(placement.variant)
        for site in sites:
            G, L = site['g'].consts, site['l'].consts
            where = f"{site['region']['source']} at {site['pc']:08X}"
            for area in sorted(site['areas']) or list(AREAS):
                if G is not None and L is not None:
                    pairs = [(g, l) for g in G for l in L]
                    for pair in pairs:
                        (self.exact if len(pairs) == 1 else self.dynamic)[area][pair].append(where)
                elif G is not None:
                    for g in G:
                        self.dynamic[area][('group', g)].append(f'{where}: the line is computed at run time')
                elif re.match(r'lhu? table\[', site['g'].note):
                    self.table_site(site, area, where, apd_sign)
                # else: supplied by a script or an info actor, bounded below
        self.scripts()
        self.actors()
        self.notices()

    def table_site(self, site, area, where, apd_sign):
        note = site['g'].note
        base = int(re.search(r'table\[(\w+)\]', note).group(1), 16)
        read = self.reader(site['region'])
        if base == SIGNPOSTS:
            for subtype in sorted(apd_sign.get(area, ())):
                g, l, _z0, _z1 = struct.unpack('<4h', struct.pack('<2I', read(base + 8 * subtype), read(base + 8 * subtype + 4)))
                if subtype < 5 or subtype == 6:
                    self.dynamic[area][('group', g)].append(f'{where}: sign subtype {subtype} -> ({g}, {l}), line shifted at run time')
                else:
                    self.exact[area][(g, l)].append(f'{where}: sign subtype {subtype} -> ({g}, {l})')
            return
        for k in range(64):
            w0, w1 = read(base + 8 * k), read(base + 8 * k + 4)
            if w0 is None or w1 is None:
                break
            g, l, z0, z1 = struct.unpack('<4h', struct.pack('<2I', w0, w1))
            if not (0 <= g < 64 and 0 <= l < 512 and z0 == 0 and z1 == 0):
                break
            self.dynamic[area][('group', g)].append(f'{where}: sign table record {k} ({g}, {l})')

    def scripts(self):
        for item in self.project.disc.files:
            if not item.path.upper().endswith('.WSS'):
                continue
            script = Wss(self.project.payload(item))
            stem = Path(item.path).stem.upper()
            areas = sorted({a for (a, _section), names in SCRIPTS.items() if stem in names}) or list(AREAS)
            for kind, options in (('talk', {}), ('actor', dict(actions=(3,), base_arg=5, line_arg=6))):
                for selection in selectors(script, **options):
                    if not selection['bounded']:
                        for area in areas:
                            self.open[area].append(f'{item.path} +{selection["offset"]:X}: a {kind} selector has unbounded operands')
                        continue
                    multiple = len(selection['bases']) * len(selection['lines']) > 1
                    for g in selection['bases']:
                        for l in selection['lines']:
                            for area in areas:
                                (self.dynamic if kind == 'actor' or multiple else self.exact)[area][(g, l)].append(
                                    f'{item.path} +{selection["offset"]:X} ({kind} action)')

    def actors(self):
        # The info actors start with their group and line both set from one global byte.
        for region in self.regions.values():
            if region['source'].startswith('SYSTEM/INFO'):
                for area in sorted(region['areas']) or list(AREAS):
                    for v in range(256):
                        self.dynamic[area][(v, v)].append(f'{region["source"]}: info actor fields start from a global byte')

    def memory(self, address, area, size):
        found = self.found
        if found.holds(address, size) and address < found.build.overlay:
            return found.data[address - found.base + 0x800:address - found.base + 0x800 + size]
        for region in self.regions.values():
            if area in region['areas'] and region['source'].upper().startswith('SYSTEM/X'):
                offset = address - region['base']
                if 0 <= offset and offset + size <= len(region['data']):
                    return region['data'][offset:offset + size]
        return None

    def notices(self):
        for area in AREAS:
            fallback = self.memory(TABLES['fallback'] + area * 2, area, 2)
            for item in range(60):
                pointer = struct.unpack('<I', self.memory(TABLES['items'] + 4 * item, area, 4))[0]
                pair = self.memory(pointer + area * 2, area, 2)
                if pair is None:
                    self.open[area].append(f'item notice {item}: its pointer {pointer:08X} is not readable')
                    continue
                g, l = pair if pair[0] != 0xFF else fallback
                self.exact[area][(g, l)].append(f'item notice {item}: table {TABLES["items"] + 4 * item:08X}')
            group = self.memory(TABLES['group_base'] + area, area, 1)[0]
            pointer = struct.unpack('<I', self.memory(TABLES['area_events'] + 4 * area, area, 4))[0]
            table = self.memory(pointer, area, 160)
            if table is None:
                self.open[area].append(f'event notices: the area table {pointer:08X} is not readable')
                continue
            for a, c in enumerate(table):
                pair = (('base', group), c) if c != 0xFF else tuple(fallback)
                self.exact[area][pair].append(f'event notice {a}: area table {pointer:08X}')

    # ---- per bank
    def statuses(self, bank_assets, wfm):
        areas = sorted({area_number(a.ldar) for a in bank_assets if area_number(a.ldar) >= 0})
        groups, n = wfm.groups, len(wfm.dialogues)

        def index(g, l):
            base = g[1] if isinstance(g, tuple) else g
            i = (groups[base] if base < len(groups) else 0) + l
            return i if 0 <= i < n else None

        def extent(g):
            base = groups[g] if g < len(groups) else 0
            return range(base, min([x for x in groups if x > base] + [n]))
        referenced, dynamic = collections.defaultdict(list), collections.defaultdict(list)
        for area in areas:
            for (g, l), why in self.exact.get(area, {}).items():
                if (i := index(g, l)) is not None:
                    referenced[i] += why[:2]
            for key, why in self.dynamic.get(area, {}).items():
                if key[0] == 'group':
                    for i in extent(key[1]):
                        dynamic[i] += why[:2]
                elif (i := index(*key)) is not None:
                    dynamic[i] += why[:2]
        complete = not any(self.open.get(area) for area in areas)
        text = {}
        for i in range(n):
            if i in referenced:
                text[str(i)] = dict(status='referenced', method='jp-retail-selector-audit', evidence=referenced[i][:3]
                    + ['Static display reference only; its trigger reachability is not established.'])
            elif i in dynamic:
                text[str(i)] = dict(status='dynamic', method='jp-retail-selector-audit', evidence=dynamic[i][:3]
                    + ['A possible selection: a conservative bound, not proof that this entry is shown.'])
            elif complete:
                text[str(i)] = dict(status='not_found', method=REVISION, evidence=[
                    'Possibly unused: no path of the audited code, scripts or tables selects this entry.',
                    'Checked: every message-window call and its helpers, the signposts the area places, the scripts\' talk actions, '
                    'the item and event notice tables and the info actors.',
                    'A static candidate, not proof about every game state. Glyph recognition and translation are not used to decide this.'])
        return text, complete


def study(project, record):
    """The profile record with every slot-0 bank of the area load tables classified."""
    audit = Audit(project)
    audit.collect()
    result = json.loads(json.dumps(record))
    apd = {}
    for groups in project.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind == 'APD' and asset.source:
                    apd[f'{asset.source.path}@{asset.offset:X}'] = hashlib.sha1(project.asset_data(asset)).hexdigest()
    from formats.text.wfm import Wfm
    for key, bank in result['banks'].items():
        source, offset = key.rsplit('@', 1)
        assets = [a for a in project.by_source.get(source, ()) if a.kind == 'WFM' and a.offset == int(offset, 16)]
        if not assets or {a.slot for a in assets} != {0}:
            continue
        wfm = Wfm(project.asset_data(assets[0]))
        text, complete = audit.statuses(assets, wfm)
        bank['text'] = text
        bank['coverage_complete'] = complete
        bank['computed_calls'] = 0
        bank['coverage'] = ('Static selector audit of the message-window calls, signposts, scripts, item and event notice tables '
                            'and info actors for this exact Japanese retail build. Dynamic bounds are conservative. '
                            'Possibly unused does not prove game-state unreachability.' if complete else
                            'Selector audit with open items: ' + '; '.join(sorted({r for a in {area_number(x.ldar) for x in assets}
                                                                                for r in audit.open.get(a, ())})[:3]))
    result['audit_revision'] = REVISION
    result['apd_sha1'] = apd
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--write-index', action='store_true')
    args = parser.parse_args()
    path = Path(__file__).with_name('native_text_usage.json')
    document = json.loads(path.read_text(encoding='utf8'))
    project = Project(args.image)
    result = study(project, document['builds'][SHA1])
    totals = collections.Counter(item['status'] for bank in result['banks'].values() for item in bank['text'].values())
    print(dict(totals))
    if args.write_index:
        document['builds'][SHA1] = result
        path.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
