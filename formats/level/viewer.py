"""Section scene inspection using the standard model viewer controls."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QPushButton, QTableWidgetItem
from formats.models.wmd_viewer import ModelView


class LevelView(ModelView):
    open_resource = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.scene = None
        self.filter = QComboBox()
        self.filter.addItems(['Whole level', 'Geometry', 'Models', 'Sprites', 'Unresolved'])
        self.scope = QComboBox()
        self.scope.addItems(['This section', 'All loaded APD banks'])
        self.assets = QComboBox()
        open_button = QPushButton('Open asset')
        open_button.clicked.connect(self.open_asset)
        row = QHBoxLayout()
        for w in (QLabel('Show:'), self.filter, self.scope, QLabel('Loaded assets:'), self.assets, open_button):
            row.addWidget(w)
        self.layout().insertLayout(0, row)
        self.notice = QLabel('Select a section to load its level.')
        self.notice.setWordWrap(True)
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout().insertWidget(1, self.notice)
        self.filter.currentIndexChanged.connect(self.apply_filter)
        self.scope.currentIndexChanged.connect(self.apply_filter)
        self.objects.horizontalHeaderItem(1).setText('Scene object')
        self.objects.cellClicked.connect(self.show_entry)
        self.canvas.picked.connect(self.picked_entry)
        self.spread_action.setVisible(False)

    def set_scene(self, scene):
        self.scene = scene
        self.set_data([entry.mesh for entry in scene.entries], scene.vram, 0x5080,
                      {i: e.name for i, e in enumerate(scene.entries)})
        self.assets.clear()
        for a in scene.resources:
            self.assets.addItem(a.label, a)
        self.notice.setText(' | '.join(scene.notes))
        self.apply_filter()
        self.canvas.fit(animate=False)
        resolved = sum(e.active and e.category in ('Models', 'Sprites') for e in scene.entries)
        total = sum(e.active and e.placement is not None for e in scene.entries)
        self.canvas.stats_label.setText(f'{resolved}/{total} placed visuals resolved | F: frame selected\n'
                                       'Double-click an object to frame it')
        self.canvas.stats_label.adjustSize()

    def apply_filter(self):
        if self.scene is None:
            return
        category = self.filter.currentText()
        self.objects.blockSignals(True)
        visible = set()
        for i, e in enumerate(self.scene.entries):
            show = (self.scope.currentIndex() == 1 or e.active) and (category == 'Whole level' or e.category == category)
            self.objects.setRowHidden(i, not show)
            self.objects.item(i, 0).setCheckState(Qt.CheckState.Checked if show else Qt.CheckState.Unchecked)
            if show:
                visible.add(i)
        self.objects.blockSignals(False)
        self.canvas.visible = visible
        self.canvas.selected = None
        self.canvas.selected_model = None
        self.canvas.update()

    def show_all(self):
        self.filter.setCurrentIndex(0)
        self.apply_filter()
        self.canvas.fit()

    def show_entry(self, row, column=0):
        if self.scene is None or not 0 <= row < len(self.scene.entries):
            return
        e = self.scene.entries[row]
        text = f'{e.name}\n{e.category}\n{e.source.label}\n\n{e.note}'
        if e.placement:
            p = e.placement
            text += (f'\n\nPosition: {p.position}\nLayer: {p.layer}\nType: {p.kind:02X}'
                     f'\nVariant: {p.variant:02X}\nAPD offset: 0x{p.offset:04X}'
                     f'\nRelative placement: {p.relative}\nRecord: {p.raw.hex(" ").upper()}')
        self.details.setPlainText(text)
        if e.mesh.image is not None:
            self.uv.set_image(e.mesh.image)

    def model_selected(self, row, column, old_row, old_column):
        super().model_selected(row, column, old_row, old_column)
        self.show_entry(row)

    def picked_entry(self, selected):
        if selected is not None:
            self.objects.setCurrentCell(selected[0], 1)
            self.show_entry(selected[0])

    def open_asset(self):
        asset = self.assets.currentData()
        if asset is not None:
            self.open_resource.emit(asset)
