"""VRAM viewer: 1024 x 512 words of textures and palettes side by side.

VRAM carries no description of itself, so two things are chosen separately.
How the words are cut into pixels: four bits each, eight, one word a pixel,
or three bytes a pixel. And, for the two indexed readings, how an index is
coloured: through the palette under the crosshair, as grey, or in colours
picked to tell neighbouring indices apart.

The crosshair marks a palette row. It can be typed as a CLUT word, chosen
from the palettes the open resource uses, or put on the picture: the right
mouse button places and drags it, the left button drags it when the press
lands on it, and the arrow keys walk it. Moving it never scrolls the view
and never changes how the pixels are read.

Zoom and pan draw a source rectangle of one unscaled pixmap, so the cost of
a repaint does not grow with the zoom.
"""
import colorsys
from gui.console import announce
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget)
from psx.graphics import rgba

WIDTH, HEIGHT = 1024, 512
# Pixel readings: label, bits a pixel, and image pixels drawn per VRAM word.
PIXELS = (('4-bit', 4, 4), ('8-bit', 8, 2), ('16-bit', 16, 1), ('24-bit', 24, 2 / 3))
COLOUR_CLUT, COLOUR_GREY, COLOUR_FALSE = 'Palette at crosshair', 'Grey', 'False colour'
MIN_ZOOM, MAX_ZOOM = 0.1, 32.0
# How long the red marker stays after the palette changes.
MARK_MS = 1500

CONTROLS = ('Ctrl + wheel: zoom | Wheel: scroll, Shift + wheel: sideways\n'
            'Left or middle drag: pan\n'
            'Ctrl + left click or drag, or right: put the crosshair on the palette under the pointer\n'
            'Left drag on the crosshair: move it\n'
            'Arrows: next palette or row | Shift + arrows: page or 16 rows')


