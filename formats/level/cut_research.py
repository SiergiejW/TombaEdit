"""Retail evidence browser; live data is gated by the audited JP fingerprints."""
import hashlib
import json
from pathlib import Path
import struct

REPORT = Path(__file__).resolve().parents[2] / 'docs' / 'cut-villages-jp-research.md'
REFERENCES = REPORT.parent / 'decomp'
JP_EXE = '07d577698ad31ec1a69b9d7b80a7c3f90b650888'
STOPS = ((55, 375), (231, 367), (390, 375), (111, 159), (230, 151), (334, 159))
PASSAGES = ((100, 420, 128, 428), (110, 348, 128, 354),
            (295, 406, 312, 410), (280, 268, 296, 272))


def reference_manifest():
    """Verify the bundled snapshot before presenting it as synchronized."""
    manifest = json.loads((REFERENCES/'manifest.json').read_text(encoding='utf8'))
    for entry in manifest['files']:
        target = (REFERENCES/entry['path']).resolve()
        if REFERENCES.resolve() not in target.parents:
            raise ValueError('Reference path outside bundle')
        data = target.read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f"Reference integrity check failed: {entry['path']}")
    return manifest


def supported(project):
    from game.builds import executable
    exe = executable(project)
    return exe is not None and hashlib.sha1(exe.data).hexdigest() == JP_EXE


def animations(project):
    """Decode the original pointer chain, not a transcribed frame list."""
    from game.builds import executable
    from formats.level.cut_village_view import _overlay
    from formats.level.cut_towns import JP_INFO2_SHA1
    if not supported(project):
        raise ValueError('The executable differs from the audited Japanese retail build.')
    exe = executable(project)
    overlay = bytes(_overlay(project))
    if hashlib.sha1(overlay).hexdigest() != JP_INFO2_SHA1:
        raise ValueError('INFO2 differs from the audited overlay; live findings are unavailable.')
    base = exe.build.overlay

    def read(address, count):
        if base <= address and address + count <= base + len(overlay):
            return overlay[address-base:address-base+count]
        if exe.holds(address, count):
            offset = address-exe.base+0x800
            return exe.data[offset:offset+count]
        raise ValueError(f'Animation pointer outside resident data: {address:08X}')

    table = struct.unpack('<I', read(0x801000D8+8, 4))[0]
    rows = []
    for index in range(24):
        address = struct.unpack('<I', read(table+index*4, 4))[0]
        cursor, steps, seen = address, [], set()
        while cursor not in seen and len(steps) < 256:
            seen.add(cursor)
            frame, box, argument, control = struct.unpack('<HHhH', read(cursor, 8))
            steps.append((frame, control & 0x3FFF, box, argument, control))
            if control & 0xC000 == 0x8000:
                break
            cursor = struct.unpack('<I', read(cursor+8, 4))[0] if control & 0x4000 else cursor+8
        else:
            raise ValueError('Animation sequence has no bounded terminal step.')
        rows.append((index, address, steps))
    return rows


