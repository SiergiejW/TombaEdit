"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QImage, QPixmap, QFontDatabase, QSurfaceFormat
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QSpinBox, QSplitter, QListWidget, QPlainTextEdit,
    QGraphicsView, QGraphicsScene, QFileDialog, QMessageBox)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from psx.graphics import texture_page, render_sprite



from gui.widgets.image_view import ImageView, text_view, qimage

class VramView(QWidget):
    def __init__(self, vram):
        super().__init__()
        self.vram = vram
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["All 4-bit texture pages", "16-bit VRAM overview", "4-bit texture page", "8-bit texture page", "16-bit texture page"])
        bar.addWidget(self.mode)
        self.page = QSpinBox()
        self.page.setRange(0, 31)
        self.clut = QSpinBox()
        self.clut.setRange(0, 32767)
        self.clut.setDisplayIntegerBase(16)
        self.clut.setPrefix("0x")
        self.clut.setValue(0x7800)
        bar.addWidget(QLabel("Page:")); bar.addWidget(self.page)
        bar.addWidget(QLabel("CLUT:")); bar.addWidget(self.clut)
        bar.addStretch()
        layout.addLayout(bar)
        self.image = ImageView()
        self.image.zoom.setCurrentIndex(0)
        layout.addWidget(self.image)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.page.valueChanged.connect(self.refresh)
        self.clut.valueChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        from psx.graphics import rgba
        mode = self.mode.currentIndex()
        self.page.setEnabled(mode >= 2)
        self.clut.setEnabled(mode in (0, 2, 3))
        if mode == 0:
            image = Image.new('RGBA', (8 * 256, 4 * 256), (24, 24, 24, 255))
            for page in range(32):
                image.alpha_composite(texture_page(self.vram, page, self.clut.value()),
                                      ((page % 8) * 256, (page // 8) * 256))
        elif mode == 1:
            image = Image.fromarray(rgba(self.vram))
        else:
            image = texture_page(self.vram, self.page.value() | ((mode - 2) << 7), self.clut.value())
        self.image.set_image(image)
