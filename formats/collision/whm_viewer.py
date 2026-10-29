"""Interactive X/Y viewer for Tomba 1 WHM collision planes."""
from gui.console import announce
from collections import Counter

from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QInputDialog)

from formats.collision.whm import parse_whm, attribute_shape
from formats.collision.geometry import records, lines


BEHAVIOR_NAMES = ('Standing', 'Ass-sliding', 'Set rotation', 'Butterflies',
                  'Leaves', 'Hurt', 'Jump down', 'Jump up')
PLANE_COLORS = ('#a7c653', '#57a8db', '#f2a95b', '#d781cf', '#e0d15d',
                '#61cdb2', '#e47e75', '#aaa4eb')


class PlaneCanvas(QWidget):
    picked = pyqtSignal(object)

    def __init__(self, whm):
        super().__init__()
        self.whm = whm
        self.plane = -1
        self.attribute = None
        self.selected = None
        self.line_cache = {}
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.drag_from = None
        self.setMinimumSize(360, 300)
        from gui.widgets.zoom_buttons import ZoomButtons
        ZoomButtons(self, lambda: self.zoom_by(1.2), lambda: self.zoom_by(1 / 1.2), self.fit)

    def visible_spans(self):
        planes = self.whm.planes if self.plane < 0 else [self.whm.planes[self.plane]]
        return [span for plane in planes for span in plane.spans]

    def y_bounds(self):
        spans = self.visible_spans()
        if not spans:
            return -100, 100
        low = min(span.extent[0] for span in spans)
        high = max(span.extent[1] for span in spans)
        pad = max(16, (high - low) // 20)
        return low - pad, high + pad

    def transform(self):
        ymin, ymax = self.y_bounds()
        room_w, room_h = max(1, self.width() - 56), max(1, self.height() - 52)
        scale = min(room_w / max(1, self.whm.width), room_h / max(1, ymax - ymin)) * self.zoom
        return 40 + self.pan_x, 12 - ymin * scale + self.pan_y, scale, ymin, ymax

    def fit(self):
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#202020'))
        ox, oy, scale, ymin, ymax = self.transform()
        painter.setPen(QPen(QColor('#454545')))
        for x in range(0, self.whm.width + 1, 256):
            screen = round(ox + x * scale)
            painter.drawLine(screen, 0, screen, self.height())
        for y in range((ymin // 128) * 128, ymax + 1, 128):
            screen = round(oy + y * scale)
            painter.drawLine(0, screen, self.width(), screen)
        key = (self.plane, self.attribute)
        if key not in self.line_cache:
            rows = records(self.whm, planes=None if self.plane < 0 else {self.plane})
            self.line_cache[key] = lines([r for r in rows if
                                         self.attribute is None or r.span.attribute == self.attribute])
        geometry = self.line_cache[key]
        if geometry is not None:
            vertices, colors = geometry
            for index in range(0, len(vertices), 2):
                color = QColor.fromRgbF(*map(float, colors[index]))
                painter.setPen(QPen(color, 1.5))
                a, b = vertices[index:index + 2]
                painter.drawLine(round(ox + a[0] * scale), round(oy - a[1] * scale),
                                 round(ox + b[0] * scale), round(oy - b[1] * scale))
        if self.selected is not None:
            painter.setPen(QPen(QColor('#ff6060'), 3))
            for (x0, y0), (x1, y1) in self.selected.segments:
                painter.drawLine(round(ox + x0 * scale), round(oy + y0 * scale),
                                 round(ox + x1 * scale), round(oy + y1 * scale))
        painter.setPen(QColor('#dddddd'))
        painter.drawText(8, self.height() - 7,
                         f'X 0..{self.whm.width} | Y {ymin}..{ymax} | Scroll: zoom | Right-drag: pan')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.drag_from = event.globalPosition().toPoint()
            self.pan_from = (self.pan_x, self.pan_y)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        ox, oy, scale, ymin, ymax = self.transform()
        x = max(0, min(self.whm.width // 8 - 1,
                       int((event.position().x() - ox) / max(scale, 1e-9) / 8)))
        y = (event.position().y() - oy) / max(scale, 1e-9)
        planes = self.whm.planes if self.plane < 0 else [self.whm.planes[self.plane]]
        candidates = [span for plane in planes for span in plane.columns[x]
                      if self.attribute is None or span.attribute == self.attribute]
        self.selected = min(candidates,
                            key=lambda span: max(span.extent[0] - y, 0,
                                                 y - span.extent[1])) if candidates else None
        self.picked.emit((x, self.selected))
        self.update()

    def mouseMoveEvent(self, event):
        if self.drag_from is not None:
            delta = event.globalPosition().toPoint() - self.drag_from
            self.pan_x = self.pan_from[0] + delta.x()
            self.pan_y = self.pan_from[1] + delta.y()
            self.update()

    def mouseReleaseEvent(self, event):
        self.drag_from = None

    def wheelEvent(self, event):
        self.zoom_by(1.2 if event.angleDelta().y() > 0 else 1 / 1.2, event.position().x(), event.position().y())

    def zoom_by(self, factor, x=None, y=None):
        """Zoom about a point of the widget, the middle of it unless given."""
        old_ox, old_oy, old_scale, _, _ = self.transform()
        x = self.width() / 2 if x is None else x
        y = self.height() / 2 if y is None else y
        self.zoom = max(0.25, min(24.0, self.zoom * factor))
        new_ox, new_oy, new_scale, _, _ = self.transform()
        self.pan_x += (x - old_ox) / old_scale * (old_scale - new_scale)
        self.pan_y += (y - old_oy) / old_scale * (old_scale - new_scale)
        self.update()


class WhmView(QWidget):
    def __init__(self, data):
        super().__init__()
        self.whm = parse_whm(data)
        self.settings = QSettings('TombaEdit', 'TombaEdit')
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.plane = QComboBox()
        self.plane.addItem(f'All {len(self.whm.planes)} planes', -1)
        for plane in self.whm.planes:
            self.plane.addItem(f'Plane {plane.index} | {len(plane.spans):,} spans', plane.index)
        self.plane.currentIndexChanged.connect(self.change_plane)
        bar.addWidget(QLabel('Plane:')); bar.addWidget(self.plane)
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(self.change_filter)
        bar.addWidget(QLabel('Attribute:')); bar.addWidget(self.filter)
        fit = QPushButton('Fit map'); fit.clicked.connect(lambda: self.canvas.fit())
        bar.addWidget(fit)
        name = QPushButton('Name attribute...'); name.clicked.connect(self.name_attribute)
        bar.addWidget(name)
        bar.addStretch()
        layout.addLayout(bar)
        split = QSplitter()
        self.canvas = PlaneCanvas(self.whm)
        self.canvas.picked.connect(self.pick)
        split.addWidget(self.canvas)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel('Attributes in this view'))
        self.attributes = QTableWidget(0, 3)
        self.attributes.setHorizontalHeaderLabels(['Value', 'Name', 'Spans'])
        self.attributes.verticalHeader().hide()
        self.attributes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.attributes.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.attributes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.attributes.cellClicked.connect(self.filter_from_row)
        self.attributes.cellDoubleClicked.connect(lambda row, col: self.name_attribute(row))
        side_layout.addWidget(self.attributes, 1)
        side_layout.addWidget(QLabel('Spans at selected X'))
        self.records = QTableWidget(0, 6)
        self.records.setHorizontalHeaderLabels(['Plane', 'Attribute', 'Base Y', 'Y delta', 'Parameter', 'Offset'])
        self.records.verticalHeader().hide()
        self.records.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.records.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.records.currentCellChanged.connect(
            lambda row, col, old_row, old_col: self.select_record(row, col))
        side_layout.addWidget(self.records, 1)
        self.details = QLabel('Click the X/Y map to inspect a collision span.')
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side_layout.addWidget(self.details)
        split.addWidget(side)
        split.setSizes([760, 450])
        layout.addWidget(split)
        self.refresh_attributes()

    def label(self, attribute):
        return self.settings.value(f'whm/attributes/{attribute:04X}', '') or attribute_shape(attribute)

    def change_plane(self):
        self.canvas.plane = self.plane.currentData()
        self.canvas.selected = None
        self.canvas.fit()
        self.refresh_attributes()
        self.records.setRowCount(0)

    def refresh_attributes(self):
        selected = self.filter.currentData()
        counts = Counter(span.attribute for span in self.canvas.visible_spans())
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem('All attributes', None)
        self.attributes.setRowCount(len(counts))
        for row, (attribute, amount) in enumerate(sorted(counts.items())):
            name = self.label(attribute)
            self.filter.addItem(f'{name or "Attribute"} 0x{attribute:04X}', attribute)
            for col, value in enumerate((f'0x{attribute:04X}', name or 'Unmapped', str(amount))):
                self.attributes.setItem(row, col, QTableWidgetItem(value))
        index = self.filter.findData(selected)
        self.filter.setCurrentIndex(max(0, index))
        self.filter.blockSignals(False)
        self.canvas.attribute = self.filter.currentData()
        self.canvas.update()

    def change_filter(self):
        self.canvas.attribute = self.filter.currentData()
        self.canvas.update()

    def filter_from_row(self, row, column):
        if row >= 0:
            attribute = int(self.attributes.item(row, 0).text(), 16)
            self.filter.setCurrentIndex(self.filter.findData(attribute))

    def name_attribute(self, row=None):
        if isinstance(row, bool):
            row = None
        if row is None:
            row = self.attributes.currentRow()
        if row < 0:
            return
        attribute = int(self.attributes.item(row, 0).text(), 16)
        current = self.label(attribute)
        choices = [current] + [name for name in BEHAVIOR_NAMES if name != current]
        name, accepted = QInputDialog.getItem(self, 'Name WHM attribute',
            f'Attribute 0x{attribute:04X}:', choices, 0, True)
        if accepted:
            self.settings.setValue(f'whm/attributes/{attribute:04X}', name.strip())
            self.refresh_attributes()

    def pick(self, selection):
        column, picked = selection
        planes = self.whm.planes if self.canvas.plane < 0 else [self.whm.planes[self.canvas.plane]]
        spans = [span for plane in planes for span in plane.columns[column]]
        self.column_spans = spans
        self.records.setRowCount(len(spans))
        for row, span in enumerate(spans):
            values = (str(span.plane), f'0x{span.attribute:04X}', str(span.y0),
                      str(span.y1), f'0x{span.parameter:04X}', f'0x{span.offset:06X}')
            for col, value in enumerate(values):
                self.records.setItem(row, col, QTableWidgetItem(value))
        if picked in spans:
            self.records.setCurrentCell(spans.index(picked), 0)
        else:
            self.details.setText(f'X {column * 8}..{column * 8 + 7} | no spans')

    def select_record(self, row, column):
        if row < 0 or row >= len(getattr(self, 'column_spans', [])):
            return
        span = self.column_spans[row]
        self.canvas.selected = span
        self.canvas.update()
        name = self.label(span.attribute)
        shape = (f'{span.shape}: Y {span.y0}..{span.y0 + span.y1} | '
                 f'horizontal start {span.start}, width {span.length} | contact {span.contact}')
        text = (f'Plane {span.plane} | X {span.column * 8}..{span.column * 8 + 7} | '
                f'{shape}\nAttribute 0x{span.attribute:04X}'
                f'{" | " + name if name else ""} | parameter 0x{span.parameter:04X} | '
                f'file offset 0x{span.offset:06X}')
        self.details.setText(text)
        announce('WHM span | ' + text.replace('\n', ' | '))
