"""Read-only views for indexed and less documented LDAR data."""
import struct
import colorsys
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QAbstractTableModel
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QSplitter,
    QTableView, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QComboBox)
from gui.widgets.image_view import ImageView, text_view


class HexRows(QAbstractTableModel):
    def __init__(self, data, base=0):
        super().__init__()
        self.data_bytes, self.base = data, base

    def rowCount(self, parent=None):
        return (len(self.data_bytes) + 15) // 16

    def columnCount(self, parent=None):
        return 4

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ('Offset', 'Bytes', 'Words (LE)', 'ASCII')[section]
        return None

    def data(self, index, role):
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        start = index.row() * 16
        chunk = self.data_bytes[start:start + 16]
        if index.column() == 0:
            return f'0x{self.base + start:06X}'
        if index.column() == 1:
            return chunk.hex(' ').upper()
        if index.column() == 2:
            return ' '.join(f'{v:04X}' for v in struct.unpack(
                f'<{len(chunk) // 2}H', chunk[:len(chunk) // 2 * 2]))
        return ''.join(chr(value) if 32 <= value < 127 else '.' for value in chunk)


def offset_entries(data):
    if len(data) < 12:
        return []
    count = struct.unpack_from('<I', data)[0]
    if not 0 < count <= 10000 or 4 + count * 4 > len(data):
        return []
    offsets = struct.unpack_from(f'<{count}I', data, 4)
    if offsets[0] < 4 + count * 4 or offsets[-1] > len(data):
        return []
    offsets += (len(data),)
    if any(a > b for a, b in zip(offsets, offsets[1:])):
        return []
    return list(zip(offsets, offsets[1:]))


class DataView(QWidget):
    def __init__(self, data, kind, code=0, ram=0):
        super().__init__()
        self.blob = data
        layout = QVBoxLayout(self)
        self.summary = QLabel(f'{kind} {code:04X} | {len(data):,} bytes | RAM 0x{ram:08X}')
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        split = QSplitter()
        self.entries = offset_entries(data) if kind in ('WPP', 'FOUR') else []
        if self.entries:
            table = QTableWidget(len(self.entries), 3)
            table.setHorizontalHeaderLabels(['Entry', 'Offset', 'Bytes'])
            table.verticalHeader().hide()
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for i, (start, end) in enumerate(self.entries):
                for col, value in enumerate((str(i), f'0x{start:06X}', f'{end - start:,}')):
                    table.setItem(i, col, QTableWidgetItem(value))
            table.currentCellChanged.connect(self.select_entry)
            split.addWidget(table)
            self.entry_table = table
        self.raw = QTableView()
        self.raw.setModel(HexRows(data))
        self.raw.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.raw.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.raw.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.raw.setColumnWidth(0, 90)
        self.raw.setColumnWidth(2, 300)
        self.raw.setColumnWidth(3, 145)
        split.addWidget(self.raw)
        if self.entries:
            split.setSizes([260, 900])
        layout.addWidget(split)
        if kind == 'INS':
            self.summary.setText(self.summary.text() + ' | MIPS words shown in little-endian order')
        elif kind == 'WPP':
            self.summary.setText(self.summary.text() + f' | {len(self.entries)} indexed records')

    def select_entry(self, row, column, old_row, old_column):
        if row < 0 or row >= len(self.entries):
            return
        start, end = self.entries[row]
        self.raw.setModel(HexRows(self.blob[start:end], start))


class CollisionMapView(QWidget):
    def __init__(self, data, code=0):
        super().__init__()
        layout = QVBoxLayout(self)
        width, height = struct.unpack_from('<HH', data) if len(data) >= 4 else (0, 0)
        if data[:4] == b'\x10\0\0\0':
            # Slot 15 of a town section: the pre-rendered picture, as a TIM.
            from formats.sprites.wpp import parse_tim
            from disc.reader import FormatError
            try:
                tim = parse_tim(data)
                image = np.asarray(tim.image(tim.cluts.reshape(-1) if tim.cluts is not None else None)).copy()
                image[..., 3] = 255
                layout.addWidget(QLabel(f'CLM {code:04X} | town picture, {tim.width} x {tim.height}, '
                                        f'{"8" if tim.indices.max(initial=0) > 15 else "4"}-bit TIM'))
                view = ImageView(Image.fromarray(image))
                view.zoom.setCurrentIndex(0)
                layout.addWidget(view)
                return
            except FormatError:
                pass
        # The cell map sits in slot 14 from the 1998 builds on, and in a
        # placement slot before that; either way it starts with its size.
        dimensioned = 0 < width <= 512 and 0 < height <= 512 and 4 + width * height <= len(data)
        if dimensioned:
            size = width * height
            # Rows follow the two size words directly; the rest of the
            # buffer is unused.
            start = 4
            if start + size <= len(data):
                pixels = np.frombuffer(data[start:start + size], dtype=np.uint8).reshape(height, width)
                self.pixels = pixels
                layout.addWidget(QLabel(f'CLM {code:04X} | {width} x {height} cells of 8 x 8 pixels'))
                self.mode = QComboBox()
                self.mode.addItems(['Distinct values', 'Grayscale values'])
                self.mode.currentIndexChanged.connect(self.refresh)
                layout.addWidget(self.mode)
                self.view = ImageView()
                self.view.zoom.setCurrentIndex(2)
                layout.addWidget(self.view)
                self.selected = QLabel('Click a cell for its raw value.')
                self.selected.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(self.selected)
                self.view.canvas.clicked.connect(self.select)
                self.refresh()
                return
        layout.addWidget(QLabel(f'CLM {code:04X} | layout not confirmed; inspect raw words'))
        raw = QTableView()
        raw.setModel(HexRows(data))
        raw.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(raw)

    def refresh(self):
        if self.mode.currentIndex() == 1:
            rgb = np.repeat(self.pixels[:, :, None], 3, axis=2)
        else:
            palette = np.zeros((256, 3), dtype=np.uint8)
            for value in range(1, 256):
                red, green, blue = colorsys.hsv_to_rgb((value * 0.61803398875) % 1,
                                                       0.65, 0.85)
                palette[value] = (round(red * 255), round(green * 255), round(blue * 255))
            rgb = palette[self.pixels]
        self.view.set_image(Image.fromarray(rgb, 'RGB').convert('RGBA'))

    def select(self, x, y):
        self.selected.setText(f'Cell ({x}, {y}) | value {int(self.pixels[y, x])} '
                              f'| 0x{int(self.pixels[y, x]):02X}')
        print('selected: CLM ' + self.selected.text())
