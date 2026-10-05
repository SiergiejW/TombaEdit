"""The contents of an archive, each entry opened in the viewer for its kind."""
from pathlib import Path
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QStackedWidget, QFileDialog, QMessageBox)
from disc.reader import FormatError
from formats.archive import containers
from formats.images import tim
from gui.widgets.image_view import ImageView, text_view, file_stem

LAYOUTS = {'LVL': 'named entries by sector (LVL)', 'RAQ': 'named entries by sector (RAQ)',
           'counted': 'counted table of offsets and lengths', 'pairs': 'table of offsets and lengths',
           'sectors': 'table of sectors and lengths', 'offsets': 'table of offsets',
           None: 'no index; found by their headers'}
EXTENSIONS = {'TIM': '.tim', 'VAB': '.vab', 'VAB header': '.vh', 'VAB body': '.vb', 'SEQ': '.seq', 'TMD': '.tmd',
              'MIDI': '.mid', 'Save icon': '.sc', 'EXE': '.exe'}


class ContainerView(QWidget):
    """A list of what a file holds beside a viewer for the chosen entry.

    `banks` is a callable giving [(name, bank)] to play sequences on; the
    archive's own banks are offered ahead of them."""

    def __init__(self, layout_name, items, name='', banks=None, labels=None, save_labels=None):
        super().__init__()
        self.items, self.name = list(items), name
        self.banks, self.labels, self.save_labels = banks, labels, save_labels
        self.shown = list(range(len(self.items)))
        self.vram = None
        self.model_view = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        bar = QHBoxLayout()
        kinds = {}
        for item in self.items:
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
        self.filter = QComboBox()
        self.filter.addItem(f'All ({len(self.items)})', '')
        for kind, count in sorted(kinds.items(), key=lambda pair: (pair[0] == 'Data', pair[0])):
            self.filter.addItem(f'{kind} ({count})', kind)
        self.filter.currentIndexChanged.connect(self.apply_filter)
        bar.addWidget(QLabel('Show:'))
        bar.addWidget(self.filter)
        summary = QLabel(f'{len(self.items):,} entries | {LAYOUTS.get(layout_name, layout_name)}')
        summary.setObjectName('panelTitle')
        bar.addWidget(summary, 1)
        export = QPushButton('Export entry...'); export.clicked.connect(self.export_entry)
        export_all = QPushButton('Export all shown...'); export_all.clicked.connect(self.export_all)
        bar.addWidget(export); bar.addWidget(export_all)
        outer.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Entry', 'Type', 'Offset', 'Bytes', 'Contents'])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setStyleSheet('QTableWidget::item:selected {background-color: #555555; color: white;} '
                                 'QTableWidget::item:selected:!active {background-color: #494949; color: white;}')
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column, mode in enumerate((QHeaderView.ResizeMode.Interactive, QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.Stretch)):
            header.setSectionResizeMode(column, mode)
        self.table.setColumnWidth(0, 170)
        self.table.currentCellChanged.connect(lambda row, *rest: self.choose(row))
        split.addWidget(self.table)
        self.stack = QStackedWidget()
        self.placeholder = text_view('Select an entry.')
        self.stack.addWidget(self.placeholder)
        self.current = None
        split.addWidget(self.stack)
        split.setStretchFactor(0, 2); split.setStretchFactor(1, 3)
        split.setSizes([460, 640])
        outer.addWidget(split, 1)
        # Open on the first kind that has a viewer of its own.
        first = next((i for i in range(1, self.filter.count()) if self.filter.itemData(i) != 'Data'), 0)
        self.filter.setCurrentIndex(first if first and kinds.get('Data', 0) * 2 > len(self.items) else 0)
        self.apply_filter()

    def apply_filter(self):
        wanted = self.filter.currentData()
        self.shown = [i for i, item in enumerate(self.items) if not wanted or item.kind == wanted]
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.shown))
        for row, index in enumerate(self.shown):
            item = self.items[index]
            cells = (item.name, item.kind + (f' ({item.packed})' if item.packed else ''), f'0x{item.offset:06X}',
                     f'{item.size:,}', item.note)
            for column, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                if column in (2, 3):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, cell)
        self.table.blockSignals(False)
        if self.shown:
            # Open on the first entry there is a viewer for.
            row = next((r for r, index in enumerate(self.shown) if self.items[index].kind not in ('Data', 'VAB body')), 0)
            self.table.blockSignals(True)
            self.table.setCurrentCell(row, 0)
            self.table.blockSignals(False)
            self.choose(row)
        else:
            self.show_widget(self.placeholder)

    def show_widget(self, widget):
        if self.current is not None and self.current is not widget:
            self.stack.removeWidget(self.current)
            if self.current is not self.placeholder and self.current is not self.model_view:
                self.current.deleteLater()
        if self.stack.indexOf(widget) < 0:
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)
        self.current = widget

    def all_tims(self):
        """VRAM with every picture of the archive uploaded, for its models."""
        if self.vram is None:
            self.vram = np.zeros((512, 1024), np.uint16)
            for item in self.items:
                if item.kind == 'TIM':
                    try:
                        tim.upload(self.vram, tim.parse(item.load()))
                    except FormatError:
                        continue
        return self.vram

    def choose(self, row):
        if not 0 <= row < len(self.shown):
            return
        item = self.items[self.shown[row]]
        try:
            data = item.load()
            if self.table.item(row, 4) is not None and item.note:
                self.table.item(row, 4).setText(item.note)
            self.show_widget(self.viewer(item, data))
        except Exception as exc:
            self.show_widget(text_view(f'{item.name}: {exc}'))
        print(f'selected: {self.name} entry {item.name} | {item.kind} | offset 0x{item.offset:X}, {item.size:,} bytes'
              + (f' | {item.note}' if item.note else ''))

    def viewer(self, item, data):
        stem = file_stem(f'{Path(self.name).stem} {item.name}')
        if item.kind == 'TIM':
            from formats.images.tim_viewer import TimView
            view = TimView(tim.parse(data))
            view.export_name = stem
            return view
        if item.kind == 'Save icon':
            from formats.images import save_icon
            view = ImageView(save_icon.sheet(data))
            view.export_name = stem
            return view
        if item.kind in ('VAB', 'SEQ', 'MIDI'):
            from formats.audio.audio_viewer import AudioView
            from formats.audio import sources, vab, smf
            if item.kind == 'VAB':
                found = [sources.BankSource(item.name, vab.whole(data)[0], self.labels)]
            else:
                music = smf.to_seq(data) if item.kind == 'MIDI' else data
                own = [(other.name, vab.whole(other.data)[0]) for other in self.items if other.kind == 'VAB']
                found = sources.sequence_sources(music, item.name, own + (self.banks() if self.banks else []),
                                                 labels=self.labels)
            return AudioView(found, item.name, self.labels, self.save_labels, stem)
        if item.kind == 'TMD':
            from formats.models import tmd
            from formats.models.wmd_viewer import ModelView
            if self.model_view is None:
                self.model_view = ModelView()
            self.model_view.export_name = stem
            meshes = tmd.parse(data)
            self.model_view.set_data(meshes, self.all_tims(), level=False, spread=tmd.jointed(meshes))
            return self.model_view
        from gui.widgets.hex_view import HexView
        return HexView(data, note=f'{item.packed}-packed, {item.size:,} bytes stored' if item.packed else '')

    def export_entry(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.shown):
            return
        item = self.items[self.shown[row]]
        name = file_stem(item.name.replace('+', 'at ')) + ('' if '.' in item.name else EXTENSIONS.get(item.kind, '.bin'))
        path, _ = QFileDialog.getSaveFileName(self, 'Export entry', name, 'All files (*)')
        if path:
            try:
                Path(path).write_bytes(self.stored(item))
            except (OSError, FormatError) as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))

    @staticmethod
    def stored(item):
        """An entry as a file of its own. A bank is written header first
        with its waveforms behind it, which is the .VAB layout."""
        return bytes(item.load())

    def export_all(self):
        folder = QFileDialog.getExistingDirectory(self, 'Export entries to folder')
        if not folder:
            return
        written, failed = 0, 0
        for index in self.shown:
            item = self.items[index]
            name = file_stem(item.name.replace('+', 'at ')) + ('' if '.' in item.name else EXTENSIONS.get(item.kind, '.bin'))
            try:
                (Path(folder) / name).write_bytes(self.stored(item))
                written += 1
            except (OSError, FormatError):
                failed += 1
        QMessageBox.information(self, 'Export entries', f'{written:,} entries written to {folder}.'
                                + (f' {failed:,} could not be written.' if failed else ''))
