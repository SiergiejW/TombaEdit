"""Section scene inspection using the standard model viewer controls."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QPushButton, QStyle, QTabWidget
from formats.models.wmd_viewer import ModelView
from formats.collision.inspector import CollisionInspector

# The game steps animation scripts once per frame at 30 frames a second.
TICK_MS = 33


class LevelView(ModelView):
    open_resource = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.scene = None
        self.animated = []      # [entry index, step, ticks left]
        self.filter = QComboBox()
        self.filter.addItems(['Whole level', 'Geometry', 'Models', 'Sprites', 'Backgrounds', 'Unresolved'])
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
        # Keep the familiar model list and viewport. Collision records occupy
        # a second page of that same side panel, not a second scene viewport.
        left_layout = self.objects.parentWidget().layout()
        left_layout.itemAt(0).widget().setText('Scene inspection')
        self.inspect_tabs = QTabWidget()
        left_layout.replaceWidget(self.objects, self.inspect_tabs)
        self.inspect_tabs.addTab(self.objects, 'Objects')
        self.collision_inspector = CollisionInspector(self)
        self.inspect_tabs.addTab(self.collision_inspector, 'Collision')
        object_buttons = left_layout.itemAt(2).layout()
        self.inspect_tabs.currentChanged.connect(lambda index: [
            object_buttons.itemAt(i).widget().setVisible(index == 0)
            for i in range(object_buttons.count()) if object_buttons.itemAt(i).widget()])
        self.canvas.line_picker = lambda p: (self.inspect_tabs.currentIndex() == 1 and
                                            self.collision_inspector.pick(p))
        for column in (2, 3, 4):
            self.objects.setColumnHidden(column, True)
        self.objects.setMinimumWidth(350)
        self.objects.cellClicked.connect(self.show_entry)
        self.canvas.picked.connect(self.picked_entry)
        self.spread_action.setVisible(False)
        self.canvas.highlight = False
        gif = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), 'Save GIF', self)
        gif.setToolTip('Save one pass of the selected sprite\'s animation as a GIF.')
        gif.triggered.connect(self.save_gif)
        self.toolbar.addAction(gif)
        self.collision_action = self.toggle_action(
            QStyle.StandardPixmap.SP_FileDialogListView, 'Collision', self.toggle_collision, False,
            'Draw WHM boundaries: green floors, blue ceilings, magenta side boundaries '
            'and orange solid regions. The Collision side panel filters and inspects records.\n'
            'In a town, outline the walkable cells of its map instead.')
        self.backdrop_action = self.toggle_action(
            QStyle.StandardPixmap.SP_DesktopIcon, 'Background', self.toggle_backdrop, True,
            'Draw the section\'s backdrop sprites behind the level. They scroll with the '
            'camera at their own fraction of its movement, as in the game.')
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
        self.canvas.backdrop = scene.backdrop
        self.canvas.sky = scene.sky
        self.backdrop_action.setEnabled(bool(scene.backdrop) or scene.sky is not None)
        self.canvas.show_lines = self.collision_action.isChecked()
        self.collision_action.setEnabled(scene.collision is not None)
        self.town_action.setEnabled(any(e.alternative is not None for e in scene.entries))
        self.toggle_town(self.town_action.isChecked())
        self.animated = [[i, 0, e.frames[0][1]] for i, e in enumerate(scene.entries) if e.frames]
        self.assets.clear()
        for a in scene.resources:
            self.assets.addItem(a.label, a)
        self.notice.setText(' | '.join(scene.notes))
        self.collision_inspector.set_scene(scene)
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
        if value:
            self.inspect_tabs.setCurrentIndex(1)
        self.canvas.update()

    def frame_current(self):
        if self.inspect_tabs.currentIndex() == 1 and self.collision_inspector.selected is not None:
            self.collision_inspector.frame()
        else:
            super().frame_current()

    def save_gif(self):
        """One cycle of the selected object's animation as a GIF: a sprite's
        frames, or the texture of a model whose texture coordinates move."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from gui.widgets.image_view import file_stem
        row = self.objects.currentRow()
        entry = self.scene.entries[row] if self.scene and 0 <= row < len(self.scene.entries) else None
        if entry is None or not entry.frames:
            QMessageBox.information(self, 'Save GIF', 'Select an animated sprite or model in the scene list first. '
                                    'The stats line shows how many the section has.')
            return
        name = file_stem(f'{self.export_name} - {entry.name}', 'animation')
        textured = entry.frames[0][0].image is None
        kinds = ('GIF, cropped to the UVs (*.gif);;GIF, whole texture page (*.gif)' if textured else 'GIF (*.gif)')
        path, kind = QFileDialog.getSaveFileName(self, 'Save GIF', name + '.gif', kinds)
        if not path:
            return
        images = self.texture_steps(row, entry, 'whole' in kind) if textured else self.sprite_steps(entry)
        if not images:
            QMessageBox.information(self, 'Save GIF', 'The texture coordinates of this model do not change.')
            return
        images[0].save(path, save_all=True, append_images=images[1:], loop=0, disposal=2,
                       duration=[ticks * TICK_MS for _, ticks in entry.frames[:len(images)]])
        print(f'wrote {path}: {len(images)} steps')

    @staticmethod
    def sprite_steps(entry):
        """Every step on one canvas, so the sprite keeps its place."""
        from PIL import Image
        boxes = []
        for mesh, ticks in entry.frames:
            corners = mesh.polygons[0]['vertices']
            boxes.append((min(c[0] for c in corners), max(c[1] for c in corners), mesh.image))
        left, top = min(b[0] for b in boxes), max(b[1] for b in boxes)
        width = int(max(b[0] + b[2].width for b in boxes) - left)
        height = int(top - min(b[1] - b[2].height for b in boxes))
        images = []
        for x, y, image in boxes:
            canvas = Image.new('RGBA', (width, height))
            canvas.alpha_composite(image, (int(x - left), int(top - y)))
            images.append(canvas)
        return images

    def texture_steps(self, row, entry, whole):
        """The texture a model shows at each step. A model animated this way
        keeps its polygons and moves their UVs across the page, so each step
        is the page seen through that step's UVs: cropped to them, or the
        whole page with them outlined."""
        from PIL import ImageDraw
        from psx.graphics import texture_page
        first = entry.frames[0][0].polygons
        moving = [n for n, polygon in enumerate(first) if polygon['page'] >= 0 and any(
            mesh.polygons[n]['uv'] != polygon['uv'] for mesh, _ in entry.frames[1:] if n < len(mesh.polygons))]
        if not moving:
            return []
        # The polygon picked in the view if it is one of them, else the first.
        picked = self.canvas.selected
        chosen = moving[0]
        if picked is not None and picked[0] == row:
            current = self.canvas.meshes[row].polygons
            at = next((n for n, polygon in enumerate(current) if polygon is picked[1]), None)
            chosen = at if at in moving else chosen
        texel = lambda uv: (round(uv[0] * 256 - .5), round(uv[1] * 256 - .5))
        boxes = []
        for mesh, _ in entry.frames:
            points = [texel(uv) for uv in mesh.polygons[chosen]['uv']]
            boxes.append((min(p[0] for p in points), min(p[1] for p in points),
                          max(p[0] for p in points) + 1, max(p[1] for p in points) + 1))
        width, height = max(b[2] - b[0] for b in boxes), max(b[3] - b[1] for b in boxes)
        images = []
        for (mesh, _), box in zip(entry.frames, boxes):
            polygon = mesh.polygons[chosen]
            page = texture_page(self.canvas.vram, polygon['page'], polygon['clut']).copy()
            if whole:
                draw = ImageDraw.Draw(page)
                for n in moving:
                    points = [texel(uv) for uv in mesh.polygons[n]['uv']]
                    order = [0, 1, 3, 2, 0] if len(points) == 4 else [0, 1, 2, 0]
                    draw.line([points[i] for i in order], fill='yellow')
                images.append(page)
            else:
                images.append(page.crop((box[0], box[1], box[0] + width, box[1] + height)))
        return images

    def toggle_backdrop(self, value):
        self.canvas.show_backdrop = value
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
        if e.handler is not None:
            overlay = next((a for a in self.scene.resources if a.kind == 'INS'), None)
            text += f'\n\nObject handler: 0x{e.handler:08X}'
            if overlay is not None and 0x800E7388 <= e.handler < 0x800E7388 + overlay.size:
                text += f'\n{overlay.label}\nHandler offset: 0x{e.handler - 0x800E7388:06X}'
        if e.animation_address is not None:
            text += f'\nAnimation script: 0x{e.animation_address:08X}'
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
