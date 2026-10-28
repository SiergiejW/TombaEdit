"""Evidence about text selected by the native game's display paths.

Absence from a scan is a candidate, never proof that an entry is unreachable.
Profiles are build specific. Unsupported/incomplete coverage stays unknown.
"""
import struct
import hashlib
import json
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def _study_index():
    try:
        data = json.loads(Path(__file__).with_name('native_text_usage.json').read_text(encoding='utf8'))
        return data['builds'] if data.get('schema') == 1 else {}
    except (OSError, ValueError, KeyError):
        return {}


def _study_for(project):
    from game.builds import executable
    found = executable(project)
    if found is None:
        return None
    profile = _study_index().get(hashlib.sha1(found.data).hexdigest())
    if profile is None:
        return None
    if 'scripts_sha1' in profile:
        if '_text_usage_scripts_sha1' not in project.__dict__:
            project._text_usage_scripts_sha1 = {
                item.path: hashlib.sha1(project.payload(item)).hexdigest()
                for item in project.disc.files if item.path.upper().endswith('.WSS')}
        if project._text_usage_scripts_sha1 != profile['scripts_sha1']:
            return None
    if '_text_usage_code_sha1' not in project.__dict__:
        seen, digests = set(), set()
        for groups in project.ldars.values():
            for group in groups:
                for asset in group.assets:
                    if asset.kind == 'INS' and asset.source and asset.source.path not in seen:
                        seen.add(asset.source.path)
                        digests.add(hashlib.sha1(project.asset_data(asset)).hexdigest())
        project._text_usage_code_sha1 = digests
    return profile if project._text_usage_code_sha1 == set(profile['code_sha1']) else None


def _bank_study(project, profile, source, offset):
    record = profile['banks'].get(f'{source}@{offset:X}')
    if record is None:
        return None
    assets = [a for a in project.by_source.get(source, ()) if a.kind == 'WFM' and a.offset == offset]
    contexts = sorted({(a.ldar, a.slot) for a in assets})
    if not assets or contexts != [tuple(c) for c in record['contexts']]:
        return None
    raw = project.asset_data(assets[0])
    return record if hashlib.sha1(raw).hexdigest() == record['sha1'] else None


def _attach_study(wfm, project, source, offset):
    profile = _study_for(project)
    record = _bank_study(project, profile, source, offset) if profile else None
    if record is None or record['entries'] != len(wfm.dialogues):
        return False
    for index, dialogue in enumerate(wfm.dialogues):
        evidence = record['text'].get(str(index))
        dialogue.usage = evidence or dict(status='unknown', method='partial-native-reference-study',
            evidence=['Literal display calls and scripts were studied, but no resolved selection is recorded '
                      'for this entry. Computed indices and other display paths remain unchecked; '
                      'this does not establish that the entry is unused.'])
    wfm.usage_summary = record['coverage']
    return True


def project_counts(project):
    """Tree counts from verified metadata, without decoding every font bitmap."""
    from game.builds import executable
    found = executable(project)
    if found is not None and found.build.legacy8:
        from formats.text.export import collect
        return counts(collect(project))
    profile = _study_for(project)
    if profile is None:
        return {}, {}
    banks, files = {}, {}
    for key, data in profile['banks'].items():
        source, offset = key.rsplit('@', 1)
        record = _bank_study(project, profile, source, int(offset, 16))
        if record is None:
            continue
        count = sum(item['status'] == 'not_found' for item in record['text'].values())
        if not count and len(record['text']) < record['entries']:
            count = None
        banks[source, int(offset, 16)] = count
        previous = files.get(source, 0)
        total = (previous or 0) + (count or 0)
        files[source] = total if total else None if previous is None or count is None else 0
    return banks, files

PREPRE9_EXES = {'36f830000f34ef6414afb020993806b4009e4ca1',
               '72988193d496a3a9402399d04291997d57b4be45'}
PREPRE9_CODE = {'2c67e33d098daaca2de4d98a400fe0148fc21f27',
               'a38f0e77649d9a9e35ba788086baed9a93be4758',
               '4a4f68771c049af9cc8822c63aa507f0b592ce14',
               'b17867d4c7f64a5a1b0a64b16828de9709ebafc3',
               '1ff5fb3943c2df020cdc3734843a5db1afce5433'}


def supported(project):
    from game.builds import executable
    found = executable(project)
    return found is not None and (found.build.legacy8
        or hashlib.sha1(found.data).hexdigest() in PREPRE9_EXES
        or hashlib.sha1(found.data).hexdigest() in _study_index())


