"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QImage, QPixmap, QFontDatabase, QSurfaceFormat
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QSpinBox, QSplitter, QListWidget, QPlainTextEdit,
    QGraphicsView, QGraphicsScene, QFileDialog, QMessageBox, QLineEdit)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from psx.graphics import texture_page, render_sprite



from gui.widgets.image_view import ImageView, text_view, qimage

class DialogueView(QWidget):
    def __init__(self, wfm):
        super().__init__()
        self.wfm = wfm
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText('Search dialogue...')
        self.search.textChanged.connect(self.filter)
        bar.addWidget(self.search)
        export = QPushButton('Export text...'); export.clicked.connect(self.export_text)
        bar.addWidget(export); layout.addLayout(bar)
        known = sum(c is not None for c in wfm.characters)
        layout.addWidget(QLabel(f'{len(wfm.dialogues)} entries | {known}/{len(wfm.glyphs)} recognized glyphs'))
        split = QSplitter()
        self.entries = QListWidget()
        for i, d in enumerate(wfm.dialogues):
            preview = ''.join(wfm.characters[word & 0xFFF] or '?' for word, _ in d.tokens if word < 0xFF00 and word & 0xFFF < len(wfm.characters))
            self.entries.addItem(f'{i:03d} | {preview[:70]}')
        split.addWidget(self.entries)
        right = QSplitter(Qt.Orientation.Vertical)
        self.rendered = ImageView()
        self.script = text_view("")
        right.addWidget(self.rendered)
        right.addWidget(self.script)
        right.setSizes([400, 160])
        split.addWidget(right)
        split.setSizes([330, 650])
        layout.addWidget(split, 1)
        layout.addWidget(QLabel("Glyph IDs are font-local, not ASCII. Control words are preserved below the preview."))
        self.entries.currentRowChanged.connect(self.select)
        if wfm.dialogues:
            self.entries.setCurrentRow(0)

    def select(self, index):
        if index < 0:
            return
        try:
            self.rendered.set_image(self.wfm.render(index))
            self.script.setPlainText(self.wfm.dialogues[index].script())
        except ValueError as exc:
            self.script.setPlainText(str(exc))

    def filter(self, text):
        for i, dialogue in enumerate(self.wfm.dialogues):
            self.entries.item(i).setHidden(text.casefold() not in dialogue.script().casefold())

    def export_text(self):
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(self, 'Export dialogue', 'dialogue.txt', 'Text (*.txt)')
        if path:
            try:
                Path(path).write_text('\n\n'.join(f'[{i:03d} @ {d.offset:04X}]\n{d.script()}' for i,d in enumerate(self.wfm.dialogues)), 'utf8')
            except OSError as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))
