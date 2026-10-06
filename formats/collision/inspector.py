"""Bank, plane and original-record inspection for a level's WHM overlay."""
from gui.console import announce
import numpy as np
from PyQt6.QtCore import Qt, QEvent, QSettings
from PyQt6.QtGui import QVector4D
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QPushButton, QInputDialog)
from formats.collision.geometry import lines
from formats.collision.whm import attribute_shape


def describe(row):
    s = row.span
    directions = ', '.join(name for bit, name in ((1, 'stand / floor'), (2, 'ceiling'),
                           (4, 'push left'), (8, 'push right')) if s.attribute & bit)
    return (f'{row.source.label if row.source else "WHM"}\n{row.route}\nPlane {s.plane} at '
            f'{"X" if row.turned else "Z"} = {row.depth:g}\n{s.shape}\n'
            f'Path column {s.column}: {s.column * 8}..{s.column * 8 + 8}\n'
            f'Base Y {s.y0}, signed delta {s.y1:+d}, end Y {s.y0 + s.y1}\n'
            f'Horizontal start {s.start}, width {s.length}; contact mode {s.contact}\n'
            f'Attribute 0x{s.attribute:04X}: {directions or "no directional flags"}\n'
            f'Surface code {(s.attribute >> 5) & 15}; group {(s.attribute >> 9) & 7}; '
            f'control bits 0x{s.attribute & 0xF000:04X}\n'
            f'Parameter 0x{s.parameter:04X}; record offset 0x{s.offset:06X}\n\n'
            'Floor height uses signed division towards zero. This is a 2D collision '
            'slice, not a triangle mesh. High attribute fields remain numeric where '
            'their gameplay meaning is not verified.')


