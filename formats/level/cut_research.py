"""Retail evidence browser; live data is gated by the audited JP fingerprints."""
import hashlib
import json
import re
from pathlib import Path
import struct

REPORT = Path(__file__).resolve().parents[2] / 'docs' / 'cut-villages-jp-research.md'
UNUSED_REPORT = REPORT.parent / 'jp-retail-unused-research.md'
OVERVIEW = REPORT.parent / 'cut-content-overview.md'
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
                                QDialog, QMessageBox, QSpinBox)
    if not supported(project):
        # The research is still useful with another disc open, but its JP asset
        # links and decoded pictures must not silently point into another build.
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel('This research describes Japanese retail (SLPS-01144), except where another build is named. '
                      'Open that audited disc to see its pictures and jump to its files.')
        note.setWordWrap(True)
        layout.addWidget(note)
        chooser = QComboBox()
        for label, path in (('Explore cut content', OVERVIEW),
                            ('Detailed research: cut villages (JP retail)', REPORT),
                            ('Detailed research: other unused content (JP retail)', UNUSED_REPORT)):
            chooser.addItem(label, path)
        layout.addWidget(chooser)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser, 1)
        def show_report():
            try:
                content = chooser.currentData().read_text(encoding='utf8')
            except OSError as exc:
                content = f'Research document unavailable: {exc}'
            content = re.sub(r'!\[[^\]]*\]\(fig:[^)]+\)', '*Open Japanese retail to view this image.*', content)
            content = re.sub(r'\[([^\]]+)\]\(tomba://[^)]+\)', r'\1', content)
            browser.setMarkdown(content)
        chooser.currentIndexChanged.connect(show_report)
        show_report()
        return page
    widget = QWidget()
    layout = QVBoxLayout(widget)
    try:
        manifest = reference_manifest()
        sync = 'Findings and illustrations: Japanese retail (Ore! Tomba, SLPS-01144).'
    except (OSError,ValueError,KeyError,TypeError) as exc:
        manifest = None
        sync = f'Some reference documents are unavailable: {exc}'
    note = QLabel(sync + '\n'
                  'Explore surviving art, dialogue, animations and locations; research from other builds is labelled.')
    note.setWordWrap(True)
    layout.addWidget(note)
    tabs = QTabWidget()
    layout.addWidget(tabs, 1)
    article = QWidget()
    body = QVBoxLayout(article)
    documents = QComboBox()
    documents.addItem('Explore cut content', (OVERVIEW, None))
    documents.addItem('Detailed research: cut villages (JP retail)', (REPORT, None))
    documents.addItem('Detailed research: other unused content (JP retail)', (UNUSED_REPORT, None))
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
    text.setOpenLinks(False)       # every link goes through open_link: web pages, and the tomba:// links to the disc
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
    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtGui import QDesktopServices, QImage
    from formats.level import research_figures
    try:
        figures = research_figures.build(project)
    except Exception as exc:        # a picture that cannot be made must never stop the report from opening
        figures, note_text = [], f'Report pictures unavailable: {exc}'
        note.setText(note.text() + '\n' + note_text)
    by_key = {f.key: f for f in figures}
    playing = {}                      # key -> [frame, milliseconds left]
    STEP = 40

    def picture(image):
        image = image.convert('RGBA')
        return QImage(image.tobytes(), image.width, image.height, 4 * image.width, QImage.Format.Format_RGBA8888).copy()

    def show_frame(figure, number):
        text.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(f'fig:{figure.key}'),
                                    picture(figure.frames[number]))

    for figure in figures:
        show_frame(figure, 0)
        if figure.delays:
            playing[figure.key] = [0, figure.delays[0]]

    def animate():
        if not text.isVisible():
            return
        changed = False
        for key, state in playing.items():
            figure = by_key[key]
            state[1] -= STEP
            if state[1] <= 0:
                state[0] = (state[0] + 1) % len(figure.frames)
                state[1] = figure.delays[state[0]]
                show_frame(figure, state[0])
                changed = True
        if changed:
            text.document().markContentsDirty(0, text.document().characterCount())
            text.viewport().update()
    clock = QTimer(widget)
    clock.timeout.connect(animate)
    clock.start(STEP)

    def open_link(url):
        if url.scheme() != 'tomba':
            QDesktopServices.openUrl(url)
            return
        target = url.path().lstrip('/')
        if jump is None:
            return
        if url.host() == 'file':
            jump('file', target)
        elif url.host() == 'village' and target in ('11', '16', '17', '18'):
            jump('village', (f'SYS/LDAR{target}.BIN', 1))
        elif url.host() == 'asset' and target == 'chief-alt':
            from formats.level.scene import loaded_resources
            asset = loaded_resources(project, 'SYS/LDAR10.BIN', 1).get(('SPR', 7))
            if asset is not None:
                jump('asset', asset)
        elif url.host() == 'asset' and target in by_key and by_key[target].asset is not None:
            jump('asset', by_key[target].asset)
    text.anchorClicked.connect(open_link)

    def document_changed():
        path,url = documents.currentData()
        try:
            report = path.read_text(encoding='utf8')
        except OSError as exc:
            report = f'Document unavailable: {exc}'
        text.document().setBaseUrl(QUrl(url or ''))
        shown = report
        if path == OVERVIEW:
            shown = re.sub(r'!\[[^\]]*\]\(fig:([^)]+)\)',
                           lambda m: m.group(0) if m.group(1) in by_key else '*Image unavailable for this disc.*', shown)
            shown = re.sub(r'\[([^\]]+)\]\(tomba://asset/([^)]+)\)',
                           lambda m: m.group(0) if m.group(2) in by_key or m.group(2) == 'chief-alt' else m.group(1) + ' (unavailable)', shown)
            if not jump:
                shown = re.sub(r'\[([^\]]+)\]\(tomba://[^)]+\)', r'\1', shown)
        elif path.parent == REPORT.parent:
            shown = research_figures.decorate(report, path.name, figures, project if jump else None)
            if not jump:                                   # no tree to jump in: the pictures stay, the buttons go
                shown = re.sub(r'\s+—\s+\[[^\]]+\]\(tomba://asset/[^)]*\)', '', shown)
        text.setMarkdown(shown)
        # Loading a document clears its resources: put the pictures back, then lay the text out again with their sizes.
        for figure in figures:
            show_frame(figure, playing.get(figure.key, [0])[0])
        if figures:
            text.document().markContentsDirty(0, text.document().characterCount())
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
        documents.setCurrentIndex(2)
        index = next((i for i, heading in enumerate(headings) if heading.startswith('Masakari Chief —')), -1)
        if index >= 0:
            outline.setCurrentRow(index)
    chief.clicked.connect(show_chief)
    bar.addWidget(chief)
    if jump:
        from formats.level.scene import loaded_resources
        jungle = project.ldars.get('SYS/LDAR10.BIN', [])
        resources = loaded_resources(project, 'SYS/LDAR10.BIN', 1) if len(jungle) > 1 else {}
        chief_bank = resources.get(('SPR', 2))
        if chief_bank is not None:
            inspect_chief = QPushButton('Open Chief sprite bank')
            inspect_chief.setToolTip('Open the JP Jungle SPR slot 2 chief bank. Slot 7 also contains related chief frames; the intended runtime palette is unconfirmed.')
            inspect_chief.clicked.connect(lambda checked=False: jump('asset', chief_bank))
            bar.addWidget(inspect_chief)
            if ('SPR', 7) in resources:
                alternate = QPushButton('Open related SPR 7')
                alternate.setToolTip('Open the other Jungle bank containing matching chief texture rectangles.')
                alternate.clicked.connect(lambda checked=False: jump('asset', resources['SPR', 7]))
                bar.addWidget(alternate)
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
                    if (hashlib.sha1(bank).hexdigest() != 'c5139a5d72fd81abdda6f281007541cfaba05b10' or
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
                    explanation = QLabel('JP SPR 2 frames 0–13 use the chief texture. Choose a CLUT to explore the colours. '
                                         'The stored 780A row is only a starting point; the intended runtime palette is unknown.')
                    explanation.setWordWrap(True)
                    content.addWidget(explanation)
                    choices = QComboBox()
                    for frame in range(14):
                        choices.addItem(f'Frame {frame}', frame)
                    content.addWidget(choices)
                    palette = QSpinBox()
                    palette.setRange(0, 65535)
                    palette.setDisplayIntegerBase(16)
                    palette.setPrefix('CLUT 0x')
                    palette.setValue(0x780a)
                    palette.setToolTip('Any 16-colour VRAM row; changing this is exploratory and does not establish the original palette.')
                    content.addWidget(palette)
                    picture = ImageView()
                    picture.zoom.setCurrentIndex(0)
                    content.addWidget(picture, 1)
                    def update_preview():
                        frame = choices.currentData()
                        picture.export_name = f'JP Chief frame {frame} - CLUT {palette.value():04X}'
                        picture.set_image(render_sprite(frames[frame], vram, tpage=3, clut=palette.value()), subject='chief')
                    choices.currentIndexChanged.connect(update_preview)
                    palette.valueChanged.connect(update_preview)
                    update_preview()
                    dialog.show()
                except (KeyError, IndexError, StopIteration, ValueError, OSError) as exc:
                    QMessageBox.warning(widget, 'Chief preview unavailable', str(exc))
            preview_chief.clicked.connect(show_chief_preview)
            bar.addWidget(preview_chief)
    search.returnPressed.connect(find)
    next_button.clicked.connect(lambda: find(False))
    previous.clicked.connect(lambda: find(True))
    tabs.addTab(article, 'Explore discoveries')

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

    def area_of(value):
        found = re.search(r'AREA\s*(\d+)', value or '')
        return int(found.group(1)) if found else None

    def overlay_path(name):
        """The disc file of an overlay named in the reports ('X01'): the one in SYSTEM, else the first one found."""
        paths = sorted(p for p in project.disc.entries if p.endswith(f'/{name}.BIN'))
        return next((p for p in paths if p.startswith('SYSTEM/')), paths[0] if paths else None)

    def activate(grid, resolve):
        """Double-clicking a row opens what it names: `resolve` gets the row's cells by header and returns the
        arguments of `jump` (or None when the row names nothing that can be opened)."""
        grid.setToolTip('Double-click a row to open it in the editor.' if jump else '')
        def opened(row, column):
            if jump is None:
                return
            cells = {}
            for c in range(grid.columnCount()):
                header, item = grid.horizontalHeaderItem(c), grid.item(row, c)
                cells[header.text() if header else str(c)] = item.text() if item else ''
            try:
                target = resolve(cells)
            except (KeyError, ValueError, IndexError):
                target = None
            if target:
                jump(*target)
        grid.cellDoubleClicked.connect(opened)
        return grid

    def town_plan(cells):
        number = area_of(cells.get('Town'))
        return ('village', (f'SYS/LDAR{number:02d}.BIN', 1)) if number in (11, 16, 17, 18) else None

    def town_palette(cells):
        number = area_of(cells.get('Town'))
        path = f'AREA{number:02d}/{cells.get("File", "")}.GAM' if number else ''
        if path in project.disc.entries:
            return ('file', path)
        return town_plan(cells)

    def event_place(cells):
        place = cells.get('Location', '')
        number = area_of(place)
        section = re.search(r'section\s*(\d+)', place)
        if number is not None and f'SYS/LDAR{number:02d}.BIN' in project.ldars:
            return ('section', (f'SYS/LDAR{number:02d}.BIN', int(section.group(1)) + 1 if section else 0))
        return ('file', 'SYSTEM/DSPSUB.BIN')

    def finding_place(cells):
        place = cells.get('JP location', '')
        if place.startswith('MAIN'):
            return ('file', 'SLPS_011.44')
        overlay = re.match(r'(X\d\d)', place)
        path = overlay_path(overlay.group(1)) if overlay else None
        return ('file', path) if path else None

    def plaque_place(cells):
        number = area_of(cells.get('Reported area / texture'))
        return ('section', (f'SYS/LDAR{number:02d}.BIN', 0)) if number is not None else None

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
            activate(shown, town_palette if title == 'Palettes' else town_plan)
            reference_tabs.addTab(shown, title)
    tabs.addTab(reference, 'Community palettes, residents and props')

    try:
        decoded = animations(project)
        rows = [(i, f'{address:08X}', ', '.join(str(s[0]) for s in steps),
                 ', '.join(str(s[1]) for s in steps), 'Hold final frame (8000)')
                for i, address, steps in decoded]
        tabs.addTab(activate(table(['Script', 'JP address', 'Frames', 'Update ticks', 'End control'], rows),
                             lambda cells: ('file', 'SLPS_011.44')),     # the 24 scripts are resident in MAIN
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
    tabs.addTab(activate(table(['Iron Town mechanism', 'World trigger x, y (inclusive)', 'Behavior', 'JP source address'], rows),
                         lambda cells: ('village', ('SYS/LDAR17.BIN', 1))),
                'Iron Town · lifts and passages · audited JP')
    rocks = QWidget()
    rocks_layout = QVBoxLayout(rocks)
    rock_note = QLabel('Doodle Rock research from Tombi-Decomp. Two plaques have documented retail placements; '
                       'the other texture finds and their intended puzzle are research evidence. '
                       'The JP text buttons open the complete original entries.')
    rock_note.setWordWrap(True)
    rocks_layout.addWidget(rock_note)
    rocks_layout.addWidget(activate(table(['Plaque value', 'Reported area / texture', 'Retail placement'], [
        ('2', 'AREA01 / AREA07 forest', 'Placed as a decorative model'),
        ('5', 'AREA04 / AREA12 Haunted Mansion', 'Placed as a decorative model'),
        ('18', 'AREA03 mountain / caves', 'Texture found; placement not identified'),
        ('139', 'AREA10 jungle', 'Texture found; placement not identified'),
        ('59', 'AREA11; also JP AREA10 room pages', 'Texture found; placement not identified'),
    ]), plaque_place))
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
    tabs.addTab(rocks, 'Doodle Rocks · research')
    recent = QWidget()
    recent_layout = QVBoxLayout(recent)
    recent_note = QLabel('More surviving code and graphics in Japanese retail. '
                         'Double-click a row to inspect its source; unreferenced code is not proof against every possible caller.')
    recent_note.setWordWrap(True)
    recent_layout.addWidget(recent_note)
    recent_layout.addWidget(activate(table(['Finding', 'JP location', 'Research result'], [
        ('Flower Tower gate', 'X01 80116238', 'Million-AP threshold; tower interior is AREA13 section 0'),
        ('Caterpillar patrol', 'X01 80131DB8', 'Older one-way route; no identified retail caller'),
        ('Flower Tears seeker', 'X09 80127CD4', 'Unreferenced walk-off routine'),
        ('Seven Friends', 'X02 801182E4', 'Unreferenced fly-up exit routine'),
        ('Debug font', 'MAIN 80021E5C', '8 × 8 font used by JP ending and game-over text'),
    ]), finding_place))
    if jump:
        system = project.ldars.get('SYS/LDSYS.BIN', [])
        font = next((a for a in (system[0].assets if system else ())
                     if a.source and a.source.path == 'SYSTEM/A00000.GAM'), None)
        if font is not None:
            button = QPushButton('Open system font texture')
            button.setToolTip('The 8 × 8 debug font is on the resident system texture; palette rows begin at VRAM (368, 496).')
            button.clicked.connect(lambda checked=False: jump('asset', font))
            recent_layout.addWidget(button)
    tabs.addTab(recent, 'More discoveries · JP')
    if manifest and any(item['path'] == 'docs/EVENTS_MAP.md' for item in manifest['files']):
        event_page = QWidget()
        event_layout = QVBoxLayout(event_page)
        event_note = QLabel('PAL retail event-location research, including script and shared-overlay references. '
                            'These are PAL leads; they do not link to Japanese locations without verification.')
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
        documents.setCurrentIndex(1)
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
    dialog.setWindowTitle('Cut Content Research')
    dialog.resize(1200, 800)
    QVBoxLayout(dialog).addWidget(view(project, jump, area))
    dialog.show()
    return dialog
