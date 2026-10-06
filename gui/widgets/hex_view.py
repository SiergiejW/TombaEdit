"""Hex view with an adjustable row width and coloured, explained byte ranges.

The table is a model over the bytes, so a megabyte costs no more to open
than a kilobyte. Regions come from formats/annotate.py: each is painted in
the colour of its group, described in the line under the table when a byte
in it is selected, and listed on the right for jumping to.
"""
from gui.console import announce
from bisect import bisect_right
import struct
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QEvent
from PyQt6.QtGui import QColor, QFontDatabase
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QTableView,
    QAbstractItemView, QHeaderView, QSplitter, QTableWidget, QTableWidgetItem, QLineEdit)

# Group colours, chosen to stay readable under light or dark text.
GROUP_COLOURS = {
    'count': (214, 120, 60), 'pointer': (70, 130, 210), 'uv': (60, 160, 150), 'clut': (190, 90, 170),
    'page': (150, 110, 220), 'size': (120, 150, 70), 'position': (200, 160, 50), 'colour': (200, 80, 90),
    'code': (70, 110, 90), 'code2': (60, 90, 120), 'padding': (90, 90, 90),
}
GROUP_NAMES = {
    'count': 'counts', 'pointer': 'offsets and addresses', 'uv': 'texture coordinates, flags, animation steps',
    'clut': 'palettes, tags, text', 'page': 'texture pages, layers', 'size': 'sizes', 'position': 'positions',
    'colour': 'colours, pixels', 'code': 'functions', 'code2': 'functions', 'padding': 'padding',
}
MAX_LISTED = 5000


class DragValue(QSpinBox):
    """A number that is typed like any other, or dragged: hold the left
    button on it and move sideways."""
    PIXELS_PER_STEP = 6

    def __init__(self, low, high, value):
        super().__init__()
        self.setRange(low, high)
        self.setValue(value)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.setKeyboardTracking(False)
        self.setToolTip('Drag left or right, or type a value.')
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.lineEdit().setCursor(Qt.CursorShape.SizeHorCursor)
        self.lineEdit().installEventFilter(self)
        self.press = None       # (x, value) while the button is down
        self.dragged = False

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.press, self.dragged = (event.globalPosition().x(), self.value()), False
        elif kind == QEvent.Type.MouseMove and self.press is not None:
            delta = event.globalPosition().x() - self.press[0]
            if self.dragged or abs(delta) >= self.PIXELS_PER_STEP:
                self.dragged = True
                self.setValue(self.press[1] + int(delta / self.PIXELS_PER_STEP))
                return True     # no text selection while dragging
        elif kind == QEvent.Type.MouseButtonRelease and self.press is not None:
            dragged, self.press = self.dragged, None
            if dragged:
                self.lineEdit().deselect()
                return True
        return super().eventFilter(watched, event)


class HexModel(QAbstractTableModel):
    def __init__(self, data, regions, base=0, columns=16):
        super().__init__()
        self.bytes, self.regions, self.base, self.columns = data, regions, base, columns
        self.starts = [region.start for region in regions]
        self.brushes = {group: QColor(*rgb, 150) for group, rgb in GROUP_COLOURS.items()}

    def set_columns(self, columns):
        self.beginResetModel()
        self.columns = columns
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return (len(self.bytes) + self.columns - 1) // self.columns

    def columnCount(self, parent=QModelIndex()):
        return self.columns + 1

    def region_at(self, offset):
        i = bisect_right(self.starts, offset) - 1
        if i >= 0 and self.regions[i].start <= offset < self.regions[i].end:
            return self.regions[i]
        return None

    def offset(self, index):
        offset = index.row() * self.columns + index.column()
        return offset if index.column() < self.columns and offset < len(self.bytes) else None

    def headerData(self, section, orientation, role):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return f'{self.base + section * self.columns:06X}'
        return f'{section:02X}' if section < self.columns else 'Text'

    def data(self, index, role):
        if index.column() == self.columns:
            if role == Qt.ItemDataRole.DisplayRole:
                start = index.row() * self.columns
                return ''.join(chr(c) if 32 <= c < 127 else '.' for c in self.bytes[start:start + self.columns])
            return None
        offset = self.offset(index)
        if offset is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return f'{self.bytes[offset]:02X}'
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role in (Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ToolTipRole):
            region = self.region_at(offset)
            if region is None:
                return None
            if role == Qt.ItemDataRole.BackgroundRole:
                return self.brushes.get(region.group)
            return f'{region.name}\n{region.detail}'.strip()
        return None


