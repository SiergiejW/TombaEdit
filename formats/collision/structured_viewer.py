"""Read-only APD placements and WHM word explorer."""
import struct
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QImage, QPolygonF, QTransform
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSplitter, QSizePolicy, QPushButton)


class PlacementMap(QWidget):
    picked = pyqtSignal(int)
    def __init__(self, records):
        super().__init__()
        self.records = records
        self.selected = -1
        self.visuals = []
        self.visual_cache = None
        self.zoom = 1.
        self.pan = QPointF()
        self.drag = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(280, 260)
        from gui.widgets.zoom_buttons import ZoomButtons
        ZoomButtons(self, lambda: self.zoom_by(1.2), lambda: self.zoom_by(1 / 1.2), self.fit)

    def set_scene(self, scene, source):
        """Record the loaded objects in APD X/Y coordinates, behind the dots."""
        import numpy as np
        from PIL.ImageQt import ImageQt
        from psx.graphics import texture_page
        from disc.reader import FormatError
        textures = {}
        self.visuals = []
        self.visual_cache = None
        images = {}
        positions = {e.placement.offset: e.placement.position for e in scene.entries
                     if e.source is source and e.placement is not None}
        # Relative APD records use their resolved parent position, just as
        # the overlaid object does. Preserve record order for row selection.
        self.records = [r[:6] + tuple(positions.get(i * 16, r[6:9])) + r[9:]
                        for i, r in enumerate(self.records)]
        entries = [e for e in scene.entries if e.source is source and e.placement is not None
                   and e.category in ('Models', 'Sprites', 'Spawned', 'Geometry', 'Backgrounds')]
        # Farther objects first; the placement map looks straight along Z.
        entries.sort(key=lambda e: e.placement.position[2], reverse=True)
        for entry in entries:
            for (page, clut, _), (vertices, uv, colors) in entry.mesh.batches.items():
                image = entry.mesh.image
                if image is None and page >= 0:
                    key = (page, clut)
                    if key not in textures:
                        try:
                            textures[key] = texture_page(scene.vram, page, clut)
                        except FormatError:
                            textures[key] = None
                    image = textures[key]
                if image is not None and id(image) not in images:
                    images[id(image)] = ImageQt(image.convert('RGBA')).copy()
                qimage = images.get(id(image))
                for start in range(0, len(vertices), 3):
                    target = np.asarray(vertices[start:start + 3, :2], dtype=float) * (1, -1)
                    if len(target) != 3:
                        continue
                    triangle = QPolygonF([QPointF(*p) for p in target])
                    if qimage is None:
                        color = np.clip(np.mean(colors[start:start + 3], axis=0), 0, 1)
                        self.visuals.append((triangle, QColor.fromRgbF(*map(float, color)), None))
                        continue
                    pixels = np.asarray(uv[start:start + 3], dtype=float) * (image.width, image.height)
                    try:
                        affine = np.linalg.solve(np.column_stack((pixels, np.ones(3))), target)
                    except np.linalg.LinAlgError:
                        continue
                    self.visuals.append((triangle, qimage, QTransform(*affine.ravel())))
        self.update()

    def points(self):
        if not self.records:
            return []
        transform = self.view_transform()
        return [(point.x(), point.y()) for point in
                (transform.map(QPointF(r[6], r[7])) for r in self.records)]

    def view_transform(self):
        xs, ys = [r[6] for r in self.records], [r[7] for r in self.records]
        scale = min((self.width() - 48) / max(1, max(xs) - min(xs)),
                    (self.height() - 48) / max(1, max(ys) - min(ys)))
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        transform = QTransform()
        transform.translate(self.width() / 2 + self.pan.x(), self.height() / 2 + self.pan.y())
        transform.scale(scale * self.zoom, scale * self.zoom)
        transform.translate(-cx, -cy)
        return transform

    def fit(self):
        self.zoom, self.pan = 1., QPointF()
        self.visual_cache = None
        self.update()

    def zoom_by(self, factor, anchor=None):
        if not self.records:
            return
        anchor = anchor if anchor is not None else QPointF(self.width() / 2, self.height() / 2)
        world = self.view_transform().inverted()[0].map(anchor)
        self.zoom = max(.1, min(64., self.zoom * factor))
        self.pan += anchor - self.view_transform().map(world)
        self.visual_cache = None
        self.update()

    def wheelEvent(self, event):
        self.zoom_by(1.2 ** (event.angleDelta().y() / 120), event.position())
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F:
            self.fit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self.drag = event.position()
            return
        points = self.points()
        if points:
            pos = event.position()
            row = min(range(len(points)), key=lambda i: (points[i][0] - pos.x()) ** 2 +
                                                       (points[i][1] - pos.y()) ** 2)
            if (points[row][0] - pos.x()) ** 2 + (points[row][1] - pos.y()) ** 2 <= 225:
                self.picked.emit(row)

    def mouseMoveEvent(self, event):
        if self.drag is not None:
            self.pan += event.position() - self.drag
            self.drag = event.position()
            self.visual_cache = None
            self.update()

    def mouseReleaseEvent(self, event):
        self.drag = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#202020'))
        if not self.records:
            return
        xs = [r[6] for r in self.records]
        ys = [r[7] for r in self.records]
        low_x, high_x = min(xs), max(xs)
        low_y, high_y = min(ys), max(ys)
        if self.visuals:
            if self.visual_cache is None or self.visual_cache.size() != self.size():
                self.visual_cache = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
                self.visual_cache.fill(Qt.GlobalColor.transparent)
                overlay = QPainter(self.visual_cache)
                overlay.setPen(Qt.PenStyle.NoPen)
                overlay.setWorldTransform(self.view_transform())
                for triangle, image, transform in self.visuals:
                    if transform is None:
                        overlay.setBrush(image)
                        overlay.drawPolygon(triangle)
                    else:
                        overlay.save()
                        clip = QPainterPath()
                        clip.addPolygon(triangle)
                        overlay.setClipPath(clip)
                        overlay.setWorldTransform(transform, combine=True)
                        overlay.drawImage(QPointF(0, 0), image)
                        overlay.restore()
                overlay.end()
            painter.save()
            painter.setOpacity(.5)
            painter.drawImage(0, 0, self.visual_cache)
            painter.restore()
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
            header = QLabel(f'{len(self.records)} placements | X/Y map | Objects: 50% opacity | '
                            'Scroll: zoom | Middle/right-drag: pan | F: fit')
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
