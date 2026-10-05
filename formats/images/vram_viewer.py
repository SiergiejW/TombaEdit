"""VRAM viewer: 1024 x 512 words of textures and palettes side by side.

VRAM carries no description of itself, so the view offers the readings that
are useful when looking for something: 4-bit texels as grey or false-colour
indices, the same texels through one palette, 8-bit texels through a 256
colour palette, and every word as a 15-bit pixel.

A palette can be typed as a CLUT word, chosen from the ones the open
resource uses, or picked on the picture: the right mouse button puts the
crosshair on a palette row and drags it, the left button drags it when the
press lands on it, and the arrow keys walk it.

Zoom and pan draw a source rectangle of one unscaled pixmap, so the cost of
a repaint does not grow with the zoom.
"""
import colorsys
import numpy as np
from PIL import Image
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget)
from psx.graphics import rgba

WIDTH, HEIGHT = 1024, 512
MODE_GREY, MODE_FALSE, MODE_CLUT, MODE_DIRECT = (
    '4-bit indices (grey)', '4-bit indices (false colour)', 'Through CLUT', '16-bit direct')
MIN_ZOOM, MAX_ZOOM = 0.1, 32.0
# How long the red marker stays after the palette changes.
MARK_MS = 1500

CONTROLS = ('Ctrl + wheel: zoom | Wheel: scroll, Shift + wheel: sideways\n'
            'Left or middle drag: pan\n'
            'Ctrl + left click or drag, or right: read through the palette under the pointer\n'
            'Left drag on the crosshair: move it\n'
            'Arrows: next palette or row | Shift + arrows: page or 16 rows')


def false_colours():
    """Sixteen colours far apart in hue, so neighbouring indices read apart."""
    out = np.zeros((16, 4), np.uint8)
    out[:, 3] = 255
    for i in range(1, 16):
        r, g, b = colorsys.hsv_to_rgb(i * 7 % 15 / 15, .85, .55 + .45 * (i % 2))
        out[i, :3] = int(r * 255), int(g * 255), int(b * 255)
    return out


FALSE_COLOURS = false_colours()


