"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QImage, QPixmap, QFontDatabase, QSurfaceFormat
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QSpinBox, QSplitter, QListWidget, QPlainTextEdit,
    QGraphicsView, QGraphicsScene, QFileDialog, QMessageBox, QScrollArea)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from psx.graphics import texture_page, render_sprite



def text_view(text):
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    view.setPlainText(text)
    return view

def file_stem(text, fallback='export'):
    """`text` made safe to offer as a file name."""
    cleaned = ''.join(c if c.isalnum() or c in ' -_.()' else ' ' for c in text or '')
    return ' '.join(cleaned.split())[:120] or fallback


def qimage(image):
    image = image.convert("RGBA")
    return QImage(image.tobytes(), image.width, image.height, image.width * 4,
                  QImage.Format.Format_RGBA8888).copy()

from gui.widgets.pixel_canvas import PixelCanvas, fit_zoom

class ImageView(QWidget):
    def __init__(self, image=None):
        super().__init__()
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.zoom = QComboBox()
        self.zoom.addItems(["Fit", "100%", "200%", "400%", "800%"])
        self.zoom.setCurrentIndex(2)
        self.zoom.currentIndexChanged.connect(self.scale_image)
        save = QPushButton("Export PNG...")
        save.clicked.connect(self.save)
        self.dimensions = QLabel()
        tools.addWidget(QLabel("Zoom:"))
        tools.addWidget(self.zoom)
        tools.addWidget(self.dimensions)
        tools.addStretch()
        tools.addWidget(save)
        self.tools = tools
        layout.addLayout(tools)
        self.canvas = PixelCanvas()
        self.view = QScrollArea()
        self.view.setWidget(self.canvas)
        self.view.setWidgetResizable(False)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.view)
        from gui.widgets.zoom_buttons import ZoomButtons
        ZoomButtons(self.view.viewport(), lambda: self.step_zoom(1), lambda: self.step_zoom(-1), self.fit_view)
        self.image = None
        self.export_name = ''       # default file name, without extension
        if image is not None:
            self.set_image(image)

    def set_image(self, image, preserve_view=False, subject=None):
        """Show a picture. `subject` says what it is a picture of: the same
        subject drawn again (with outlines, through another palette) keeps
        the zoom and scroll it is being looked at with, and a new one is
        framed afresh."""
        bars = (self.view.horizontalScrollBar(), self.view.verticalScrollBar())
        scroll = [bar.value() for bar in bars]
        if subject is not None:
            preserve_view = self.image is not None and subject == getattr(self, 'subject', None)
            self.subject = subject
        self.image = image
        self.canvas.set_image(qimage(image))
        self.dimensions.setText(f'{image.width} x {image.height}')
        if not preserve_view:
            self.scale_image()
        else:
            for bar, value in zip(bars, scroll):
                bar.setValue(value)

    def scale_image(self):
        if self.image is None:
            return
        if self.zoom.currentIndex() == 0:
            # Fit fills the pane: the largest scale at which the whole
            # picture shows, whatever that comes to.
            room = self.view.maximumViewportSize()
            self.canvas.set_zoom(min((room.width() - 4) / max(1, self.image.width),
                                     (room.height() - 4) / max(1, self.image.height)), exact=True)
        else:
            self.canvas.set_zoom([1, 1, 2, 4, 8][self.zoom.currentIndex()])

    def fit_view(self):
        self.zoom.setCurrentIndex(0)
        self.scale_image()

    def step_zoom(self, direction):
        """One notch in or out from wherever the picture is, the middle of the pane staying put."""
        if self.image is None:
            return
        bars = (self.view.horizontalScrollBar(), self.view.verticalScrollBar())
        before = self.canvas.zoom
        middle = [(bar.value() + bar.pageStep() / 2) / before for bar in bars]
        self.canvas.zoom_by(direction)
        after = self.canvas.zoom
        # The box offers 100% to 800% only: it shows the nearest, and is no longer on Fit, which would
        # fit the picture again at the next resize.
        nearest = min(range(1, 5), key=lambda i: abs([1, 1, 2, 4, 8][i] - after))
        self.zoom.blockSignals(True)
        self.zoom.setCurrentIndex(nearest)
        self.zoom.blockSignals(False)

        def keep():
            for bar, centre in zip(bars, middle):
                bar.setValue(int(centre * after - bar.pageStep() / 2))
        QTimer.singleShot(0, keep)

    def show_area(self, left, top, right, bottom):
        """Scroll so the given pixels are centred, at the zoom chosen; Fit
        shows them in the whole picture."""
        if self.image is None:
            return
        scale = self.canvas.zoom
        for bar, middle in ((self.view.horizontalScrollBar(), (left + right + 1) / 2),
                            (self.view.verticalScrollBar(), (top + bottom + 1) / 2)):
            bar.setValue(int(middle * scale - bar.pageStep() / 2))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom.currentIndex() == 0:
            # Once the pane has its new size, the picture is fitted to it.
            QTimer.singleShot(0, self.scale_image)

    def save(self):
        if self.image is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export image", file_stem(self.export_name, 'preview') + '.png',
                                              "PNG (*.png)")
        if path:
            try:
                self.image.save(path)
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", str(exc))