def attach(wfm, project, source, offset):
    """Build-specific display evidence; never infer use from successful decoding."""
    if wfm.version == b'PP8' or any(entry(d) for d in wfm.dialogues):
        return
    try:
        if _attach_study(wfm, project, source, offset):
            return
    except (OSError, ValueError):
        wfm.usage_summary = 'Usage not checked: the native study could not validate this disc data.'
        return
    from game.builds import executable
    from formats.archive.ldar import area_number
    found = executable(project)
    if found is None or hashlib.sha1(found.data).hexdigest() not in PREPRE9_EXES:
        return
    if '_prepre9_text_code_verified' not in project.__dict__:
        seen, digests = set(), set()
        for groups in project.ldars.values():
            for group in groups:
                for asset in group.assets:
                    if asset.kind == 'INS' and asset.source and asset.source.path not in seen:
                        seen.add(asset.source.path)
                        digests.add(hashlib.sha1(project.asset_data(asset)).hexdigest())
        project._prepre9_text_code_verified = digests == PREPRE9_CODE
    if not project._prepre9_text_code_verified:
        return
    assets = [a for a in project.by_source.get(source, ()) if a.kind == 'WFM' and a.offset == offset]
    contexts = {(area_number(a.ldar), a.slot) for a in assets if area_number(a.ldar) in (1, 2)}
    if not contexts:
        return
    title = all(slot == 1 for area, slot in contexts)
    references = {}
    for area, slot in contexts:
        if slot == 1 and len(wfm.dialogues) == 30:
            # 8001F044 reads table[event][area], then the WFM dialogue
            # directory. The completion banner also uses the first seven
            # glyphs directly, matching title entry zero's CLEAR! sequence.
            if index_zero := wfm.dialogues[0]:
                glyphs = [word & 0xFFF for word, _ in index_zero.tokens if word < 0xFF00]
                if glyphs == list(found.unpack('<7H', 0x800705A0)):
                    references.setdefault(0, []).append(
                        'Event banner fixed glyph table 800705A0 displays this entry\'s seven glyphs '
                        'directly. Native object construction checked in AREA01 and AREA02; '
                        'no event-title directory selection is needed.')
            for event in range(200):
                pointer = found.word(0x8007113C + event * 4)
                index = found.unpack('<B', pointer + area)[0]
                if index < len(wfm.dialogues):
                    references.setdefault(index, []).append(
                        f'AREA{area:02d} event {event}: selector 8001F044, mapping at {pointer + area:08X}.')
        elif slot == 0:
            # The early info-notice routine adds two bytes selected by area;
            # unlike WFM3, these are an absolute base plus a line, not a
            # WFM header group lookup. Both item and event notices matter.
            for table, count, kind in ((0x80072A00, 50, 'item'), (0x80072BD0, 22, 'event notice')):
                for number in range(count):
                    pointer = found.word(table + number * 4) + area * 2
                    base, line = found.unpack('<2B', pointer)
                    index = base + line
                    if base != 255 and index < len(wfm.dialogues):
                        references.setdefault(index, []).append(
                            f'AREA{area:02d} {kind} {number}: info routine 80031A00, pair at {pointer:08X}.')
    for index, dialogue in enumerate(wfm.dialogues):
        evidence = references.get(index, [])
        if evidence:
            status = 'referenced'
            evidence = evidence + ['A display-table reference is not proof that every corresponding event/item is reachable.']
        elif title and len(wfm.dialogues) == 30:
            status = 'unknown'
            evidence = ['No event maps to this title entry in AREA01 or AREA02. '
                        'Native selector 8001F044 was checked for all 116 valid area/event/completion combinations.',
                        'The other bank-1 reader loads glyph images, not dialogue entries. '
                        'DSPSUB\'s separate text window selects banks 2/3. '
                        'Other direct glyph paths need checking; a mapping gap alone is not an unused candidate.']
        else:
            status = 'unknown'
            evidence = ['Item/event notice tables were checked. Conversation state, object-supplied indices '
                        'and script message paths are not yet fully traced for this entry; no unused conclusion.']
        dialogue.usage = dict(status=status, evidence=evidence, method='prepre9-native-display-v1')
    wfm.usage_summary = ('PrePre 9: event-title selection and item/event notice tables checked against native code. '
                         'Remaining dialogue/script paths are explicitly unchecked. Decoding does not establish use.')


LABELS = {'referenced': 'Display reference', 'dynamic': 'Dynamic display selection',
          'not_found': 'Possibly unused', 'unknown': 'Usage not checked'}


def entry(dialogue):
    return getattr(dialogue, 'usage', None)


def label(dialogue):
    result = entry(dialogue)
    return LABELS.get(result['status'], '') if result else ''


def explanation(dialogue):
    result = entry(dialogue)
    if not result:
        return 'In-game text usage has not been traced for this build.'
    return label(dialogue) + '\n' + '\n'.join(result['evidence'])


