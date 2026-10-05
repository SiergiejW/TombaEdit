"""Section scene inspection using the standard model viewer controls."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QPushButton, QStyle
from formats.models.wmd_viewer import ModelView

# The game steps animation scripts once per frame at 30 frames a second.
TICK_MS = 33


class LevelView(ModelView):
    open_resource = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.scene = None
        self.animated = []      # [entry index, step, ticks left]
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
        self.collision_action = self.toggle_action(
            QStyle.StandardPixmap.SP_FileDialogListView, 'Collision', self.toggle_collision, False,
            'Draw the WHM collision spans over the level: green walkable surfaces, '
            'magenta surfaces with special attributes and orange solid ranges.\n'
            'In a town, outline the walkable cells of its map instead.')
        self.town_action = self.toggle_action(
            QStyle.StandardPixmap.SP_FileDialogInfoView, 'Town Map', self.toggle_town, False,
            'Tint a town picture by its cell map: where characters can walk, and the '
            'cells with bit 7 set, shown in blue.')
        self.animate_action = self.toggle_action(
            QStyle.StandardPixmap.SP_MediaPlay, 'Animate', self.toggle_animation, True,
            'Play the animation scripts of placed sprites.')
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.advance)

    def toggle_action(self, icon, title, callback, checked, tip):
        action = QAction(self.style().standardIcon(icon), title, self)
        action.setCheckable(True)
        action.setChecked(checked)
        action.setToolTip(tip)
        action.toggled.connect(callback)
        self.toolbar.insertAction(self.origin_action, action)
        return action

    def set_scene(self, scene):
        self.timer.stop()
        self.scene = scene
        self.set_data([entry.mesh for entry in scene.entries], scene.vram, 0x5080,
                      {i: e.name for i, e in enumerate(scene.entries)})
        if any(e.alternative is not None for e in scene.entries):
            self.canvas.view_angles = (0.0, 0.0)    # a town picture is viewed square on
        self.canvas.lines = scene.collision
        self.canvas.show_lines = self.collision_action.isChecked()
        self.collision_action.setEnabled(scene.collision is not None)
        self.town_action.setEnabled(any(e.alternative is not None for e in scene.entries))
        self.toggle_town(self.town_action.isChecked())
        self.animated = [[i, 0, e.frames[0][1]] for i, e in enumerate(scene.entries) if e.frames]
        self.assets.clear()
        for a in scene.resources:
            self.assets.addItem(a.label, a)
        self.notice.setText(' | '.join(scene.notes))
        self.apply_filter()
        self.canvas.fit(animate=False)
        resolved = sum(e.active and e.category in ('Models', 'Sprites') for e in scene.entries)
        total = sum(e.active and e.placement is not None for e in scene.entries)
        self.canvas.stats_label.setText(f'{resolved}/{total} placed visuals resolved | '
                                        f'{len(self.animated)} animated\n'
                                        'F: frame selected | Double-click a row: frame it')
        self.canvas.stats_label.adjustSize()
        self.toggle_animation(self.animate_action.isChecked())

    def toggle_collision(self, value):
        self.canvas.show_lines = value
        self.canvas.update()

    def toggle_town(self, value):
        if self.scene is None:
            return
        for index, entry in enumerate(self.scene.entries):
            if entry.alternative is not None:
                self.canvas.set_mesh(index, entry.alternative if value else entry.mesh)

    def toggle_animation(self, value):
        if value and self.animated and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()

    def advance(self):
        for state in self.animated:
            state[2] -= 1
            if state[2] > 0:
                continue
            index, step, _ = state
            frames = self.scene.entries[index].frames
            step = (step + 1) % len(frames)
            state[1], state[2] = step, frames[step][1]
            self.canvas.set_mesh(index, frames[step][0])

    def showEvent(self, event):
        super().showEvent(event)
        self.toggle_animation(self.animate_action.isChecked())

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

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

    def describe(self, row):
        if self.scene is None or not 0 <= row < len(self.scene.entries):
            return super().describe(row)
        e = self.scene.entries[row]
        if not e.placement:
            return f'{e.name} | {e.source.label}'
        return (f'{e.name} | {e.category} | position {e.placement.position} | '
                f'APD offset 0x{e.placement.offset:04X} | {e.note}')

    def picked_entry(self, selected):
        if selected is None:
            return
        self.objects.blockSignals(True)     # selecting the row would drop the polygon
        self.objects.setCurrentCell(selected[0], 1)
        self.objects.blockSignals(False)
        self.canvas.selected_model = selected[0]
        entry = self.scene.entries[selected[0]]
        if entry.mesh.image is None and selected[1]['page'] >= 0:
            # Geometry and models: the polygon's page with its UVs outlined.
            self.show_polygon(selected, announce=False)
            self.details.setPlainText(f'{entry.name}\n{entry.source.label}\n\n' + self.details.toPlainText())
        else:
            self.show_entry(selected[0])
        print('selected: ' + self.describe(selected[0]))
        self.canvas.update()

    def open_asset(self):
        asset = self.assets.currentData()
        if asset is not None:
            self.open_resource.emit(asset)
