"""Read-only APD placements and WHM word explorer."""
import struct
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSplitter)


class PlacementMap(QWidget):
    def __init__(self, records):
        super().__init__()
        self.records = records
        self.selected = -1
        self.setMinimumSize(280, 260)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#202020'))
        if not self.records:
            return
        xs = [r[6] for r in self.records]
        ys = [r[7] for r in self.records]
        low_x, high_x = min(xs), max(xs)
        low_y, high_y = min(ys), max(ys)
        for i, record in enumerate(self.records):
            x = 12 + (record[6] - low_x) / max(1, high_x - low_x) * (self.width() - 24)
            y = 12 + (record[7] - low_y) / max(1, high_y - low_y) * (self.height() - 24)
            painter.setPen(QPen(QColor('#ff6060' if i == self.selected else '#a7c653'),
                                5 if i == self.selected else 2))
            painter.drawPoint(round(x), round(y))
        painter.setPen(QColor('#dddddd'))
        painter.drawText(10, self.height() - 6, f'X {low_x}..{high_x} | Y {low_y}..{high_y}')


class StructuredView(QWidget):
    def __init__(self, data, kind):
        super().__init__()
        self.kind = kind
        self.records = []
        layout = QVBoxLayout(self)
        if kind == 'APD':
            self.records = [struct.unpack_from('<6B3h2H', data, at)
                            for at in range(0, len(data) - 15, 16)]
            layout.addWidget(QLabel(f'{len(self.records)} placement records | 16 bytes each | X/Y map'))
            self.table = QTableWidget(len(self.records), 12)
            self.table.setHorizontalHeaderLabels(['#', 'Offset', 'ID 0', 'ID 1', 'ID 2',
                'ID 3', 'ID 4', 'ID 5', 'X', 'Y', 'Z', 'Flags'])
            for i, record in enumerate(self.records):
                values = [str(i), f'0x{i * 16:04X}'] + [f'{v:02X}' for v in record[:6]] + [
                    str(v) for v in record[6:9]] + [f'{record[9]:04X} {record[10]:04X}']
                for column, value in enumerate(values):
                    self.table.setItem(i, column, QTableWidgetItem(value))
            self.map = PlacementMap(self.records)
            split = QSplitter()
            split.addWidget(self.table); split.addWidget(self.map)
            split.setSizes([720, 340])
            layout.addWidget(split)
            self.table.currentCellChanged.connect(self.select)
        else:
            header = ' '.join(f'{v:04X}' for v in struct.unpack_from('<6H', data, 0)) if len(data) >= 12 else ''
            label = QLabel(f'WHM collision data | {len(data):,} bytes | Header words: {header}\n'
                           'Raw little-endian words. The Collision planes tab decodes the boundaries and attributes.')
            label.setWordWrap(True)
            layout.addWidget(label)
            count = (len(data) + 15) // 16
            self.table = QTableWidget(count, 3)
            self.table.setHorizontalHeaderLabels(['Offset', 'Unsigned words', 'Signed words'])
            for row in range(count):
                block = data[row * 16:(row + 1) * 16]
                words = struct.unpack(f'<{len(block) // 2}H', block[:len(block) // 2 * 2])
                signed = [v if v < 0x8000 else v - 0x10000 for v in words]
                for col, value in enumerate((f'0x{row * 16:06X}',
                        ' '.join(f'{v:04X}' for v in words),
                        ' '.join(str(v) for v in signed))):
                    self.table.setItem(row, col, QTableWidgetItem(value))
            layout.addWidget(self.table)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def select(self, row, column, old_row, old_column):
        self.map.selected = row
        self.map.update()
