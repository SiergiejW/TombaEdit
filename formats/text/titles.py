"""Where the letters of an event title go.

A title's dialogue in the 24-pixel font holds only its letters: no spaces,
no line breaks. Those are in the code overlays, as one list of four-byte
records per title, one record per letter in order: a zero byte, the
column, the row and a flags byte (routine 8005AA74 of the European build,
spawnEventTitle in Tombi-Decomp). A letter is drawn at column × 10, row × 14
from the title's centre; letters are two columns apart, a space adds one,
and a new line is two rows down. A list ends with a record starting FF.
The lists of dialogues 2 on are stored one after another, the same in every
overlay of a language, so they are found by their lengths: the run of lists
whose lengths are the titles' letter counts (Tombi-Decomp, tools/title_layout.py).
"""
import struct

FIRST = 2           # dialogues 0 and 1 have no list
MIN_RUN = 8         # lists that must agree before a run is taken
LANGUAGE_LETTERS = 'BFGIHSPWD'      # CFNT999?.WFM of the European disc, by language


def letters(dialogue):
    return sum(1 for word, _ in dialogue.tokens if word < 0xFF00)


def is_title_font(wfm):
    """Titles have a font of their own: 24 pixels tall, 20 in the 1997
    builds."""
    heights = {height for _, _, height, _ in wfm.glyph_headers}
    return len(heights) == 1 and heights <= {20, 24}


def read_list(data, at):
    records = []
    while at + 4 <= len(data):
        if data[at] == 0xFF:
            return records
        if data[at] != 0 or len(records) > 64:
            return None
        records.append(struct.unpack_from('<bbB', data, at + 1))
        at += 4
    return None


def all_lists(data, at):
    """The lists stored one after another from `at`."""
    out = []
    while True:
        records = read_list(data, at)
        if not records:
            return out
        out.append(records)
        at += 4 * (len(records) + 1)


def align(counts, lists):
    """{index in counts: index in lists}: the order-kept match of lengths
    with the most pairs (a longest common subsequence), so a title without
    a list is passed over instead of shifting the rest."""
    n, m = len(counts), len(lists)
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best[i][j] = max(best[i + 1][j], best[i][j + 1],
                             best[i + 1][j + 1] + 1 if counts[i] == len(lists[j]) else 0)
    out, i, j = {}, 0, 0
    while i < n and j < m:
        if counts[i] == len(lists[j]) and best[i][j] == best[i + 1][j + 1] + 1:
            out[i] = j
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def find_layouts(data, counts):
    """{dialogue number: [(column, row, flags)]}: the longest block of lists
    in `data`, matched to the titles by length (`counts`, letters of the
    dialogues FIRST on)."""
    best, at = {}, 0
    while at < len(data) - 8:
        if data[at] == 0 and read_list(data, at):
            lists = all_lists(data, at)
            if len(lists) >= MIN_RUN:
                found = {FIRST + i: lists[j] for i, j in align(counts, lists).items()}
                if len(found) > len(best):
                    best = found
                at += 4 * sum(len(r) + 1 for r in lists)
                continue
        at += 4
    return best


def text(dialogue, layout, character):
    """A title's text with its spaces and line breaks. `character(word)`
    gives a letter's text."""
    out, previous = [], None
    words = [word for word, _ in dialogue.tokens if word < 0xFF00]
    for word, (column, row, _) in zip(words, layout):
        if previous is not None:
            if row != previous[1]:
                out.append('\n')
            elif column - previous[0] > 2:
                out.append(' ')
        out.append(character(word))
        previous = (column, row)
    return ''.join(out)


def overlays(project, language=None):
    """Bytes of the code overlays loaded with a language's tables."""
    from formats.archive.ldar import table_name
    seen = set()
    for path, groups in project.ldars.items():
        if language is not None and table_name(path)[0] not in (language, None):
            continue
        for group in groups:
            for asset in group.assets:
                if asset.kind == 'INS' and asset.source is not None and asset.source.path not in seen:
                    seen.add(asset.source.path)
                    try:
                        yield project.asset_data(asset)
                    except Exception:
                        continue


def attach(wfm, project, language=None):
    """Give a title font's dialogues their layout (`Dialogue.layout`).
    Returns the number of titles laid out."""
    if not is_title_font(wfm) or len(wfm.dialogues) <= FIRST + 4:
        return 0
    counts = [letters(d) for d in wfm.dialogues[FIRST:]]
    # Every overlay of a language carries the lists, a few only some of
    # them and the first title's differs between them: the overlay that
    # lays out the most titles is taken.
    cache = project.__dict__.setdefault('title_layouts', {})
    key = (language, tuple(counts))
    if key not in cache:
        import hashlib
        best, tried = {}, set()
        for data in overlays(project, language):
            digest = hashlib.sha1(data).digest()
            if digest in tried:
                continue
            tried.add(digest)
            found = find_layouts(bytes(data), counts)
            if len(found) > len(best):
                best = found
        cache[key] = best
    best = cache[key]
    for number, records in best.items():
        wfm.dialogues[number].layout = records
    return len(best)


def language_of(name):
    """The language number of a CFNT999?.WFM file name, or None."""
    stem = name.upper().rsplit('/', 1)[-1].split('.')[0]
    if stem.startswith('CFNT') and stem[-1:] in LANGUAGE_LETTERS:
        return LANGUAGE_LETTERS.index(stem[-1])
    return None