def counts(banks):
    """Count audited candidates once per bank, and total them per source file."""
    by_bank, by_file = {}, {}
    for bank in banks:
        key = bank.source, bank.offset
        if key in by_bank:
            continue
        count = sum((entry(d) or {}).get('status') == 'not_found' for d in bank.wfm.dialogues)
        if not count and any((entry(d) or {}).get('status', 'unknown') == 'unknown' for d in bank.wfm.dialogues):
            count = None  # Unknown is not an audited zero.
        by_bank[key] = count
        previous = by_file.get(bank.source, 0)
        total = (previous or 0) + (count or 0)
        by_file[bank.source] = total if total else None if previous is None or count is None else 0
    return by_bank, by_file


def prepre8(found, bank):
    """All fourteen calls to the embedded group/line window constructor.

    80035ADC is the only code reader of A5DE4's message-table directory.
    800405C4 selects a pair from the signpost table by object subtype.
    Conversation counters are dynamic: retain their whole groups, rather
    than calling unobserved branches unused. Event/item sprite notices use
    other constructors; they do not select these embedded text streams.
    """
    from formats.sprites.animations import code_constants
    sink = 0x80035ADC
    # (call site, group, line). None means the line comes from runtime state.
    calls = {0x80034DC8: (0, None), 0x8007ED74: (11, 0), 0x8007F1C0: (11, 1),
             0x800843A8: (2, None), 0x80084604: (2, None), 0x80084658: (2, None),
             0x80084734: (2, None), 0x80084A68: (1, None), 0x80084BCC: (1, None),
             0x80084E14: (1, None), 0x80085068: (3, None), 0x80085330: (3, 1),
             0x80085370: (3, None)}
    table_call, table, count = 0x800405C4, 0x800A7DDC, 10
    payload = found.data[0x800:]
    actual = set()
    for offset in range(0, len(payload) - 3, 4):
        word = struct.unpack_from('<I', payload, offset)[0]
        if word >> 26 in (2, 3) and ((word & 0x3FFFFFF) << 2 | 0x80000000) == sink:
            actual.add(found.base + offset)
    constants = code_constants(found.base, payload)
    # A new call, function pointer, or second directory reader invalidates
    # negative conclusions. The supported executable is hash-identified too.
    complete = (hashlib.sha1(found.data).hexdigest() == '032d6f371b31085098b86aebbce465d30599293a'
                and actual == set(calls) | {table_call}
                and struct.pack('<I', sink) not in payload
                and not constants.get(sink)
                and set(constants.get(0x800A5DE4, ())) == {0x80035B84})
    by_pair, dynamic = {}, {}
    for address, (group, line) in calls.items():
        if line is None:
            dynamic.setdefault(group, []).append(
                f'Window call {address:08X}: group {group:02X}, line selected by conversation state. '
                'This entry remains potentially used; its individual reachability is not proven.')
        else:
            by_pair.setdefault((group, line), []).append(
                f'Window call {address:08X} selects {group:02X}:{line:02X}.')
    for variant in range(count):
        group, line = struct.unpack_from('<2h', found.data, table - found.base + 0x800 + variant * 8)
        by_pair.setdefault((group, line), []).append(
            f'Signpost call {table_call:08X}, subtype {variant}: '
            f'table {table + variant * 8:08X} selects {group:02X}:{line:02X}. '
            'A table reference alone does not prove that this subtype is reachable on this disc.')
    for group, start in enumerate(bank.groups):
        end = bank.groups[group + 1] if group + 1 < len(bank.groups) else len(bank.dialogues)
        for line, dialogue in enumerate(bank.dialogues[start:end]):
            evidence = list(by_pair.get((group, line), ()))
            status = 'referenced' if evidence else 'dynamic' if group in dynamic else 'not_found'
            evidence += dynamic.get(group, [])
            if not complete:
                status = 'unknown'
                evidence.append('The executable has display paths outside the verified profile; negative results withheld.')
            elif status == 'not_found':
                evidence = [f'No selection of {group:02X}:{line:02X} found among all 14 calls to window '
                            f'{sink:08X}, including conversation counters and the signpost subtype table.',
                            'Unused candidate, not proof of absence from every possible game state. '
                            'This check does not rely on missing glyphs or playthrough coverage.']
            # Independently materialised stream pointers need further tracing.
            pointer = found.base + dialogue.offset - 0x800
            if constants.get(pointer):
                status = 'unknown'
                evidence.append('The stream address is also materialised directly by code; its use needs tracing.')
            dialogue.usage = dict(status=status, evidence=evidence, method='prepre8-native-display-v1')
    bank.usage_summary = ('Native display audit: all 14 window calls, dynamic conversation groups and '
                          'the 10 signpost records. No-use results are unused candidates, not proven unreachable.')
