"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image, ImageDraw
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
        self.mode.addItems(["All pages (grayscale)", "All pages (CLUT)",
                            "16-bit VRAM overview", "4-bit page (grayscale)",
                            "4-bit page (CLUT)", "8-bit texture page", "16-bit texture page"])
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
        self.page.setEnabled(mode >= 3)
        self.clut.setEnabled(mode in (1, 2, 4, 5))
        def gray_page(page):
            x, y = (page & 15) * 64, ((page >> 4) & 1) * 256
            words = self.vram[y:y + 256, x:x + 64]
            pixels = np.empty((256, 256), dtype=np.uint8)
            for n in range(4):
                pixels[:, n::4] = ((words >> (n * 4)) & 15).astype(np.uint8) * 17
            return Image.fromarray(pixels, 'L').convert('RGBA')
        if mode in (0, 1):
            image = Image.new('RGBA', (8 * 256, 4 * 256), (24, 24, 24, 255))
            for page in range(32):
                image.alpha_composite(gray_page(page) if mode == 0 else
                                      texture_page(self.vram, page, self.clut.value()),
                                      ((page % 8) * 256, (page // 8) * 256))
        elif mode == 2:
            image = Image.fromarray(rgba(self.vram))
            cx, cy = (self.clut.value() & 63) * 16, (self.clut.value() >> 6) & 511
            ImageDraw.Draw(image).rectangle((cx, cy, cx + 15, cy), outline='red', width=2)
        elif mode == 3:
            image = gray_page(self.page.value())
        else:
            image = texture_page(self.vram, self.page.value() | ((mode - 4) << 7), self.clut.value())
        self.image.set_image(image)