class CollisionInspector(QWidget):
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.rows = []
        self.visible_rows = []
        self.selected = None
        self.settings = QSettings('TombaEdit', 'TombaEdit')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.context = QLabel()
        self.context.setWordWrap(True)
        self.context.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.context)
        self.route = QComboBox(); self.plane = QComboBox(); self.attribute = QComboBox()
        layout.addWidget(self.route); layout.addWidget(self.plane); layout.addWidget(self.attribute)
        name = QPushButton('Name attribute...')
        name.clicked.connect(self.name_attribute)
        layout.addWidget(name)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Plane', 'Boundary', 'Attribute', 'Column', 'Offset'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.plane.currentIndexChanged.connect(self.filter_rows)
        self.route.currentIndexChanged.connect(self.filter_rows)
        self.attribute.currentIndexChanged.connect(self.filter_rows)
        self.table.currentCellChanged.connect(self.select)
        self.table.cellDoubleClicked.connect(lambda *_: self.frame())
        self.table.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_F:
            self.frame()
            return True
        return super().eventFilter(watched, event)

    def set_scene(self, scene):
        self.rows = scene.collision_records
        self.line_cache = {('Default route', None, None): scene.collision}
        self.selected = None
        self.context.setText(scene.collision_context if self.rows or scene.collision is None else
                             'This section has no WHM records. Town collision uses the cell map.')
        for combo in (self.route, self.plane, self.attribute):
            combo.blockSignals(True); combo.clear()
        self.route.addItem('Default route', 'Default route')
        if any(r.route != 'Default route' for r in self.rows):
            self.route.addItem('Alternate mountain route', 'Alternate mountain route')
            self.route.addItem('Both routes', None)
        self.route.setVisible(self.route.count() > 1)
        self.plane.addItem('All banks and planes', None)
        seen = set()
        for row in self.rows:
            key = (id(row.source), row.span.plane, row.route)
            if key not in seen:
                seen.add(key)
                self.plane.addItem(f'{row.source.code:04X} | Plane {row.span.plane} | '
                                   f'{"X" if row.turned else "Z"} {row.depth:g}', key)
        self.attribute.addItem('All attributes', None)
        for value in sorted({r.span.attribute for r in self.rows}):
            label = self.settings.value(f'whm/attributes/{value:04X}', '') or attribute_shape(value)
            self.attribute.addItem(f'{label or "Attribute"} 0x{value:04X}', value)
        for combo in (self.route, self.plane, self.attribute):
            combo.blockSignals(False)
        self.filter_rows()

    def name_attribute(self):
        value = self.selected.span.attribute if self.selected is not None else self.attribute.currentData()
        if value is None:
            return
        current = self.settings.value(f'whm/attributes/{value:04X}', '')
        label, accepted = QInputDialog.getText(self, 'Name WHM attribute',
                                             f'Attribute 0x{value:04X}:', text=current)
        if accepted:
            self.settings.setValue(f'whm/attributes/{value:04X}', label.strip())
            index = self.attribute.findData(value)
            self.attribute.setItemText(index, f'{label.strip() or attribute_shape(value)} 0x{value:04X}')

    def filter_rows(self):
        route, plane, attribute = self.route.currentData(), self.plane.currentData(), self.attribute.currentData()
        self.visible_rows = [r for r in self.rows if
                             (route is None or r.route == route) and
                             (plane is None or (id(r.source), r.span.plane, r.route) == plane) and
                             (attribute is None or r.span.attribute == attribute)]
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.visible_rows))
        for i, row in enumerate(self.visible_rows):
            s = row.span
            for col, value in enumerate((s.plane, s.shape, f'{s.attribute:04X}', s.column, f'{s.offset:06X}')):
                self.table.setItem(i, col, QTableWidgetItem(str(value)))
        self.table.clearSelection(); self.table.setCurrentCell(-1, -1)
        self.table.blockSignals(False)
        self.selected = None
        self.viewer.canvas.selection_lines = None
        key = (route, plane, attribute)
        if key not in self.line_cache:
            self.line_cache[key] = lines(self.visible_rows) if self.rows else self.viewer.scene.collision
        self.viewer.canvas.lines = self.line_cache[key]
        self.viewer.canvas.update()

    def select(self, index, *_):
        if not 0 <= index < len(self.visible_rows):
            return
        self.selected = self.visible_rows[index]
        canvas = self.viewer.canvas
        canvas.selected = None; canvas.selected_model = None
        canvas.selection_lines = self.selected.points
        self.viewer.details.setPlainText(describe(self.selected))
        announce('collision | ' + describe(self.selected).replace('\n', ' | '))
        canvas.update()

    def frame(self):
        if self.selected is None:
            return
        canvas = self.viewer.canvas
        points = np.asarray(self.selected.points)
        lo, hi = points.min(axis=0), points.max(axis=0)
        radius = max(20., float(np.linalg.norm(hi - lo)) / 2)
        if canvas.flat_mode:
            import math
            from gui.widgets.camera_controls import FIELD_OF_VIEW
            centre = (lo + hi) / 2
            centre[2] = 0
            half = max(20., (hi[1] - lo[1]) / 2,
                       (hi[0] - lo[0]) / 2 * canvas.height() / max(1, canvas.width())) * 1.08
            canvas.camera_controls.glide_frame(centre, radius, heading=0, pitch=0,
                margin=half / math.tan(math.radians(FIELD_OF_VIEW) / 2) / (radius * 1.2))
            canvas.auto_fit = False
            return
        canvas.camera_controls.glide_frame((lo + hi) / 2, radius,
                                          heading=90 if self.selected.turned else 0, pitch=0)
        canvas.auto_fit = False

    def pick(self, position):
        """Screen-distance line picking, so thin vertical records are clickable."""
        canvas = self.viewer.canvas
        if not self.visible_rows:
            return False
        matrix = canvas._model_view_projection()
        click = np.array((position.x(), position.y()))
        nearest, found = 8., None
        for index, row in enumerate(self.visible_rows):
            for a, b in zip(row.points[::2], row.points[1::2]):
                projected = [matrix.map(QVector4D(*p, 1)) for p in (a, b)]
                if any(p.w() <= 0 or not -1 <= p.z() / p.w() <= 1 for p in projected):
                    continue
                start, end = [np.array(((p.x() / p.w() + 1) * canvas.width() / 2,
                                       (1 - p.y() / p.w()) * canvas.height() / 2)) for p in projected]
                delta = end - start
                t = np.clip(np.dot(click - start, delta) / max(np.dot(delta, delta), 1e-12), 0, 1)
                distance = float(np.linalg.norm(click - start - t * delta))
                if distance < nearest:
                    nearest, found = distance, index
        if found is None:
            return False
        self.table.setCurrentCell(found, 1)
        self.select(found)
        return True
