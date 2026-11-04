"""Retail evidence browser; live data is gated by the audited JP fingerprints."""
import hashlib
import json
import re
from pathlib import Path
import struct

REPORT = Path(__file__).resolve().parents[2] / 'docs' / 'cut-villages-jp-research.md'
UNUSED_REPORT = REPORT.parent / 'jp-retail-unused-research.md'
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
                                QTabWidget, QTableWidget, QTableWidgetItem, QComboBox,
                                QDialog, QMessageBox)
    widget = QWidget()
    layout = QVBoxLayout(widget)
    try:
        manifest = reference_manifest()
        sync = f"Upstream snapshot {manifest['revision'][:12]} • checked {manifest['checked_date']} • file hashes verified"
    except (OSError,ValueError,KeyError,TypeError) as exc:
        manifest = None
        sync = f'Upstream reference snapshot unavailable: {exc}'
    note = QLabel(sync + '\n'
                  'Choose a report below for cut villages or other JP remnants, including the eel, items and animations. '
                  'Native findings, incomplete connections and unverified leads are identified in each report.')
    note.setWordWrap(True)
    layout.addWidget(note)
    tabs = QTabWidget()
    layout.addWidget(tabs, 1)
    article = QWidget()
    body = QVBoxLayout(article)
    documents = QComboBox()
    documents.addItem('TombaEdit: JP findings, corrections and upstream recalibration', (REPORT, None))
    documents.addItem('TombaEdit: JP unused content beyond cut villages', (UNUSED_REPORT, None))
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
    chief = QPushButton('Masakari Chief dialogue and sprites')
    chief.setToolTip('Open the JP Chief research, including the complete recovered dialogue.')
    def show_chief():
        documents.setCurrentIndex(1)
        index = next((i for i, heading in enumerate(headings) if heading.startswith('Masakari Chief —')), -1)
        if index >= 0:
            outline.setCurrentRow(index)
    chief.clicked.connect(show_chief)
    bar.addWidget(chief)
    if jump:
        from formats.level.scene import loaded_resources
        jungle = project.ldars.get('SYS/LDAR10.BIN', [])
        chief_bank = loaded_resources(project, 'SYS/LDAR10.BIN', 1).get(('SPR', 7)) if len(jungle) > 1 else None
        if chief_bank is not None:
            inspect_chief = QPushButton('Open Chief sprite bank')
            inspect_chief.setToolTip('Open Jungle SPR slot 7. JP chief frame definitions and texture pixels match PAL; the intended runtime palette is unconfirmed.')
            inspect_chief.clicked.connect(lambda checked=False: jump('asset', chief_bank))
            bar.addWidget(inspect_chief)
            preview_chief = QPushButton('Preview JP Chief')
            preview_chief.setToolTip('Preview the recovered JP texture and candidate frames with a stored palette; the runtime palette is not established.')
            def show_chief_preview():
                try:
                    import numpy as np
                    from psx.graphics import sprite_frames, render_sprite
                    from gui.widgets.image_view import ImageView
                    if not supported(project):
                        raise ValueError('This preview requires the audited Japanese retail executable.')
                    bank = project.asset_data(chief_bank)
                    group = project.ldars['SYS/LDSYS.BIN'][57]
                    page = next(a for a in group.assets if a.kind == 'GRPX')
                    pixels = project.asset_data(page)
                    if (hashlib.sha1(bank).hexdigest() != 'e3dc39e7c1eed97e3fbc487d0d69d2557cbaa787' or
                            hashlib.sha1(pixels).hexdigest() != 'f48629510d5b7838647d23b6d90d21e616ec8cdc'):
                        raise ValueError('The sprite bank or system texture differs from the audited JP retail data.')
                    frames = sprite_frames(bank)
                    vram = project.vram('SYS/LDAR10.BIN', 1).copy()
                    vram[0:256, 64:256] = np.frombuffer(pixels, '<u2').reshape(256, 192)
                    dialog = QDialog(widget)
                    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                    dialog.setWindowTitle('JP Masakari Chief — recovered sprite candidates')
                    dialog.resize(620, 650)
                    content = QVBoxLayout(dialog)
                    explanation = QLabel('JP sprite definitions and texture pixels match the PAL candidates. '
                                         'This preview uses stored CLUT 780A; the intended runtime palette is unknown. '
                                         'Frame 53 is an unrelated mis-cut atlas block.')
                    explanation.setWordWrap(True)
                    content.addWidget(explanation)
                    choices = QComboBox()
                    for frame in (31, 47, 48, 49, 50, 51, 52, 54, 55, 56, 57, 58):
                        choices.addItem(f'Frame {frame}', frame)
                    content.addWidget(choices)
                    picture = ImageView()
                    picture.zoom.setCurrentIndex(0)
                    content.addWidget(picture, 1)
                    def update_preview():
                        frame = choices.currentData()
                        picture.export_name = f'JP Chief frame {frame} - CLUT 780A'
                        picture.set_image(render_sprite(frames[frame], vram, tpage=1, clut=0x780a), subject='chief')
                    choices.currentIndexChanged.connect(update_preview)
                    update_preview()
                    dialog.show()
                except (KeyError, IndexError, StopIteration, ValueError, OSError) as exc:
                    QMessageBox.warning(widget, 'Chief preview unavailable', str(exc))
            preview_chief.clicked.connect(show_chief_preview)
            bar.addWidget(preview_chief)
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
    rocks = QWidget()
    rocks_layout = QVBoxLayout(rocks)
    rock_note = QLabel('Graffiti Rock research from Tombi-Decomp. Two plaques have documented retail placements; '
                       'the other texture finds and their intended puzzle are research evidence. '
                       'The JP text buttons open the complete original entries.')
    rock_note.setWordWrap(True)
    rocks_layout.addWidget(rock_note)
    rocks_layout.addWidget(table(['Plaque value', 'Reported area / texture', 'Retail placement'], [
        ('2', 'AREA01 / AREA07 forest', 'Placed as a decorative model'),
        ('5', 'AREA04 / AREA12 Haunted Mansion', 'Placed as a decorative model'),
        ('18', 'AREA03 mountain / caves', 'Texture found; placement not identified'),
        ('139', 'AREA10 jungle', 'Texture found; placement not identified'),
        ('59', 'AREA11; also JP AREA10 room pages', 'Texture found; placement not identified'),
    ]))
    if jump:
        rock_links = QHBoxLayout()
        def open_rock_text(area, entry):
            from formats.text.export import collect
            source = f'AREA{area:02d}/A003.GAM'
            bank = next((b for b in collect(project, area=area)
                         if b.source == source and b.offset == 0x6CA8 and entry < len(b.wfm.dialogues)), None)
            if bank is not None:
                jump('text', (bank.wfm, bank.source, bank.offset, bank.name, entry))
        for label, area_number, entry in (('Digger: hidden hint · #433', 2, 433),
                                          ('Stone villager: rock · #188', 16, 188),
                                          ('Stone villager: numerals · #189', 16, 189)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, a=area_number, e=entry: open_rock_text(a, e))
            rock_links.addWidget(button)
        forest = project.ldars.get('SYS/LDAR02.BIN', [])
        glyph = next((a for a in (forest[4].assets if len(forest) > 4 else ())
                      if a.source and a.source.path == 'AREA02/B301.000'), None)
        if glyph is not None:
            button = QPushButton('Open tunnel glyph sheet')
            button.setToolTip('Upstream identifies a 10 × 3 grid of 24-pixel cells at page 13, u 0–239, v 72–143.')
            button.clicked.connect(lambda checked=False: jump('asset', glyph))
            rock_links.addWidget(button)
        rocks_layout.addLayout(rock_links)
    tabs.addTab(rocks, 'Graffiti Rocks · research')
    recent = QWidget()
    recent_layout = QVBoxLayout(recent)
    recent_note = QLabel('Recent Tombi-Decomp findings: regional addresses and unreferenced-code conclusions '
                         'are attributed to upstream research. Open the research report for details and limits.')
    recent_note.setWordWrap(True)
    recent_layout.addWidget(recent_note)
    recent_layout.addWidget(table(['Finding', 'JP location', 'Research result'], [
        ('Flower Tower gate', 'X01 80116238', 'Million-AP threshold; tower interior is AREA13 section 0'),
        ('Caterpillar patrol', 'X01 80131DB8', 'Older one-way route; no identified retail caller'),
        ('Flower Tears seeker', 'X09 80127CD4', 'Unreferenced walk-off routine'),
        ('Seven Friends', 'X02 801182E4', 'Unreferenced fly-up exit routine'),
        ('Debug font', 'MAIN 80021E5C', '8 × 8 font used by JP ending and game-over text'),
    ]))
    if jump:
        system = project.ldars.get('SYS/LDSYS.BIN', [])
        font = next((a for a in (system[0].assets if system else ())
                     if a.source and a.source.path == 'SYSTEM/A00000.GAM'), None)
        if font is not None:
            button = QPushButton('Open system font texture')
            button.setToolTip('The 8 × 8 debug font is on the resident system texture; palette rows begin at VRAM (368, 496).')
            button.clicked.connect(lambda checked=False: jump('asset', font))
            recent_layout.addWidget(button)
    tabs.addTab(recent, 'Recent upstream findings')
    if manifest and any(item['path'] == 'docs/EVENTS_MAP.md' for item in manifest['files']):
        event_page = QWidget()
        event_layout = QVBoxLayout(event_page)
        event_note = QLabel('Upstream PAL event-location research, including script and shared-overlay references. '
                            'Locations and unknown entries are research leads; JP equivalence is not assumed.')
        event_note.setWordWrap(True)
        event_layout.addWidget(event_note)
        event_filter = QLineEdit()
        event_filter.setPlaceholderText('Filter by event ID, area, section, source or description')
        event_layout.addWidget(event_filter)
        event_rows = []
        for line in (REFERENCES/'docs'/'EVENTS_MAP.md').read_text(encoding='utf8').splitlines():
            if not re.match(r'^\|\s*\d+\s*\(0x[0-9A-Fa-f]+\)', line):
                continue
            cells = [part.strip() for part in line.strip().strip('|').split('|', 3)]
            if len(cells) == 4:
                event_rows.append(cells)
        event_table = table(['Event ID', 'Location', 'Kind', 'Evidence'], event_rows)
        for row in range(event_table.rowCount()):
            for column in range(event_table.columnCount()):
                event_table.item(row, column).setToolTip(event_table.item(row, column).text())
        event_layout.addWidget(event_table)
        def filter_events(value):
            needle = value.casefold().strip()
            for row, cells in enumerate(event_rows):
                event_table.setRowHidden(row, bool(needle) and needle not in ' '.join(cells).casefold())
        event_filter.textChanged.connect(filter_events)
        tabs.addTab(event_page, 'Event locations · PAL reference')
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
    dialog.setWindowTitle('JP retail research')
    dialog.resize(1200, 800)
    QVBoxLayout(dialog).addWidget(view(project, jump, area))
    dialog.show()
    return dialog
