"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QPoint
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
        layout.addLayout(tools)
        self.canvas = PixelCanvas()
        self.view = QScrollArea()
        self.view.setWidget(self.canvas)
        self.view.setWidgetResizable(False)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.view)
        self.image = None
        self.export_name = ''       # default file name, without extension
        if image is not None:
            self.set_image(image)

    def set_image(self, image):
        self.image = image
        self.canvas.set_image(qimage(image))
        self.dimensions.setText(f'{image.width} x {image.height}')
        self.scale_image()

    def scale_image(self):
        if self.image is None:
            return
        scale = fit_zoom(self.image.size, self.view.viewport().size()) if self.zoom.currentIndex() == 0 else [1, 1, 2, 4, 8][self.zoom.currentIndex()]
        self.canvas.set_zoom(scale)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom.currentIndex() == 0:
            self.scale_image()

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