class HexView(QWidget):
    def __init__(self, data, regions=(), base=0, note=''):
        super().__init__()
        self.model = HexModel(data, list(regions), base)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel('Bytes per row:'))
        self.width_box = DragValue(1, 64, 16)
        self.width_box.valueChanged.connect(self.set_columns)
        bar.addWidget(self.width_box)
        bar.addWidget(QLabel('Go to offset:'))
        self.goto_box = QLineEdit()
        self.goto_box.setPlaceholderText('hex')
        self.goto_box.setMaximumWidth(90)
        self.goto_box.returnPressed.connect(self.goto_typed)
        bar.addWidget(self.goto_box)
        summary = f'{len(data):,} bytes'
        if regions:
            covered = sum(region.end - region.start for region in regions)
            summary += f' | {len(regions):,} described ranges covering {covered * 100 // max(1, len(data))}%'
        if note:
            summary += ' | ' + note
        label = QLabel(summary)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bar.addWidget(label)
        bar.addStretch()
        layout.addLayout(bar)
        if regions:
            legend = QHBoxLayout()
            shown = set()
            for region in regions:
                name = GROUP_NAMES.get(region.group, region.group)
                if name in shown:
                    continue
                shown.add(name)
                chip = QLabel(f' {name} ')
                r, g, b = GROUP_COLOURS.get(region.group, (90, 90, 90))
                chip.setStyleSheet(f'background-color: rgba({r}, {g}, {b}, 150); border-radius: 3px;')
                legend.addWidget(chip)
            legend.addStretch()
            layout.addLayout(legend)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setMinimumSectionSize(10)
        self.table.selectionModel().currentChanged.connect(self.describe)
        split = QSplitter()
        split.addWidget(self.table)
        self.listed = list(regions)[:MAX_LISTED]
        if regions:
            self.list = QTableWidget(len(self.listed), 3)
            self.list.setHorizontalHeaderLabels(['Offset', 'Bytes', 'Contents'])
            self.list.verticalHeader().hide()
            self.list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.list.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            for row, region in enumerate(self.listed):
                for column, value in enumerate((f'{base + region.start:06X}', str(region.end - region.start), region.name)):
                    self.list.setItem(row, column, QTableWidgetItem(value))
            self.list.setColumnWidth(0, 70)
            self.list.setColumnWidth(1, 56)
            self.list.currentCellChanged.connect(lambda row, *_: self.goto(self.listed[row].start) if row >= 0 else None)
            split.addWidget(self.list)
            split.setSizes([760, 360])
        layout.addWidget(split, 1)
        self.info = QLabel('Select a byte to see what it belongs to.')
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info)
        self.size_columns()

    def size_columns(self):
        metrics = self.table.fontMetrics()
        cell = metrics.horizontalAdvance('00') + 10
        for column in range(self.model.columns):
            self.table.setColumnWidth(column, cell)
        self.table.setColumnWidth(self.model.columns, metrics.horizontalAdvance('W' * self.model.columns) + 16)

    def set_columns(self, columns):
        """Re-flow the bytes, keeping the selected one selected and in view."""
        current = self.model.offset(self.table.currentIndex()) if self.table.currentIndex().isValid() else None
        first = self.table.rowAt(0) * self.model.columns if self.table.rowAt(0) >= 0 else 0
        self.model.set_columns(columns)
        self.size_columns()
        self.goto(current if current is not None else first, select=current is not None)

    def goto(self, offset, select=True):
        offset = max(0, min(len(self.model.bytes) - 1, offset))
        index = self.model.index(offset // self.model.columns, offset % self.model.columns)
        if select:
            self.table.setCurrentIndex(index)
        self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter if select
                            else QAbstractItemView.ScrollHint.PositionAtTop)

    def goto_typed(self):
        try:
            self.goto(int(self.goto_box.text(), 16) - self.model.base)
        except ValueError:
            self.info.setText(f'"{self.goto_box.text()}" is not a hexadecimal offset')

    def describe(self, index, previous=None):
        offset = self.model.offset(index)
        if offset is None:
            return
        data = self.model.bytes
        text = f'Offset 0x{self.model.base + offset:X} | byte {data[offset]}'
        if offset + 2 <= len(data):
            word = struct.unpack_from('<H', data, offset)[0]
            text += f' | 16-bit {word} (0x{word:04X}), signed {struct.unpack_from("<h", data, offset)[0]}'
        if offset + 4 <= len(data):
            text += f' | 32-bit 0x{struct.unpack_from("<I", data, offset)[0]:08X}'
        region = self.model.region_at(offset)
        if region is not None:
            text += (f'\n{region.name} (0x{self.model.base + region.start:X}, {region.end - region.start} bytes)'
                     + (f': {region.detail}' if region.detail else ''))
            announce(f'byte 0x{self.model.base + offset:X} | {region.name}'
                  + (f' | {region.detail}' if region.detail else ''))
        self.info.setText(text)
