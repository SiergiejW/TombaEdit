"""Evidence about text selected by the native game's display paths.

Absence from a scan is a candidate, never proof that an entry is unreachable.
Profiles are build specific. Unsupported/incomplete coverage stays unknown.
"""
import struct
import hashlib


LABELS = {'referenced': 'Display reference', 'dynamic': 'Dynamic display selection',
          'not_found': 'No in-game use found', 'unknown': 'Usage not checked'}


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
        by_file[bank.source] = None if previous is None or count is None else previous + count
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