def false_colours(count=16):
    """Colours far apart in hue, so neighbouring indices read apart."""
    out = np.zeros((count, 4), np.uint8)
    out[:, 3] = 255
    for i in range(1, count):
        r, g, b = colorsys.hsv_to_rgb(i * 7 % 15 / 15 + (i // 16) / 97 % 1, .85, .55 + .45 * (i % 2))
        out[i, :3] = int(r * 255), int(g * 255), int(b * 255)
    return out


FALSE_COLOURS = {16: false_colours(16), 256: false_colours(256)}


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
        self.setMinimumSize(320, 120)
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
        # Rectangles to outline, as (word x, row, words, rows, colour): where
        # the parts of the open sprite take their pixels from.
        self.outlines = []
        self.auto_fit = True            # until the view is zoomed or dragged
        self.drag_from = self.drag_origin = self.picking = None
        self.help = QLabel(CONTROLS, self)
        self.help.setObjectName('viewerOverlay')
        self.help.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.help.adjustSize()
        self.mark_timer = QTimer(self)
        self.mark_timer.setSingleShot(True)
        self.mark_timer.timeout.connect(self.clear_mark)

    def set_image(self, image, per_word=None):
        """Show a new reading. Where the pixels per word change, the word in
        the middle of the view stays there."""
        if per_word is not None and per_word != self.per_word:
            if self.pixmap and not self.auto_fit:
                half = self.width() / self.zoom / 2
                self.origin.setX((self.origin.x() + half) * per_word / self.per_word - half)
            self.per_word = per_word
        self.pixmap = QPixmap.fromImage(image)
        if self.auto_fit:
            self.fit()
        else:
            self.clamp()
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

    def show_words(self, x, y, width, height):
        """Bring a rectangle of words into view if none of it is showing.
        Used when something else selects a region; the crosshair itself
        never moves the view."""
        left, top = x * self.per_word, y
        span_x, span_y = self.width() / self.zoom, self.height() / self.zoom
        seen = QRectF(self.origin.x(), self.origin.y(), span_x, span_y)
        if self.auto_fit or seen.intersects(QRectF(left, top, width * self.per_word, height)):
            return
        self.origin = QPointF(left + width * self.per_word / 2 - span_x / 2, top + height / 2 - span_y / 2)
        self.clamp()
        self.update()

    def palette_at(self, position):
        if not self.pixmap:
            return None
        at = self.to_image(QPointF(position))
        if not (0 <= at.x() < self.pixmap.width() and 0 <= at.y() < self.pixmap.height()):
            return None
        return clut_word(int(at.x() / self.per_word), int(at.y()))

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
        texture page across or sixteen rows. The view stays where it is."""
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

    def word_rect(self, x, y, width, height):
        """Widget rectangle of a rectangle of words."""
        return QRectF((x * self.per_word - self.origin.x()) * self.zoom, (y - self.origin.y()) * self.zoom,
                      width * self.per_word * self.zoom, max(height * self.zoom, 1.))

    def row_rect(self, position):
        """Widget rectangle of the palette row at (word x, row)."""
        return self.word_rect(position[0], position[1], self.colours, 1)

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
            x = int(source.x() / step) * step
            while x <= source.right():
                at = int((x - source.x()) * self.zoom)
                painter.drawLine(at, 0, at, self.height())
                x += step
            for y in (0, 256, 512):
                at = int((y - source.y()) * self.zoom)
                painter.drawLine(0, at, self.width(), at)
        for x, y, width, height, colour in self.outlines:
            painter.setPen(QPen(QColor(*colour), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.word_rect(x, y, width, height))
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
    clut_picked = pyqtSignal(int)   # the palette the user put the crosshair on

    def __init__(self, vram, cluts=(), name='VRAM', embedded=False):
        """`cluts` are the CLUT words the open resource draws with. An
        embedded view sits inside another viewer, which shows its controls
        in a tooltip to keep the picture clear."""
        super().__init__()
        self.vram, self.name = np.ascontiguousarray(vram, np.uint16), name
        self.index_cache = None
        self.image = None
        self.canvas = VramCanvas()
        self.canvas.hovered.connect(self.hover)
        self.canvas.picked_clut.connect(self.pick)
        self.canvas.crosshair_moved.connect(self.pick)
        self.pixels = QComboBox()
        self.pixels.addItems([label for label, _, _ in PIXELS])
        self.pixels.setToolTip('How the words are cut into pixels. Textures and palettes sit together with\n'
                               'nothing marking which is which, so this chooses what to look for:\n'
                               '4-bit and 8-bit for indexed textures, 16-bit for palettes and pictures in\n'
                               'direct colour, 24-bit for decoded movie frames.')
        self.colouring = QComboBox()
        self.colouring.addItems([COLOUR_CLUT, COLOUR_GREY, COLOUR_FALSE])
        self.colouring.setToolTip('How an index is coloured in the 4-bit and 8-bit readings.')
        self.colouring_label = QLabel('Colours:')
        self.clut_box = QComboBox()
        self.clut_box.setEditable(True)
        self.clut_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.clut_box.setToolTip('The palette under the crosshair, as a CLUT word (row * 64 + x / 16).\n'
                                 'The list holds the palettes the open resource uses.')
        for word in sorted(set(cluts)):
            x, y = clut_xy(word)
            self.clut_box.addItem(f'0x{word:04X}  ({x}, {y})', word)
        self.cross = QCheckBox('Crosshair')
        self.cross.setToolTip('Mark the palette row. Arrow keys move it one palette or one row;\n'
                              'with Shift a texture page across or sixteen rows.')
        self.grid = QCheckBox('Page grid')
        self.top = QHBoxLayout()
        self.top.setContentsMargins(8, 4, 8, 2)
        for widget in (QLabel('Pixels:'), self.pixels, self.colouring_label, self.colouring,
                       QLabel('Crosshair CLUT:'), self.clut_box, self.cross, self.grid):
            self.top.addWidget(widget)
        self.top.addStretch(1)
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
        if embedded:
            self.canvas.help.hide()
            hint = QLabel('Controls')
            hint.setObjectName('panelTitle')
            hint.setToolTip(CONTROLS)
            bottom.insertWidget(1, hint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self.top)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(bottom)
        self.clut = find_palette(self.vram, 16, sorted(set(cluts)))
        self.clut_box.setEditText(f'0x{self.clut:04X}')
        self.cross.setChecked(True)
        self.canvas.crosshair = clut_xy(self.clut)
        self.pixels.currentIndexChanged.connect(self.depth_changed)
        self.colouring.currentIndexChanged.connect(self.render)
        self.cross.toggled.connect(self.toggle_crosshair)
        self.grid.toggled.connect(self.toggle_grid)
        self.clut_box.lineEdit().returnPressed.connect(self.clut_typed)
        self.clut_box.activated.connect(self.clut_chosen)
        self.render()

    def add_controls(self, *widgets):
        """Put another viewer's widgets on the top line, after this one's."""
        at = self.top.count() - 1
        for n, widget in enumerate(widgets):
            self.top.insertWidget(at + n, widget)

    def depth(self):
        return PIXELS[self.pixels.currentIndex()][1]

    def colours(self):
        """Length of the palette the crosshair marks: what the indexed
        reading on screen needs, or sixteen in the direct ones."""
        return 256 if self.depth() == 8 else 16

    def indices(self):
        if self.depth() == 8:
            return self.vram.view(np.uint8).reshape(HEIGHT, WIDTH * 2)
        if self.index_cache is None:
            self.index_cache = texels(self.vram)
        return self.index_cache

    def palette(self):
        x, y = clut_xy(self.clut)
        flat = self.vram.reshape(-1)
        return rgba(flat[(y * WIDTH + x + np.arange(self.colours())) % flat.size])

    def show_clut(self, word, flash=True):
        """Put the crosshair on a palette. The pixels are redrawn only if
        they are being read through it."""
        self.clut = int(word) & 0x7FFF
        self.clut_box.setEditText(f'0x{self.clut:04X}')
        if self.cross.isChecked():
            self.canvas.crosshair = clut_xy(self.clut)
        if self.depth() in (4, 8):
            self.render()
        else:
            self.canvas.update()
            self.describe()
        if flash:
            self.canvas.flash(self.clut)

    def pick(self, word):
        """The user chose a palette: show it and tell whoever is listening."""
        self.show_clut(word)
        x, y = clut_xy(self.clut)
        announce(f'CLUT 0x{self.clut:04X} @ ({x}, {y}) ({self.name})')
        self.clut_picked.emit(self.clut)

    def set_clut(self, word, announce=True):
        """Kept for callers that set a palette from outside."""
        self.pick(word) if announce else self.show_clut(word)

    def clut_typed(self):
        words = self.clut_box.currentText().split()
        try:
            self.pick(int(words[0], 16))
        except (ValueError, IndexError):
            self.info.setText(f'"{self.clut_box.currentText()}" is not a hexadecimal CLUT word')

    def clut_chosen(self, index):
        word = self.clut_box.itemData(index)
        if word is not None:
            self.pick(word)

    def depth_changed(self):
        indexed = self.depth() in (4, 8)
        self.colouring.setEnabled(indexed)
        self.colouring_label.setEnabled(indexed)
        self.render()

    def toggle_crosshair(self, on):
        self.canvas.crosshair = clut_xy(self.clut) if on else None
        if on:
            self.canvas.setFocus()
        self.canvas.update()

    def toggle_grid(self, on):
        self.canvas.show_grid = on
        self.canvas.update()

    def render(self, *_):
        depth, per_word = PIXELS[self.pixels.currentIndex()][1:]
        self.canvas.colours = self.colours()
        if depth == 16:
            pixels = rgba(self.vram).copy()
            pixels[..., 3] = 255
        elif depth == 24:
            # Three bytes a pixel: 682 of them across, two bytes over.
            count = WIDTH * 2 // 3
            rgb = self.vram.view(np.uint8).reshape(HEIGHT, WIDTH * 2)[:, :count * 3].reshape(HEIGHT, count, 3)
            pixels = np.dstack([rgb, np.full((HEIGHT, count), 255, np.uint8)])
        else:
            indices, colouring = self.indices(), self.colouring.currentText()
            if colouring == COLOUR_CLUT:
                palette = self.palette()
                palette[:, 3] = 255
                pixels = palette[indices]
            elif colouring == COLOUR_FALSE:
                pixels = FALSE_COLOURS[self.colours()][indices]
            else:
                grey = indices * 17 if depth == 4 else indices
                pixels = np.dstack([grey, grey, grey, np.full_like(grey, 255)])
            # The palette under the crosshair keeps its own colours, so it
            # can be seen for what it is in any indexed reading.
            x, y = clut_xy(self.clut)
            row = rgba(self.vram[y, x:x + self.colours()]).copy()
            row[:, 3] = 255
            pixels = np.ascontiguousarray(pixels)
            pixels[y, x * per_word:(x + len(row)) * per_word] = np.repeat(row, per_word, axis=0)
        pixels = np.ascontiguousarray(pixels)
        self.image = QImage(pixels.tobytes(), pixels.shape[1], pixels.shape[0], pixels.shape[1] * 4,
                            QImage.Format.Format_RGBA8888).copy()
        self.canvas.set_image(self.image, per_word)
        self.describe()

    def describe(self, extra=''):
        x, y = clut_xy(self.clut)
        text = f'{self.name}: {self.pixels.currentText()}'
        if self.depth() in (4, 8):
            text += f', {self.colouring.currentText().lower()}'
        text += f'  |  crosshair CLUT 0x{self.clut:04X} at ({x}, {y})'
        self.info.setText(text + extra)

    def hover(self, x, y):
        word = min(WIDTH - 1, int(x / self.canvas.per_word))
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
