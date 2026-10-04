"""Sprite bank, frame assembly and persistent comparison selection."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
    QFileDialog, QMessageBox, QComboBox, QCheckBox, QTabWidget)
from gui.widgets.image_view import ImageView, qimage, text_view
from psx.graphics import render_sprite


class SpriteView(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, frames, vram, page_base=0, renderer=None):
        super().__init__()
        self.frames, self.vram = frames, vram
        self.renderer = renderer
        self.cache = {}
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.frame = QSpinBox()
        self.frame.setRange(0, max(0, len(frames) - 1))
        self.frame.valueChanged.connect(self.select)
        tools.addWidget(QLabel(f'{len(frames)} frames | Frame:'))
        tools.addWidget(self.frame)
        self.page_base = QSpinBox()
        self.page_base.setRange(0, 31)
        self.page_base.setValue(page_base)
        tools.addWidget(QLabel('Texture page offset:'))
        tools.addWidget(self.page_base)
        self.page_base.valueChanged.connect(self.rebuild)
        self.play = QPushButton('Play')
        self.play.setCheckable(True)
        self.play.toggled.connect(self.animate)
        tools.addWidget(self.play)
        self.fps = QSpinBox(); self.fps.setRange(1, 60); self.fps.setValue(10)
        self.fps.valueChanged.connect(lambda: self.timer.setInterval(1000 // self.fps.value()))
        tools.addWidget(QLabel('Preview FPS:')); tools.addWidget(self.fps)
        tools.addStretch()
        layout.addLayout(tools)
        export_bar = QHBoxLayout()
        self.export_mode = QComboBox()
        self.export_mode.addItems(['Current PNG', 'Selected PNGs', 'All PNGs', 'Sprite sheet + JSON', 'Animated GIF'])
        export_bar.addWidget(self.export_mode)
        self.keep_origin = QCheckBox('Keep sprite origin'); self.keep_origin.setChecked(True)
        export_bar.addWidget(self.keep_origin)
        export = QPushButton('Export sprites...'); export.clicked.connect(self.export)
        export_bar.addWidget(export); export_bar.addStretch()
        layout.addLayout(export_bar)
        split = QSplitter()
        self.bank = QListWidget()
        self.bank.setViewMode(QListWidget.ViewMode.IconMode)
        self.bank.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.bank.setIconSize(QSize(80, 80)); self.bank.setGridSize(QSize(100, 108))
        self.bank.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.bank.currentRowChanged.connect(lambda i: self.frame.setValue(max(0, i)))
        self.bank.itemSelectionChanged.connect(self.selected)
        split.addWidget(self.bank)
        right = QTabWidget()
        self.image = ImageView(); self.image.zoom.setCurrentIndex(3)
        right.addTab(self.image, 'Frame')
        self.selection = ImageView(); self.selection.zoom.setCurrentIndex(0)
        right.addTab(self.selection, 'Selected frames')
        self.details = text_view(''); right.addTab(self.details, 'Frame records')
        split.addWidget(right); split.setSizes([440, 420])
        layout.addWidget(split, 1)
        note = QLabel('Ctrl/Shift-click keeps a selection for comparison and export. Playback uses the chosen FPS, not game animation timing.')
        note.setWordWrap(True); layout.addWidget(note)
        self.timer = QTimer(self); self.timer.timeout.connect(self.advance)
        self.thumb_timer = QTimer(self); self.thumb_timer.timeout.connect(self.make_thumbnails)
        self.rebuild()

    def frame_image(self, index, origin=False):
        if index not in self.cache:
            self.cache[index] = self.renderer(index) if self.renderer else render_sprite(self.frames[index], self.vram, self.page_base.value())
        image = self.cache[index]
        if not origin or not self.frames[index]:
            return image
        # Fixed origin keeps frames aligned when exported or animated.
        bounds = [p for frame in self.frames for p in frame]
        left = min([p[13] for p in bounds] + [0]); top = min([p[14] for p in bounds] + [0])
        right = max([p[13] + p[9] for p in bounds] + [1]); bottom = max([p[14] + p[10] for p in bounds] + [1])
        out = Image.new('RGBA', (right-left, bottom-top))
        f = self.frames[index]
        out.alpha_composite(image, (min(p[13] for p in f)-left, min(p[14] for p in f)-top))
        return out

    def rebuild(self):
        self.cache.clear(); self.bank.blockSignals(True); self.bank.clear()
        for i in range(len(self.frames)):
            self.bank.addItem(QListWidgetItem(f'{i:03d}'))
        self.bank.blockSignals(False)
        self.next_thumb = 0; self.thumb_timer.start(0)
        self.select(self.frame.value())

    def make_thumbnails(self):
        for i in range(self.next_thumb, min(len(self.frames), self.next_thumb + 8)):
            image = self.frame_image(i)
            self.bank.item(i).setIcon(QIcon(QPixmap.fromImage(qimage(image))))
        self.next_thumb += 8
        if self.next_thumb >= len(self.frames):
            self.thumb_timer.stop()

    def select(self, index):
        if not self.frames:
            return
        self.image.set_image(self.frame_image(index))
        rows = [f'Frame {index} | {len(self.frames[index])} parts']
        for n, p in enumerate(self.frames[index]):
            rows.append(f'{n:02d} | XY {p[13], p[14]} | size {p[9], p[10]} | CLUT {p[2]:04X} | page {p[5]:02X} | UV {p[0],p[1]} {p[3],p[4]} {p[7],p[8]} {p[11],p[12]}')
        self.details.setPlainText('\n'.join(rows))

    def selected(self):
        indices = sorted(self.bank.row(item) for item in self.bank.selectedItems())
        self.selection_changed.emit(indices)
        if indices:
            self.selection.set_image(self.sheet(indices)[0])

    def restore_state(self, indices):
        self.bank.blockSignals(True)
        for i in indices:
            if 0 <= i < self.bank.count():
                self.bank.item(i).setSelected(True)
        self.bank.blockSignals(False)
        self.selected()

    def sheet(self, indices):
        images = [self.frame_image(i, self.keep_origin.isChecked()) for i in indices]
        cw, ch = max(im.width for im in images)+4, max(im.height for im in images)+4
        cols = max(1, math.ceil(math.sqrt(len(images))))
        out = Image.new('RGBA', (cw*cols, ch*math.ceil(len(images)/cols)))
        entries = []
        for n, (index, im) in enumerate(zip(indices, images)):
            x,y = (n%cols)*cw, (n//cols)*ch
            out.alpha_composite(im, (x,y))
            entries.append(dict(frame=index, x=x, y=y, width=im.width, height=im.height))
        return out, entries

    def animate(self, playing):
        self.play.setText('Pause' if playing else 'Play')
        if playing:
            self.timer.start(1000 // self.fps.value())
        else:
            self.timer.stop()

    def advance(self):
        indices = sorted(self.bank.row(i) for i in self.bank.selectedItems()) or list(range(len(self.frames)))
        if indices:
            current = self.frame.value()
            self.frame.setValue(indices[(indices.index(current)+1)%len(indices)] if current in indices else indices[0])

    def hideEvent(self, event):
        self.play.setChecked(False)
        super().hideEvent(event)

    def export(self):
        mode = self.export_mode.currentIndex()
        indices = sorted(self.bank.row(i) for i in self.bank.selectedItems())
        if mode == 1 and not indices:
            QMessageBox.information(self, 'Select frames', 'Select one or more frames in the bank first.'); return
        indices = indices or list(range(len(self.frames)))
        try:
            if mode in (1,2):
                directory = QFileDialog.getExistingDirectory(self, 'Export PNG frames')
                if directory:
                    chosen = indices if mode == 1 else range(len(self.frames))
                    for i in chosen:
                        self.frame_image(i, self.keep_origin.isChecked()).save(Path(directory)/f'frame_{i:04d}.png')
                return
            suffix = 'gif' if mode == 4 else 'png'
            path, _ = QFileDialog.getSaveFileName(self, 'Export sprites', f'sprites.{suffix}', f'{suffix.upper()} (*.{suffix})')
            if not path:
                return
            if mode == 0:
                self.frame_image(self.frame.value(), self.keep_origin.isChecked()).save(path)
            elif mode == 3:
                image, entries = self.sheet(indices); image.save(path)
                Path(path).with_suffix('.json').write_text(json.dumps(dict(frames=entries), indent=2), 'utf8')
            else:
                frames = [self.frame_image(i, True) for i in indices]
                frames[0].save(path, save_all=True, append_images=frames[1:], duration=round(1000/self.fps.value()), loop=0, disposal=2)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))
