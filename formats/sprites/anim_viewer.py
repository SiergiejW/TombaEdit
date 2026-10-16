"""Animations of a sprite bank: the scripts that step an object through its
frames (formats.sprites.animations), found in the code loaded with the bank,
listed and played at the game's own rate."""
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
                             QTableWidget, QTableWidgetItem, QSplitter, QSpinBox, QCheckBox, QFileDialog,
                             QAbstractItemView, QMessageBox, QInputDialog)
from gui.widgets.image_view import ImageView, file_stem
from gui.widgets.columns import adjustable
from formats.sprites.animations import Memory, sniff, read_script

FILTERS = ('Verified animations', 'Unverified candidates (advanced)', 'Verified in the overlay', 'Verified in the executable')
BACKGROUND = (40, 40, 56, 255)
ORIGIN = (255, 80, 80, 255)


def frames_text(frames):
    """Hex sprite IDs, with consecutive frames joined as ranges."""
    runs, out = [], []
    for frame in frames:
        if runs and frame == runs[-1][1] + 1:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame])
    for low, high in runs:
        out.append(f'{low:02X}' if low == high else f'{low:02X}-{high:02X}')
    text = ', '.join(out)
    return text


class AnimationView(QWidget):
    """`regions`: [(name, load address, bytes)] of the code to search;
    `count`: frames in the bank; `picture(frame)`: (RGBA image, left, top)
    of a frame relative to the object's position, or None; `users`:
    {script address: [what starts on it]}; `rate`: updates a second."""

    def __init__(self, regions, count, picture, users=None, rate=60, name='animation'):
        super().__init__()
        self.memory = Memory(regions)
        self.count, self.picture, self.users = count, picture, dict(users or {})
        self.rate, self.export_name = rate, name
        self.scripts, self.shown = None, []
        self.script, self.step, self.left = None, 0, 0
        self.pictures = {}
        self.entry_flags = None
        self.label_set, self.save_labels, self.bank_key = None, None, ''
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItems(FILTERS)
        self.filter.currentIndexChanged.connect(self.relist)
        self.address = QLineEdit()
        self.address.setPlaceholderText('Script address, e.g. 800F22C8')
        self.address.setMaximumWidth(200)
        self.address.returnPressed.connect(self.read_address)
        read = QPushButton('Read')
        read.setToolTip('Decode the script at this address with this bank.')
        read.clicked.connect(self.read_address)
        tools.addWidget(QLabel('Show:'))
        tools.addWidget(self.filter)
        tools.addSpacing(12)
        tools.addWidget(QLabel('Address:'))
        tools.addWidget(self.address)
        tools.addWidget(read)
        tools.addStretch()
        layout.addLayout(tools)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(['Address', 'In', 'Found by', 'Steps', 'Updates', 'Ends', 'Frames', 'Used by', 'Label', 'Looks off'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.currentCellChanged.connect(lambda row, *_: self.choose(row))
        self.table.cellDoubleClicked.connect(lambda *_: self.play.setChecked(True))
        adjustable(self.table, min_widths={8: 180})
        self.table.horizontalHeader().moveSection(self.table.horizontalHeader().visualIndex(9), 0)
        split.addWidget(self.table)
        right = QWidget()
        side = QVBoxLayout(right)
        side.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.play = QPushButton('Play')
        self.play.setCheckable(True)
        self.play.toggled.connect(self.toggle)
        back, forward = QPushButton('<'), QPushButton('>')
        back.setToolTip('Previous step')
        forward.setToolTip('Next step')
        back.clicked.connect(lambda: self.go(-1))
        forward.clicked.connect(lambda: self.go(1))
        self.speed = QSpinBox()
        self.speed.setRange(1, 240)
        self.speed.setValue(rate)
        self.speed.setSuffix(' updates/s')
        self.speed.setToolTip(f'The game steps animations once per update, {rate} a second on this disc.')
        self.marker = QCheckBox('Origin')
        self.marker.setToolTip('Mark the object\'s position.')
        self.marker.toggled.connect(self.redraw)
        gif, strip = QPushButton('GIF...'), QPushButton('Strip...')
        gif.clicked.connect(self.save_gif)
        strip.clicked.connect(self.save_strip)
        for widget in (self.play, back, forward, self.speed, self.marker):
            controls.addWidget(widget)
        controls.addStretch()
        controls.addWidget(gif)
        controls.addWidget(strip)
        side.addLayout(controls)
        self.status = QLabel('Select an animation.')
        side.addWidget(self.status)
        self.view = ImageView()
        side.addWidget(self.view)
        name_button = QPushButton('Name animation...')
        name_button.clicked.connect(self.rename_selection)
        side.addWidget(name_button)
        split.addWidget(right)
        split.setSizes([620, 520])
        layout.addWidget(split, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.left = 0

    # Finding --------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self.scripts is None:
            self.search()
        if self.script is not None:
            self.play.setChecked(True)

    def search(self):
        names = [name for name, _, _ in self.memory.regions]
        self.scripts = {}
        for address in self.users:
            if address not in self.scripts:
                script = read_script(self.memory, address, self.count)
                if script is not None:
                    self.scripts[address] = script
        for address, script in self.scripts.items():
            if address in self.users:
                script.found.add('object')
        self.relist()
        self.note.setText(f'{len(self.users)} animation starts linked to this bank by object handlers or '
                          'loaded animation tables. Other byte patterns are excluded from normal playback. '
                          'Advanced candidates and manually entered addresses are not verified bank links.')

    def related(self):
        """Scripts in use here and those sharing a table with one."""
        return set(self.users) & set(self.scripts)

    def relist(self):
        if self.scripts is None:
            return
        mode = self.filter.currentIndex()
        if mode == 0:
            chosen = self.related()
        elif mode == 1:
            if not getattr(self, 'candidates_read', False):
                self.scripts.update({a: s for a, s in sniff(
                    self.memory, self.count, code=[n for n, _, _ in self.memory.regions]).items()
                    if a not in self.scripts})
                self.candidates_read = True
            chosen = set(self.scripts)
        else:
            want = 'overlay' if mode == 2 else 'executable'
            chosen = {a for a in self.related() if self.memory.region(a) == want}
        rank = {'typed': 0, 'object': 0, 'table': 1, 'code': 2, 'pointer': 3}
        self.shown = sorted(chosen, key=lambda a: (min(rank.get(f, 4) for f in self.scripts[a].found or {'?'}), a))
        self.table.setRowCount(len(self.shown))
        for row, address in enumerate(self.shown):
            script = self.scripts[address]
            table = f'table {script.tables[0][0]:08X} #{script.tables[0][1]}' if script.tables else ''
            found = ('Verified: handler/table' if address in self.users else 'Unverified')
            cells = (f'{address:08X}', self.memory.region(address), found, str(len(script.steps)),
                     str(script.ticks), script.ending, frames_text(script.frames),
                     ', '.join(self.users.get(address, ())), self.animation_label(script))
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, column, item)
        if self.entry_flags is not None:
            self.entry_flags.fill([f'0x{address:08X}' for address in self.shown])
        if self.shown:
            self.table.setCurrentCell(0, 0)
        else:
            self.play.setChecked(False)
            self.script = None
            self.status.setText('No verified animations for this bank and load context.')

    def read_address(self):
        try:
            address = int(self.address.text().strip().lower().removeprefix('0x'), 16)
        except ValueError:
            return
        script = read_script(self.memory, address, self.count)
        if script is None:
            QMessageBox.information(self, 'Read', f'No script of this bank\'s {self.count} frames starts at '
                                    f'{address:08X} in the code searched.')
            return
        if self.scripts is None:
            self.search()
        script = self.scripts.setdefault(address, script)
        script.found.add('typed')
        if self.filter.currentIndex() != 1:
            self.filter.setCurrentIndex(1)
        else:
            self.relist()
        self.table.setCurrentCell(self.shown.index(address), 0)

    # Playing ----------------------------------------------------------------
    def choose(self, row):
        if not 0 <= row < len(self.shown):
            return
        self.script = self.scripts[self.shown[row]]
        self.step, self.left = 0, self.script.steps[0].duration
        self.box = self.bounds(self.script)
        self.redraw()
        if self.isVisible():
            self.play.setChecked(True)

    def set_labels(self, label_set, save, bank_key):
        self.label_set, self.save_labels, self.bank_key = label_set, save, bank_key

    def set_check_target(self, target, store):
        from formats.sprites.check_view import SpriteCheckBar
        self.check_bar = SpriteCheckBar(target, lambda: dict(
            animation_address=f'0x{self.script.address:08X}' if self.script else None), self, store)
        self.layout().insertWidget(1, self.check_bar)
        from formats.sprites.entry_flags import EntryFlags
        self.entry_flags = EntryFlags(self.table, 9, self.check_bar, 'animation')
        self.entry_flags.fill([f'0x{address:08X}' for address in self.shown])

    def animation_key(self, script):
        from game.labels import content_key
        steps = [(s.frame, s.box, s.arg, s.ticks, s.flags) for s in script.steps]
        return content_key((self.bank_key + repr((steps, script.loop))).encode())

    def animation_label(self, script):
        return (self.label_set.label_for(self.animation_key(script)) or '') if self.label_set is not None else ''

    def rename_selection(self):
        if self.script is None or self.label_set is None:
            return
        name, ok = QInputDialog.getText(self, 'Name animation', 'Label (empty removes it):',
                                       text=self.animation_label(self.script))
        if ok:
            self.label_set.rename(self.animation_key(self.script), name.strip(), kind='SPR animation')
            if self.save_labels:
                self.save_labels()
            row = self.table.currentRow()
            if row >= 0:
                self.table.setItem(row, 8, QTableWidgetItem(name.strip()))

    def frame_picture(self, frame):
        if frame not in self.pictures:
            self.pictures[frame] = self.picture(frame)
        return self.pictures[frame]

    def bounds(self, script):
        """The box every frame of the script fits in, about the origin."""
        boxes = [(left, top, left + image.width, top + image.height)
                 for image, left, top in filter(None, (self.frame_picture(f) for f in set(script.frames)))]
        if not boxes:
            return (-8, -8, 8, 8)
        return (min(b[0] for b in boxes) - 2, min(b[1] for b in boxes) - 2,
                max(b[2] for b in boxes) + 2, max(b[3] for b in boxes) + 2)

    def compose(self, step, background=BACKGROUND):
        x0, y0, x1, y1 = self.box
        canvas = Image.new('RGBA', (x1 - x0, y1 - y0), background)
        found = self.frame_picture(step.frame)
        if found is not None:
            image, left, top = found
            canvas.alpha_composite(image, (left - x0, top - y0))
        if self.marker.isChecked():
            draw = ImageDraw.Draw(canvas)
            draw.line((-x0 - 3, -y0, -x0 + 3, -y0), fill=ORIGIN)
            draw.line((-x0, -y0 - 3, -x0, -y0 + 3), fill=ORIGIN)
        return canvas

    def redraw(self):
        if self.script is None:
            return
        step = self.script.steps[self.step]
        self.view.set_image(self.compose(step), subject=self.script.address)
        flags = {0: '', 0x8000: ', end', 0x4000: ', then jumps', 0xC000: ', then jumps and reports the end'}[step.flags]
        self.status.setText(f'Step {self.step + 1}/{len(self.script.steps)}: frame {step.frame:02X}, '
                            f'{step.ticks} updates, box {step.box}, argument {step.arg}{flags} '
                            f'| {self.script.ticks} updates a pass, {self.script.ending}')

    def toggle(self, on):
        self.play.setText('Pause' if on else 'Play')
        if on:
            self.timer.start(max(1, round(1000 / self.speed.value())))
        else:
            self.timer.stop()

    def tick(self):
        if self.script is None:
            return
        self.timer.setInterval(max(1, round(1000 / self.speed.value())))
        self.left -= 1
        if self.left > 0:
            return
        self.advance()
        self.redraw()

    def advance(self):
        script = self.script
        if self.step + 1 < len(script.steps):
            self.step += 1
        elif script.loop is not None:
            self.step = script.loop
        self.left = script.steps[self.step].duration

    def go(self, direction):
        if self.script is None:
            return
        self.step = (self.step + direction) % len(self.script.steps)
        self.left = self.script.steps[self.step].duration
        self.redraw()

    def hideEvent(self, event):
        self.play.setChecked(False)
        super().hideEvent(event)

    # Export -----------------------------------------------------------------
    def stem(self):
        return file_stem(f'{self.export_name} {self.script.address:08X}', 'animation')

    def save_gif(self):
        if self.script is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save GIF', self.stem() + '.gif', 'GIF (*.gif)')
        if not path:
            return
        images = [self.compose(step, (0, 0, 0, 0)) for step in self.script.steps]
        rate = self.speed.value()
        images[0].save(path, save_all=True, append_images=images[1:], loop=0, disposal=2,
                       duration=[max(20, round(s.duration * 1000 / rate)) for s in self.script.steps])

    def save_strip(self):
        if self.script is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save strip', self.stem() + '.png', 'PNG (*.png)')
        if not path:
            return
        cells = [self.compose(step, (0, 0, 0, 0)) for step in self.script.steps]
        width, height = cells[0].size
        strip = Image.new('RGBA', ((width + 2) * len(cells), height))
        for k, cell in enumerate(cells):
            strip.alpha_composite(cell, (k * (width + 2), 0))
        strip.save(path)