def clut_word(x, y):
    return (y & 511) << 6 | (x // 16) & 63


def clut_xy(word):
    return (word & 63) * 16, (word >> 6) & 511


def texels(vram):
    """4096 x 512 four-bit indices; the leftmost texel is the low nibble."""
    out = np.empty((HEIGHT, WIDTH * 4), np.uint8)
    for n in range(4):
        out[:, n::4] = (vram >> (n * 4)) & 15
    return out


# Every section uploads its palettes as one block here.
CLUT_BLOCK = (128, 480, 256, 32)


def find_palette(vram, colours=16, prefer=()):
    """A palette that shows something: one of `prefer`, else a row of the
    section's palette block, else the first row anywhere, as long as it holds
    at least three different colours."""
    def usable(x, y):
        return x + colours <= WIDTH and len(set(vram[y, x:x + colours].tolist())) >= 3
    left, top, width, height = CLUT_BLOCK
    block = [(x, y) for y in range(top, top + height) for x in range(left, left + width, 16)]
    everywhere = ((x, y) for y in range(HEIGHT) for x in range(0, WIDTH, 16))
    for x, y in [clut_xy(word) for word in prefer] + block:
        if usable(x, y):
            return clut_word(x, y)
    return next((clut_word(x, y) for x, y in everywhere if usable(x, y)), 0)


class VramCanvas(QWidget):
    hovered = pyqtSignal(int, int)      # image pixel under the cursor
    picked_clut = pyqtSignal(int)       # CLUT word, right button
    crosshair_moved = pyqtSignal(int)   # CLUT word, arrow keys or right-drag

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.pixmap = None
        self.zoom = 1.0
        self.origin = QPointF(0, 0)     # top-left of the view, in image pixels
        self.show_grid = False
        self.per_word = 4               # image pixels drawn per VRAM word
        self.crosshair = None           # (word x, row) of a palette, or None
        self.colours = 16
        self.mark = None                # palette flagged by the timed marker
        self.auto_fit = True            # until the view is zoomed or dragged
        self.drag_from = self.drag_origin = self.picking = None
        self.help = QLabel(CONTROLS, self)
        self.help.setObjectName('viewerOverlay')
        self.help.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.help.adjustSize()
        self.mark_timer = QTimer(self)
        self.mark_timer.setSingleShot(True)
        self.mark_timer.timeout.connect(self.clear_mark)

    def set_image(self, image):
        self.pixmap = QPixmap.fromImage(image)
        if self.auto_fit:
            self.fit()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.help.move(self.width() - self.help.width() - 6, self.height() - self.help.height() - 6)
        if self.auto_fit and self.pixmap:
            self.fit()

    def fit(self):
        if not self.pixmap:
            return
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, min(self.width() / self.pixmap.width(),
                                                    self.height() / self.pixmap.height())))
        self.origin = QPointF(0, 0)
        self.auto_fit = True
        self.update()

    def set_zoom(self, zoom, about=None):
        if not self.pixmap:
            return
        about = about or QPointF(self.width() / 2, self.height() / 2)
        before = self.to_image(about)
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.origin += before - self.to_image(about)
        self.auto_fit = False
        self.clamp()
        self.update()

    def to_image(self, point):
        return QPointF(self.origin.x() + point.x() / self.zoom, self.origin.y() + point.y() / self.zoom)

    def clamp(self):
        if not self.pixmap:
            return
        max_x = max(0., self.pixmap.width() - self.width() / self.zoom)
        max_y = max(0., self.pixmap.height() - self.height() / self.zoom)
        self.origin = QPointF(min(max(0., self.origin.x()), max_x), min(max(0., self.origin.y()), max_y))

    def flash(self, word):
        """Point at a palette row for a moment."""
        self.mark = clut_xy(word)
        self.mark_timer.start(MARK_MS)
        self.update()

    def clear_mark(self):
        self.mark = None
        self.update()

    def keep_in_view(self, x, y):
        left, width = x * self.per_word, self.colours * self.per_word
        span_x, span_y = self.width() / self.zoom, self.height() / self.zoom
        ox, oy = self.origin.x(), self.origin.y()
        if left < ox:
            ox = left - span_x / 4
        elif left + width > ox + span_x:
            ox = left + width - span_x * 3 / 4
        if y < oy:
            oy = y - span_y / 4
        elif y + 1 > oy + span_y:
            oy = y + 1 - span_y * 3 / 4
        self.origin = QPointF(ox, oy)
        self.clamp()

    def palette_at(self, position):
        if not self.pixmap:
            return None
        at = self.to_image(QPointF(position))
        if not (0 <= at.x() < self.pixmap.width() and 0 <= at.y() < self.pixmap.height()):
            return None
        return clut_word(int(at.x()) // self.per_word, int(at.y()))

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if not self.pixmap or not steps:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.zoom * 1.25 ** steps, event.position())
        else:
            # A tenth of the view per notch, down the picture or along it.
            sideways = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            span = (self.width() if sideways else self.height()) / self.zoom
            move = QPointF(-steps * span / 10, 0) if sideways else QPointF(0, -steps * span / 10)
            self.origin += move
            self.auto_fit = False
            self.clamp()
            self.update()
        event.accept()

    def keyPressEvent(self, event):
        """Arrows step the crosshair one palette or one row; with Shift a
        texture page across or sixteen rows."""
        if self.crosshair is None:
            return super().keyPressEvent(event)
        big = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        across, down = (64, 16) if big else (16, 1)
        move = {Qt.Key.Key_Left: (-across, 0), Qt.Key.Key_Right: (across, 0),
                Qt.Key.Key_Up: (0, -down), Qt.Key.Key_Down: (0, down)}.get(event.key())
        if move is None:
            return super().keyPressEvent(event)
        x, y = (self.crosshair[0] + move[0]) % WIDTH, (self.crosshair[1] + move[1]) % HEIGHT
        self.crosshair = (x, y)
        self.keep_in_view(x, y)
        self.update()
        self.crosshair_moved.emit(clut_word(x, y))
        event.accept()

    def mousePressEvent(self, event):
        self.setFocus()
        on_crosshair = (event.button() == Qt.MouseButton.LeftButton and self.crosshair is not None
                        and self.row_rect(self.crosshair).adjusted(-4, -4, 4, 4).contains(event.position()))
        with_ctrl = (event.button() == Qt.MouseButton.LeftButton
                     and bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
        if with_ctrl:
            on_crosshair = False
        if event.button() == Qt.MouseButton.RightButton or on_crosshair or with_ctrl:
            self.picking = self.palette_at(event.position())
            if self.picking is not None and not on_crosshair:
                self.picked_clut.emit(self.picking)
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self.drag_from, self.drag_origin = event.position(), QPointF(self.origin)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.picking is not None:
            word = self.palette_at(event.position())
            if word is not None and word != self.picking:
                self.picking = word
                self.crosshair_moved.emit(word)
        if self.drag_from is not None:
            self.origin = self.drag_origin - (event.position() - self.drag_from) / self.zoom
            self.auto_fit = False
            self.clamp()
            self.update()
            return
        at = self.to_image(event.position())
        if self.pixmap and 0 <= at.x() < self.pixmap.width() and 0 <= at.y() < self.pixmap.height():
            self.hovered.emit(int(at.x()), int(at.y()))

    def mouseReleaseEvent(self, event):
        self.drag_from = self.picking = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def row_rect(self, position):
        """Widget rectangle of the palette row at (word x, row)."""
        x, y = position
        left = (x * self.per_word - self.origin.x()) * self.zoom
        top = (y - self.origin.y()) * self.zoom
        return QRectF(left, top, self.colours * self.per_word * self.zoom, max(self.zoom, 1.))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 24, 24))
        if not self.pixmap:
            painter.setPen(QColor(160, 160, 160))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'No VRAM loaded')
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        source = QRectF(self.origin.x(), self.origin.y(), self.width() / self.zoom, self.height() / self.zoom)
        clipped = source.intersected(QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        if clipped.isEmpty():
            return
        painter.drawPixmap(QRectF((clipped.x() - source.x()) * self.zoom, (clipped.y() - source.y()) * self.zoom,
                                  clipped.width() * self.zoom, clipped.height() * self.zoom),
                           self.pixmap, clipped)
        if self.show_grid:
            # Texture pages: 64 words across, 256 rows down.
            painter.setPen(QPen(QColor(0, 200, 255, 140), 1))
            step = 64 * self.per_word
            x = int(source.x()) // step * step
            while x <= source.right():
                at = int((x - source.x()) * self.zoom)
                painter.drawLine(at, 0, at, self.height())
                x += step
            for y in (0, 256, 512):
                at = int((y - source.y()) * self.zoom)
                painter.drawLine(0, at, self.width(), at)
        if self.crosshair is not None:
            rect = self.row_rect(self.crosshair)
            centre = rect.center()
            pen = QPen(QColor(255, 60, 200, 150), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(0, centre.y()), QPointF(rect.left() - 4, centre.y()))
            painter.drawLine(QPointF(rect.right() + 4, centre.y()), QPointF(self.width(), centre.y()))
            painter.drawLine(QPointF(centre.x(), 0), QPointF(centre.x(), rect.top() - 4))
            painter.drawLine(QPointF(centre.x(), rect.bottom() + 4), QPointF(centre.x(), self.height()))
            painter.setPen(QPen(QColor(255, 60, 200), 2))
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))
        if self.mark is not None:
            rect = self.row_rect(self.mark)
            tip = QPointF(rect.center().x(), rect.top() - 3)
            painter.setPen(QPen(QColor(255, 40, 40), 2))
            painter.setBrush(QColor(255, 40, 40))
            painter.drawPolygon(QPolygonF([tip, tip + QPointF(-9, -14), tip + QPointF(9, -14)]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))


