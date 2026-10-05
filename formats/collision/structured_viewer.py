"""Read-only APD placements and WHM word explorer."""
import struct
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSplitter, QSizePolicy)


class PlacementMap(QWidget):
    picked = pyqtSignal(int)
    def __init__(self, records):
        super().__init__()
        self.records = records
        self.selected = -1
        self.setMinimumSize(280, 260)

    def points(self):
        if not self.records:
            return []
        xs, ys = [r[6] for r in self.records], [r[7] for r in self.records]
        scale = min((self.width() - 48) / max(1, max(xs) - min(xs)),
                    (self.height() - 48) / max(1, max(ys) - min(ys)))
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        return [(self.width() / 2 + (r[6] - cx) * scale,
                 self.height() / 2 + (r[7] - cy) * scale) for r in self.records]

    def mousePressEvent(self, event):
        points = self.points()
        if points:
            pos = event.position()
            row = min(range(len(points)), key=lambda i: (points[i][0] - pos.x()) ** 2 +
                                                       (points[i][1] - pos.y()) ** 2)
            if (points[row][0] - pos.x()) ** 2 + (points[row][1] - pos.y()) ** 2 <= 225:
                self.picked.emit(row)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#202020'))
        if not self.records:
            return
        xs = [r[6] for r in self.records]
        ys = [r[7] for r in self.records]
        low_x, high_x = min(xs), max(xs)
        low_y, high_y = min(ys), max(ys)
        for i, (x, y) in enumerate(self.points()):
            painter.setPen(QPen(QColor('#ff6060' if i == self.selected else '#a7c653'),
                                5 if i == self.selected else 2))
            painter.drawEllipse(round(x) - 3, round(y) - 3, 6, 6)
            if i == self.selected:
                painter.drawText(round(x) + 7, round(y) - 5, f'#{i:03d}')
        painter.setPen(QColor('#dddddd'))
        painter.drawText(10, self.height() - 6, f'X {low_x}..{high_x} | Y {low_y}..{high_y}')


class StructuredView(QWidget):
    def __init__(self, data, kind):
        super().__init__()
        self.kind = kind
        self.records = []
        layout = QVBoxLayout(self)
        if kind == 'APD':
            from formats.level.apd import parse_apd
            self.placements = parse_apd(data)
            self.records = [struct.unpack('<6B3h2H', placement.raw) for placement in self.placements]
            header = QLabel(f'{len(self.records)} placements | X/Y map | Click a point or row to inspect')
            header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            header.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(header)
            self.table = QTableWidget(len(self.records), 12)
            self.table.setHorizontalHeaderLabels(['#', 'Offset', 'Section', 'Layer', 'Type',
                'State', 'Variant', 'Facing', 'X', 'Y', 'Z', 'Flags'])
            for i, record in enumerate(self.records):
                placement = self.placements[i]
                values = [str(i), f'0x{placement.offset:04X}', str(placement.section),
                          str(placement.layer), f'{placement.kind:02X}', f'{record[3]:02X}',
                          f'{placement.variant:02X}', f'{record[5]:02X}'] + [
                    str(v) for v in placement.position] + [f'{record[9]:04X} {record[10]:04X}']
                for column, value in enumerate(values):
                    self.table.setItem(i, column, QTableWidgetItem(value))
            self.map = PlacementMap(self.records)
            split = QSplitter(Qt.Orientation.Vertical)
            split.addWidget(self.map)
            split.addWidget(self.table)
            split.setSizes([460, 260])
            layout.addWidget(split, 1)
            self.details = QLabel('Select a placement.')
            self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.details.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            layout.addWidget(self.details)
            self.map.picked.connect(lambda row: self.table.setCurrentCell(row, 0))
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
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents if kind == 'APD' else QHeaderView.ResizeMode.Interactive)
        if kind != 'APD':
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def select(self, row, column, old_row, old_column):
        self.map.selected = row
        self.map.update()
        if 0 <= row < len(self.placements):
            p = self.placements[row]
            self.details.setText(f'Placement #{row:03d} | offset 0x{p.offset:04X} | '
                f'layer {p.layer}, type {p.kind:02X}, variant {p.variant:02X} | '
                f'position {p.position}' + (' | relative to preceding parent' if p.relative else ''))
