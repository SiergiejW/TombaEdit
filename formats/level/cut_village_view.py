"""The plan of a cut top-down village, with what each resident says.

Section 0 of AREA11, AREA16 and AREA17 has an empty load list, so the level view
shows nothing for it. Its residents, props and houses survive in the INFO2
overlay (formats.level.cut_towns); this draws them as a plan and lists each
resident with the messages its dialogue routine can open.

The plan is drawn from the data alone. The village's background picture, its
collision map and the sprite tables that say which drawing each subtype is were
not kept on the disc, so the figures are marks and not art.
"""
from dataclasses import dataclass, field
from PIL import Image, ImageDraw, ImageFont

from formats.level.cut_towns import CUT, VILLAGES, WINDOWS, dialogue_cases, villages

SCALE = 2
MARGIN = 40
AREA_SETS = {area: number for number, (area, *_rest) in VILLAGES.items() if number in CUT}


@dataclass
class Row:
    number: int
    subtype: int
    where: str
    behaviour: str
    case: int
    messages: list = field(default_factory=list)    # [(entry index, text)]; entry None: not on this disc
    note: str = ''


@dataclass
class Preview:
    name: str
    area: int
    image: object
    rows: list
    notes: list


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def patrol_box(village, r):
    """The box a resident walks in as world positions, or None for one that stands still."""
    x0, y0, x1, y1 = r.box
    if not r.behaviour or (x0, y0, x1, y1) == (0, 0, 0, 0):
        return None
    if village.set_number == 0x0E:      # Stonetown keeps its boxes relative to the resident
        return r.x + x0, r.y + y0, r.x + x1, r.y + y1
    return x0, y0, x1, y1