class VramView(QWidget):
    def __init__(self, vram, cluts=(), name='VRAM'):
        """`cluts` are the CLUT words the open resource draws with."""
        super().__init__()
        self.vram, self.name = np.ascontiguousarray(vram, np.uint16), name
        self.index_cache = None
        self.image = None
        self.canvas = VramCanvas()
        self.canvas.hovered.connect(self.hover)
        self.canvas.picked_clut.connect(self.set_clut)
        self.canvas.crosshair_moved.connect(self.crosshair_moved)
        self.mode = QComboBox()
        self.mode.addItems([MODE_CLUT, MODE_GREY, MODE_FALSE, MODE_DIRECT])
        self.mode.setToolTip('How to read the words. Textures and palettes sit together with nothing\n'
                             'marking which is which, so this chooses what to look for.')
        self.clut_box = QComboBox()
        self.clut_box.setEditable(True)
        self.clut_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.clut_box.setToolTip('Palette as a CLUT word (row * 64 + x / 16). The list holds the palettes\n'
                                 'the open resource uses; right-click a palette row to pick one.')
        for word in sorted(set(cluts)):
            x, y = clut_xy(word)
            self.clut_box.addItem(f'0x{word:04X}  ({x}, {y})', word)
        self.depth = QComboBox()
        self.depth.addItems(['16 colours', '256 colours'])
        self.cross = QCheckBox('Crosshair')
        self.cross.setToolTip('Mark the palette row. Arrow keys move it one palette or one row;\n'
                              'with Shift a texture page across or sixteen rows.')
        self.grid = QCheckBox('Page grid')
        top = QHBoxLayout()
        top.setContentsMargins(8, 4, 8, 2)
        for widget in (QLabel('Read as:'), self.mode, QLabel('CLUT:'), self.clut_box, self.depth,
                       self.cross, self.grid):
            top.addWidget(widget)
        top.addStretch(1)
        self.info = QLabel()
        self.info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(8, 2, 8, 4)
        bottom.addWidget(self.info, 1)
        for label, callback in (('-', lambda: self.canvas.set_zoom(self.canvas.zoom / 2)),
                                ('+', lambda: self.canvas.set_zoom(self.canvas.zoom * 2)),
                                ('1:1', lambda: self.canvas.set_zoom(1.0)),
                                ('Fit', self.canvas.fit), ('Export PNG...', self.export_png),
                                ('Export raw...', self.export_raw)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            bottom.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(top)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(bottom)
        self.clut = find_palette(self.vram, 16, sorted(set(cluts)))
        self.clut_box.setEditText(f'0x{self.clut:04X}')
        self.cross.setChecked(True)
        self.canvas.crosshair = clut_xy(self.clut)
        self.mode.currentTextChanged.connect(self.render)
        self.depth.currentTextChanged.connect(self.depth_changed)
        self.cross.toggled.connect(self.toggle_crosshair)
        self.grid.toggled.connect(self.toggle_grid)
        self.clut_box.lineEdit().returnPressed.connect(self.clut_typed)
        self.clut_box.activated.connect(self.clut_chosen)
        self.render()

    def colours(self):
        return 256 if self.depth.currentIndex() else 16

    def indices(self):
        if self.index_cache is None:
            self.index_cache = texels(self.vram)
        return self.index_cache

    def palette(self):
        x, y = clut_xy(self.clut)
        flat = self.vram.reshape(-1)
        return rgba(flat[(y * WIDTH + x + np.arange(self.colours())) % flat.size])

    def set_clut(self, word, announce=True):
        """Read through this palette and point it out on the picture."""
        self.clut = int(word) & 0x7FFF
        self.clut_box.setEditText(f'0x{self.clut:04X}')
        if self.cross.isChecked():
            self.canvas.crosshair = clut_xy(self.clut)
        if self.mode.currentText() != MODE_CLUT:
            self.mode.setCurrentText(MODE_CLUT)
        else:
            self.render()
        self.canvas.flash(self.clut)
        if announce:
            x, y = clut_xy(self.clut)
            print(f'selected: CLUT 0x{self.clut:04X} @ ({x}, {y}) ({self.name})')

    def crosshair_moved(self, word):
        self.set_clut(word)

    def clut_typed(self):
        words = self.clut_box.currentText().split()
        try:
            self.set_clut(int(words[0], 16))
        except (ValueError, IndexError):
            self.info.setText(f'"{self.clut_box.currentText()}" is not a hexadecimal CLUT word')

    def clut_chosen(self, index):
        word = self.clut_box.itemData(index)
        if word is not None:
            self.set_clut(word)

    def depth_changed(self):
        self.canvas.colours = self.colours()
        if self.mode.currentText() == MODE_CLUT:
            x, y = clut_xy(self.clut)
            if len(set(self.vram[y, x:x + self.colours()].tolist())) < 3:
                self.set_clut(find_palette(self.vram, self.colours()), announce=False)
                return
        self.render()

    def toggle_crosshair(self, on):
        self.canvas.crosshair = clut_xy(self.clut) if on else None
        if on:
            self.canvas.setFocus()
        self.canvas.update()

    def toggle_grid(self, on):
        self.canvas.show_grid = on
        self.canvas.update()

    def render(self):
        mode = self.mode.currentText()
        self.canvas.colours = self.colours()
        if mode == MODE_DIRECT:
            pixels = rgba(self.vram).copy()
            pixels[..., 3] = 255
            self.canvas.per_word = 1
        else:
            self.canvas.per_word = 4
            if mode == MODE_CLUT and self.colours() == 256:
                palette = self.palette()
                palette[:, 3] = 255
                pixels = np.repeat(palette[self.vram.view(np.uint8).reshape(HEIGHT, WIDTH * 2)], 2, axis=1)
            elif mode == MODE_CLUT:
                palette = self.palette()
                palette[:, 3] = 255
                pixels = palette[self.indices()]
            elif mode == MODE_FALSE:
                pixels = FALSE_COLOURS[self.indices()]
            else:
                grey = self.indices() * 17
                pixels = np.dstack([grey, grey, grey, np.full_like(grey, 255)])
            # Palette rows keep their own colours in every 4-bit reading.
            x, y = clut_xy(self.clut)
            row = rgba(self.vram[y, x:x + self.colours()]).copy()
            row[:, 3] = 255
            pixels = np.ascontiguousarray(pixels)
            pixels[y, x * 4:(x + len(row)) * 4] = np.repeat(row, 4, axis=0)
        pixels = np.ascontiguousarray(pixels)
        self.image = QImage(pixels.tobytes(), pixels.shape[1], pixels.shape[0], pixels.shape[1] * 4,
                            QImage.Format.Format_RGBA8888).copy()
        self.canvas.set_image(self.image)
        self.describe()

    def describe(self, extra=''):
        x, y = clut_xy(self.clut)
        text = f'{self.name}: {self.mode.currentText()}'
        if self.mode.currentText() == MODE_CLUT:
            text += f', CLUT 0x{self.clut:04X} at ({x}, {y}), {self.colours()} colours'
        self.info.setText(text + extra)

    def hover(self, x, y):
        word = x // self.canvas.per_word
        page = word // 64 + (y // 256) * 16
        self.describe(f'  |  word ({word}, {y})  page {page}  value 0x{int(self.vram[y, word]):04X}'
                      f'  zoom {self.canvas.zoom:.2f}x')

    def export_png(self):
        if self.image is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export VRAM picture', 'vram.png', 'PNG (*.png)')
        if path and self.image.save(path, 'PNG'):
            print(f'wrote {path}')

    def export_raw(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export raw VRAM', 'vram.bin', 'Raw VRAM (*.bin *.vram)')
        if path:
            try:
                with open(path, 'wb') as stream:
                    stream.write(self.vram.astype('<u2').tobytes())
                print(f'wrote {path} ({self.vram.size * 2} bytes)')
            except OSError as exc:
                self.info.setText(f'Export failed: {exc}')