def view(project, jump=None, area=None):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor, QTextDocument
    from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                                QPushButton, QSplitter, QListWidget, QTextBrowser,
                                QTabWidget, QTableWidget, QTableWidgetItem, QComboBox)
    widget = QWidget()
    layout = QVBoxLayout(widget)
    try:
        manifest = reference_manifest()
        sync = f"Upstream snapshot {manifest['revision'][:12]} • checked {manifest['checked_date']} • file hashes verified"
    except (OSError,ValueError,KeyError,TypeError) as exc:
        manifest = None
        sync = f'Upstream reference snapshot unavailable: {exc}'
    note = QLabel(sync + '\n'
                  'Recovered code/data, incomplete scenes and reconstruction leads are distinguished in the report. '
                  'The report records the original editor discrepancy; this editor now uses corrected dialogue bindings.')
    note.setWordWrap(True)
    layout.addWidget(note)
    tabs = QTabWidget()
    layout.addWidget(tabs, 1)
    article = QWidget()
    body = QVBoxLayout(article)
    documents = QComboBox()
    documents.addItem('TombaEdit: JP findings, corrections and upstream recalibration', (REPORT, None))
    if manifest:
        for entry in manifest['files']:
            url = f"{manifest['repository']}/blob/{manifest['revision']}/{entry['path']}"
            documents.addItem('Upstream: '+entry['label'], (REFERENCES/entry['path'],url))
    body.addWidget(documents)
    bar = QHBoxLayout()
    search = QLineEdit()
    search.setPlaceholderText('Find in the complete research report (addresses, functions, items…)')
    bar.addWidget(search)
    previous, next_button = QPushButton('Previous'), QPushButton('Next')
    bar.addWidget(previous)
    bar.addWidget(next_button)
    body.addLayout(bar)
    split = QSplitter()
    outline, text = QListWidget(), QTextBrowser()
    text.setOpenExternalLinks(True)
    headings = []
    split.addWidget(outline)
    split.addWidget(text)
    split.setStretchFactor(1, 1)
    split.setSizes([250, 850])
    body.addWidget(split, 1)
    status = QLabel()
    status.setMaximumHeight(24)
    body.addWidget(status)

    def find(backward=False):
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        if not search.text():
            status.clear()
            return
        if not text.find(search.text(), flags):
            text.moveCursor(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            found = text.find(search.text(), flags)
            status.setText('Wrapped search' if found else 'No match')
        else:
            status.clear()

    def section(index):
        if index >= 0:
            text.moveCursor(QTextCursor.MoveOperation.Start)
            text.find(headings[index])

    outline.currentRowChanged.connect(section)
    def document_changed():
        from PyQt6.QtCore import QUrl
        path,url = documents.currentData()
        try:
            report = path.read_text(encoding='utf8')
        except OSError as exc:
            report = f'Document unavailable: {exc}'
        text.document().setBaseUrl(QUrl(url or ''))
        text.setMarkdown(report)
        outline.clear()
        headings.clear()
        for line in report.splitlines():
            if line.startswith('## '):
                heading = QTextDocument()
                heading.setMarkdown(line)
                headings.append(heading.toPlainText().strip())
        outline.addItems(headings)
        status.clear()
    documents.currentIndexChanged.connect(document_changed)
    document_changed()
    search.returnPressed.connect(find)
    next_button.clicked.connect(lambda: find(False))
    previous.clicked.connect(lambda: find(True))
    tabs.addTab(article, 'Research and sources')

    def table(headers, rows):
        result = QTableWidget(len(rows), len(headers))
        result.setHorizontalHeaderLabels(headers)
        result.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem()
                if isinstance(value, int):
                    item.setData(Qt.ItemDataRole.DisplayRole, value)
                else:
                    item.setText(str(value))
                result.setItem(i, j, item)
        result.resizeColumnsToContents()
        return result

    from formats.level.community_reference import snapshot, compare_palette
    community = snapshot()
    reference = QWidget()
    reference_layout = QVBoxLayout(reference)
    reference_note = QLabel(
        f'Community civ_towns spreadsheet · read-only snapshot {community["retrieved"]}. '
        'Confidence and identification claims are transcribed from the sheet, not independently confirmed. '
        'Palette labels attach only when all 16 words match the opened ROM. '
        'Resident/prop rows are reference data, not live ROM decoding. '
        'Lost sprite mappings remain unknown; patrol boxes may be relative coordinates. '
        'P# prop markers and passage scene numbers are separate numbering systems. '
        f'<a href="{community["source"]}">Open current community sheet</a>')
    reference_note.setWordWrap(True)
    reference_note.setOpenExternalLinks(True)
    reference_layout.addWidget(reference_note)
    reference_tabs = QTabWidget()
    reference_layout.addWidget(reference_tabs)
    for title, rows in community['sheets'].items():
        if title == 'Read me':
            reference_tabs.addTab(table(['Source notes'], rows), title)
        else:
            headers = [str(v or '') for v in rows[0]]
            values = [[v if v is not None else '' for v in row] for row in rows[1:]]
            if title == 'Palettes':
                order = [0, 1, 2, 20, 21, 22] + list(range(4, 20)) + [23, 24, 25, 26, 3]
                headers = ['Sheet row', 'Opened ROM comparison'] + [headers[i] for i in order] + ['Opened ROM 16 words']
                values = [[n, compare_palette(project, row)[0]] + [value[i] for i in order] +
                          [compare_palette(project, row)[1]] for n, (row, value) in enumerate(zip(rows[1:], values), 2)]
            shown = table(headers, values)
            if title == 'Palettes':
                from PyQt6.QtGui import QColor
                for n, row in enumerate(rows[1:]):
                    for column, word in enumerate(row[26].split(), 8):
                        word = int(word, 16)
                        rgb = [(word >> shift & 31) * 255 // 31 for shift in (0, 5, 10)]
                        cell = shown.item(n, column)
                        cell.setText(f'{word:04X}')
                        cell.setBackground(QColor(*rgb))
                        cell.setForeground(QColor('black' if sum(rgb) > 384 else 'white'))
                        cell.setToolTip('Community sheet colour, not the opened ROM value. Bit 15 is preserved in the hex word.')
            shown.setSortingEnabled(True)
            shown.sortItems(0, Qt.SortOrder.AscendingOrder)
            reference_tabs.addTab(shown, title)
    tabs.addTab(reference, 'Community palettes, residents and props')

    try:
        decoded = animations(project)
        rows = [(i, f'{address:08X}', ', '.join(str(s[0]) for s in steps),
                 ', '.join(str(s[1]) for s in steps), 'Hold final frame (8000)')
                for i, address, steps in decoded]
        tabs.addTab(table(['Script', 'JP address', 'Frames', 'Update ticks', 'End control'], rows),
                    'Recovered animations · live ROM')
    except ValueError as exc:
        warning = QLabel(str(exc))
        warning.setWordWrap(True)
        tabs.addTab(warning, 'Live data unavailable')
    rows = [(f'{"Lower" if i < 3 else "Upper"} lift, stop {i % 3 + 1}',
             f'{x}..{x+2}, {y}..{y+2}', 'Board / ride / walk off', '801018CC / 800FE0EC')
            for i, (x, y) in enumerate(STOPS)]
    rows += [(f'Passage scene {n}', f'{a}..{c}, {b}..{d}', motion, address)
             for n, (a, b, c, d), motion, address in zip((8, 9, 10, 11), PASSAGES,
                 ('Up 84 px', 'Down 84 px', 'Up 145 px, sideways', 'Down 145 px, sideways'),
                 ('800FE22C', '800FE3D8', '800FE504', '800FE668'))]
    tabs.addTab(table(['Iron Town mechanism', 'World trigger x, y (inclusive)', 'Behavior', 'JP source address'], rows),
                'Iron Town · lifts and passages · audited JP')
    if jump:
        towns = QHBoxLayout()
        for number, name in ((11, 'Lumberjack Town'), (16, 'Stonetown'), (17, 'Iron Town'), (18, 'Reunited town')):
            button = QPushButton(f'Open {name} plan')
            button.clicked.connect(lambda checked=False, n=number: jump('village', (f'SYS/LDAR{n:02d}.BIN', 1)))
            towns.addWidget(button)
        layout.addLayout(towns)
        links = QHBoxLayout()
        for label, path in (('INFO2 code', 'SYSTEM/INFO2.BIN'), ('Inventory conditions', 'SYSTEM/DSPSUB.BIN'),
                            ('Main executable', 'SLPS_011.44'), ('Orphan X19', 'SYSTEM/X19.BIN')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, p=path: jump('file', p))
            links.addWidget(button)
        layout.addLayout(links)
    if area:
        terms = {11: 'Lumberjack Town has a conditional', 16: 'Confirmed correction:',
                 17: "Iron Town's iron-lump", 18: 'Upstream recalibration'}
        wanted = terms.get(area, '')
        index = next((i for i, h in enumerate(headings) if wanted in h), -1)
        if index >= 0:
            outline.setCurrentRow(index)
    return widget


def show_dialog(project, parent=None, jump=None, area=None):
    from PyQt6.QtWidgets import QDialog, QVBoxLayout
    from PyQt6.QtCore import Qt
    dialog = QDialog(parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowTitle('Cut-village research · Japanese retail')
    dialog.resize(1200, 800)
    QVBoxLayout(dialog).addWidget(view(project, jump, area))
    dialog.show()
    return dialog