def draw_plan(village):
    """The plan of a village as an image: houses, patrol boxes, props and numbered residents."""
    boxes = [b for b in (patrol_box(village, r) for r in village.residents) if b]
    xs = ([r.x for r in village.residents] + [p.x for p in village.props] + [h[i] for h in village.houses for i in (0, 2)]
          + [b[i] for b in boxes for i in (0, 2)])
    ys = ([r.y for r in village.residents] + [p.y for p in village.props] + [h[i] for h in village.houses for i in (1, 3)]
          + [b[i] for b in boxes for i in (1, 3)])
    left, top = min(xs) - MARGIN, min(ys) - MARGIN
    width, height = (max(xs) + MARGIN - left) * SCALE, (max(ys) + MARGIN - top) * SCALE

    def at(x, y):
        return (x - left) * SCALE, (y - top) * SCALE
    image = Image.new('RGBA', (width, height), (226, 222, 210, 255))
    draw = ImageDraw.Draw(image)
    for gx in range(int(left) // 64 * 64, int(left + width / SCALE) + 64, 64):
        draw.line([at(gx, top), at(gx, top + height / SCALE)], fill=(214, 210, 198, 255))
    for gy in range(int(top) // 64 * 64, int(top + height / SCALE) + 64, 64):
        draw.line([at(left, gy), at(left + width / SCALE, gy)], fill=(214, 210, 198, 255))
    label, small = _font(13), _font(11)
    for n, (x0, y0, x1, y1) in enumerate(village.houses, 1):
        draw.rectangle([at(x0, y0), at(x1, y1)], outline=(40, 110, 230, 255), width=2)
        draw.text((at(x0, y0)[0] + 4, at(x0, y0)[1] + 3), f'H{n}', fill=(40, 110, 230, 255), font=label)
    for box in boxes:
        draw.rectangle([at(box[0], box[1]), at(box[2], box[3])], outline=(30, 160, 60, 255), width=2)
    for p in village.props:
        px, py = at(p.x, p.y)
        draw.rectangle([px - 4, py - 4, px + 4, py + 4], fill=(240, 190, 30, 255), outline=(120, 90, 0, 255))
    for r in village.residents:
        px, py = at(r.x, r.y)
        colour = (150, 40, 190, 255) if r.room else (210, 30, 30, 255)
        draw.line([(px, py), (px, py - 22)], fill=colour, width=2)
        draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=colour)
        draw.ellipse([px - 10, py - 34, px + 10, py - 14], fill=colour, outline=(255, 255, 255, 255))
        text = str(r.index + 1)
        box = draw.textbbox((0, 0), text, font=small)
        draw.text((px - (box[2] - box[0]) / 2 - box[0], py - 24 - (box[3] - box[1]) / 2 - box[1] - 0), text, fill=(255, 255, 255, 255), font=small)
    return image


def _overlay(project):
    for groups in project.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind == 'INS' and asset.source and 'NFO2' in asset.source.path.upper():
                    return project.asset_data(asset)
    return None


def _bank(project, path):
    from formats.text.wfm import Wfm
    for asset in project.ldars[path][0].assets:
        if asset.kind == 'WFM' and asset.code >> 8 == 0xD0:
            try:
                return Wfm(project.asset_data(asset))
            except Exception:
                return None
    return None


def _village(project, path, index):
    """(executable, overlay, village) for the empty section a load-table group stands for, or None."""
    from formats.level.scene import area_of
    area = area_of(path)
    if index != 1 or area not in AREA_SETS or project.ldars[path][1].assets:
        return None
    from game.builds import executable
    found = executable(project)
    data = _overlay(project)
    if found is None or data is None:
        return None
    village = villages(data, found.build.overlay).get(AREA_SETS[area])
    return None if village is None else (found, data, village)


def available(project, path, index):
    """Whether the group is an empty section whose village survives in the overlay (no plan is drawn)."""
    return _village(project, path, index) is not None


def preview(project, path, index):
    """The Preview of the empty section a load-table group stands for, or None for any other group."""
    from formats.text import export
    located = _village(project, path, index)
    if located is None:
        return None
    found, data, village = located
    area = next(a for a, n in AREA_SETS.items() if n == village.set_number)
    notes = ["The village's background picture, collision map and the tables that say which drawing each resident "
             'subtype is are not on the disc, so this is a plan of marks and not the village as it looked.']
    cases = bank = None
    windows = WINDOWS.get(found.build.name)
    if windows:
        cases = dialogue_cases(data, found.build.overlay, lambda a: found.word(a) if found.holds(a, 4) else None, windows).get(village.set_number)
        bank = _bank(project, path)
        if cases is None or bank is None:
            notes.append('The dialogue routine of this village was not found in the overlay, so the lines are not shown.')
    else:
        notes.append('The dialogue routines of this build are not mapped, so only each resident\'s case number is shown.')
    rows = []
    for r in village.residents:
        row = Row(r.index + 1, r.subtype, 'outdoors' if not r.room else f'inside house {r.room}' if r.room != 255 else 'special',
                  r.behaviour_name, r.dialogue)
        if cases is not None and bank is not None:
            pairs = cases.get(r.dialogue)
            if pairs is None:
                row.note = 'no message: the routine has no such case'
            elif not pairs:
                row.note = 'no message in the code (it sets a flag or does nothing)'
            for g, l in pairs or ():
                entry = (bank.groups[g] if g < len(bank.groups) else 0) + l
                if entry < len(bank.dialogues):
                    row.messages.append((entry, export.plain(bank.dialogues[entry]).replace('\n', ' ')))
                else:
                    row.messages.append((None, f'(group {g}, line {l}: the line is not in this disc\'s text)'))
        rows.append(row)
    if village.cut:
        notes.insert(0, f'{village.name} (AREA{area:02d} section 0) is never loaded: its load list is empty and no exit leads into it.')
    return Preview(village.name, area, draw_plan(village), rows, notes)


def view(preview, english=None, request=None, changed=None):
    """The widget for a Preview. `english(text)` gives a translation of a line, or None.

    Selecting a row calls `request(texts)` with that row's lines so they are translated first;
    `changed` is a signal that fires when a translation may have arrived.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView
    from gui.widgets.image_view import ImageView
    widget = QWidget()
    layout = QVBoxLayout(widget)
    note = QLabel(' '.join(preview.notes))
    note.setWordWrap(True)
    layout.addWidget(note)
    split = QSplitter(Qt.Orientation.Horizontal)
    picture = ImageView()
    picture.zoom.setCurrentIndex(0)     # Fit: the plan is larger than its pane at 200%
    picture.set_image(preview.image)
    split.addWidget(picture)
    headers = ['#', 'Where', 'Behaviour', 'Drawing', 'Case', 'Says (Japanese)'] + (['English'] if english else [])
    table = QTableWidget(len(preview.rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    def lines(row):
        return [text for entry, text in row.messages if entry is not None]

    def translated(row):
        found = [english(text) for text in lines(row)]
        return ' / '.join(line for line in found if line)

    def show_english():
        column = len(headers) - 1
        for r, row in enumerate(preview.rows):
            text = translated(row)
            item = table.item(r, column)
            if item is not None and item.text() != text:
                item.setText(text)
                item.setToolTip(text)

    for r, row in enumerate(preview.rows):
        says = ' / '.join(text if entry is None else f'#{entry}: {text}' for entry, text in row.messages) or row.note
        cells = [str(row.number), row.where, row.behaviour, str(row.subtype), str(row.case), says]
        if english:
            cells.append(translated(row))
        for c, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.setColumnWidth(5, min(table.columnWidth(5), 300))     # the Japanese is the shorter column
    if english:
        table.setColumnWidth(6, 560)
        table.horizontalHeader().setStretchLastSection(True)
    if english and changed is not None:
        def refresh():
            try:
                show_english()
            except RuntimeError:        # the tab was closed
                changed.disconnect(refresh)
        changed.connect(refresh)
    if request is not None:
        def selected():
            # The selected rows' lines first, then the rest of the village's.
            rows = sorted({i.row() for i in table.selectedIndexes()})
            request([text for r in rows for text in lines(preview.rows[r])]
                    + [text for row in preview.rows for text in lines(row)])
        table.itemSelectionChanged.connect(selected)
        selected()      # opening the tab already queues every line of the village
    split.addWidget(table)
    split.setSizes([480, 900])
    layout.addWidget(split, 1)
    layout.addWidget(QLabel('Red: resident outdoors. Purple: resident inside a house. Blue: house. '
                            'Green: where a patrolling resident walks. Yellow: prop. Numbers are the rows of the table.'))
    return widget
