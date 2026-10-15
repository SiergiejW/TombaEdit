"""The sound viewer: one layout for sample banks, sequences and streams.

Top to bottom it is a title line, three panes and a player. The panes are
the sources (banks of a file, or the banks that can play a sequence), the
rows of the chosen source, and the details of the chosen row. The player
along the bottom holds everything that acts on the sound: what is playing,
its waveform, the transport and the exports.
"""
from pathlib import Path
from PyQt6.QtCore import (Qt, QObject, QRunnable, QThreadPool, QTimer, pyqtSignal,
                          QByteArray, QBuffer, QIODevice, QUrl, QSize)
from PyQt6.QtGui import QFont, QFontDatabase, QKeySequence, QShortcut
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox,
    QFileDialog, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QSlider, QInputDialog, QFrame, QPlainTextEdit, QCheckBox, QSizePolicy)
from gui.widgets.image_view import file_stem
from gui.widgets.columns import adjustable
from gui.widgets.transport_icons import set_glyph
from gui.widgets.wave_preview import WavePreview
from gui.widgets.mini_audio import waveform_icon

ICON = QSize(132, 24)
ROW_HEIGHT = 30
SELECTION = ('QTableWidget::item:selected {background-color: #555555; color: white;} '
             'QTableWidget::item:selected:!active {background-color: #494949; color: white;}')


class Signals(QObject):
    done = pyqtSignal(int, object, str)


class RenderJob(QRunnable):
    def __init__(self, generation, callback, receiver):
        super().__init__()
        self.generation, self.callback = generation, callback
        self.signals = Signals(); self.signals.done.connect(receiver)

    def run(self):
        try:
            result, error = self.callback(), ''
        except Exception as exc:
            result, error = None, str(exc)
        try:
            self.signals.done.emit(self.generation, result, error)
        except RuntimeError:
            pass


def caption(text):
    label = QLabel(text.upper())
    label.setObjectName('panelTitle')
    return label


def table(columns):
    view = QTableWidget(0, len(columns))
    view.setHorizontalHeaderLabels(list(columns))
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setShowGrid(False)
    view.setWordWrap(False)
    view.setStyleSheet(SELECTION)
    view.horizontalHeader().setHighlightSections(False)
    view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return view


def pane(title, *widgets, stretch=None):
    """A captioned column of widgets; `stretch` names the one that grows."""
    frame = QWidget()
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(caption(title))
    for widget in widgets:
        layout.addWidget(widget, 1 if widget is (stretch or widgets[-1]) else 0)
    frame.caption = layout.itemAt(0).widget()
    return frame


class AudioView(QWidget):
    def __init__(self, sources, title='', label_set=None, save_labels=None, export_name=''):
        super().__init__()
        self.sources = list(sources)
        self.label_set, self.save_labels = label_set, save_labels
        self.export_name = export_name or title
        self.generation = 0
        self.pool = QThreadPool.globalInstance()
        self.pending = None         # where an export in progress is going
        self.loaded = None          # (source index, row) of the sound in the player
        self.rendering = None       # the same, with its title, for the one being rendered
        self.preview_column = -1
        self.rows = []
        self.buffer = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # Title line.
        head = QHBoxLayout()
        self.title = QLabel(title)
        font = QFont(self.title.font()); font.setPointSizeF(font.pointSizeF() + 2); font.setBold(True)
        self.title.setFont(font)
        self.summary = QLabel()
        self.summary.setObjectName('panelTitle')
        self.summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.title)
        head.addWidget(self.summary, 1)
        outer.addLayout(head)

        # Sources, rows, details.
        self.source_table = table(('Source', 'Contents'))
        self.source_table.setColumnWidth(0, 220)
        adjustable(self.source_table)
        self.source_pane = pane('Sources', self.source_table)
        self.row_table = table(())
        self.row_table.setIconSize(ICON)
        self.row_pane = pane('Entries', self.row_table)
        self.detail_table = table(('Property', 'Value'))
        self.detail_table.horizontalHeader().hide()
        self.detail_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.detail_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.detail_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.detail_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.detail_table.verticalHeader().setDefaultSectionSize(24)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text_caption = caption('Events')
        self.detail_pane = pane('Details', self.detail_table, self.text_caption, self.text, stretch=self.detail_table)
        self.detail_pane.layout().setStretchFactor(self.text, 2)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setChildrenCollapsible(False)
        for widget in (self.source_pane, self.row_pane, self.detail_pane):
            self.split.addWidget(widget)
        self.split.setStretchFactor(0, 2); self.split.setStretchFactor(1, 5); self.split.setStretchFactor(2, 3)
        self.split.setSizes([260, 560, 340])
        outer.addWidget(self.split, 1)

        # The player.
        dock = QFrame()
        dock.setFrameShape(QFrame.Shape.StyledPanel)
        dock_layout = QVBoxLayout(dock)
        dock_layout.setContentsMargins(10, 8, 10, 8)
        dock_layout.setSpacing(6)
        line = QHBoxLayout()
        self.now = QLabel('Nothing loaded')
        bold = QFont(self.now.font()); bold.setBold(True); self.now.setFont(bold)
        self.status = QLabel()
        self.status.setObjectName('panelTitle')
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        line.addWidget(self.now)
        line.addWidget(self.status, 1)
        dock_layout.addLayout(line)
        self.wave = WavePreview()
        self.wave.setFixedHeight(72)
        self.wave.placeholder = 'The waveform of what is playing appears here; click it to seek.'
        self.wave.scrubbed.connect(lambda fraction: self.player.setPosition(round(self.player.duration() * fraction)))
        dock_layout.addWidget(self.wave)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        previous = QPushButton(); set_glyph(previous, 'previous'); previous.clicked.connect(lambda: self.step(-1))
        self.play_button = QPushButton(); set_glyph(self.play_button, 'play')
        self.play_button.clicked.connect(self.toggle_play)
        stop = QPushButton(); set_glyph(stop, 'stop'); stop.clicked.connect(self.stop)
        following = QPushButton(); set_glyph(following, 'next'); following.clicked.connect(lambda: self.step(1))
        for button in (previous, self.play_button, stop, following):
            bar.addWidget(button)
        self.clock = QLabel('0:00.00 / 0:00.00')
        self.clock.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        bar.addSpacing(8)
        bar.addWidget(self.clock)
        bar.addStretch(1)
        self.auto = QCheckBox('Play on select')
        self.auto.setChecked(True)
        bar.addWidget(self.auto)
        self.rate_label = QLabel('Preview rate')
        self.rate = QSpinBox(); self.rate.setRange(4000, 176400); self.rate.setSingleStep(1050)
        self.rate.setValue(22050); self.rate.setSuffix(' Hz')
        self.rate.setToolTip('A waveform has no rate of its own: the game plays it at whatever pitch the note asks for.')
        bar.addSpacing(8); bar.addWidget(self.rate_label); bar.addWidget(self.rate)
        bar.addSpacing(8); bar.addWidget(QLabel('Volume'))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100); self.volume.setValue(75); self.volume.setFixedWidth(110)
        bar.addWidget(self.volume)
        bar.addSpacing(12)
        self.name_button = QPushButton('Name...'); self.name_button.clicked.connect(self.rename_selection)
        self.export_button = QPushButton('Export sound...'); self.export_button.clicked.connect(lambda: self.render('export'))
        self.midi_button = QPushButton('Export MIDI...'); self.midi_button.clicked.connect(self.export_midi)
        for button in (self.name_button, self.export_button, self.midi_button):
            bar.addWidget(button)
        dock_layout.addLayout(bar)
        outer.addWidget(dock)

        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self); self.output.setVolume(.75)
        self.player.setAudioOutput(self.output)
        self.volume.valueChanged.connect(lambda value: self.output.setVolume(value / 100))
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda value: self.position_changed(self.player.position()))
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.errorOccurred.connect(lambda error, message: self.status.setText(message))
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.toggle_play)
        # Waveform thumbnails are drawn a few at a time so a large bank
        # opens at once.
        self.thumbnails = QTimer(self)
        self.thumbnails.setInterval(0)
        self.thumbnails.timeout.connect(self.draw_thumbnails)
        self.thumbnail_row = 0

        self.source_table.setRowCount(len(self.sources))
        for i, source in enumerate(self.sources):
            # Banks are files; the folder is in the tooltip.
            folder, _, short = source.name.rpartition('/')
            self.source_table.setItem(i, 0, QTableWidgetItem(short or source.name or 'No bank'))
            self.source_table.item(i, 0).setToolTip(source.name)
            self.source_table.setItem(i, 1, QTableWidgetItem(source.summary))
        self.source_pane.setVisible(len(self.sources) > 1)
        self.source_table.currentCellChanged.connect(lambda row, *rest: self.choose_source(row))
        self.row_table.currentCellChanged.connect(lambda row, *rest: self.choose_row(row))
        self.row_table.cellDoubleClicked.connect(lambda row, column: self.render('play'))
        self.source_table.cellDoubleClicked.connect(lambda row, column: self.render('play'))
        self.ready = False
        if self.sources:
            self.source_table.setCurrentCell(0, 0)
        self.ready = True

    # --- what is selected ---------------------------------------------------

    @property
    def source(self):
        row = self.source_table.currentRow()
        return self.sources[row] if 0 <= row < len(self.sources) else None

    def choose_source(self, index):
        self.stop()
        source = self.source
        if source is None:
            return
        whole = any(s.whole for s in self.sources)
        self.source_pane.caption.setText(('Instrument banks' if whole else 'Banks').upper())
        self.row_pane.caption.setText(source.caption.upper())
        self.summary.setText(source.summary if len(self.sources) == 1 else
                             f'{len(self.sources)} {"banks to play it on" if whole else "sources"}   |   {source.summary}')
        headers = (('#',) if source.numbered else ()) + tuple(source.headers)
        self.rows = source.rows()
        view = self.row_table
        view.blockSignals(True)
        view.clear()
        view.setColumnCount(len(headers))
        view.setHorizontalHeaderLabels(list(headers))
        view.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            cells = ((str(r + 1),) if source.numbered else ()) + tuple(row.cells)
            for c, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if headers[c] in ('#', 'Samples', 'Bytes', 'Sectors', 'Notes', 'Length'):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                view.setItem(r, c, item)
        header = view.horizontalHeader()
        name_column = 1 if source.numbered else 0
        # Columns start as wide as what they hold and can be dragged.
        adjustable(view, fit=True)
        if headers:
            view.setColumnWidth(name_column, max(190, view.columnWidth(name_column)))
        for c, name in enumerate(headers):
            if name == 'Preview':
                header.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
                view.setColumnWidth(c, ICON.width() + 12)
        view.blockSignals(False)
        self.preview_column = headers.index('Preview') if 'Preview' in headers else -1
        self.thumbnail_row = 0
        if self.preview_column >= 0:
            self.thumbnails.start()
        text = source.text()
        self.text.setPlainText(text)
        self.text.setVisible(bool(text)); self.text_caption.setVisible(bool(text))
        self.rate.setVisible(source.rate_adjustable); self.rate_label.setVisible(source.rate_adjustable)
        self.auto.setVisible(source.autoplay)
        self.midi_button.setVisible(source.whole)
        self.name_button.setVisible(self.label_set is not None and any(row.key for row in self.rows))
        self.now.setText('Nothing loaded')
        self.wave.envelope = None; self.wave.update()
        self.clock.setText('0:00.00 / 0:00.00')
        self.status.setText('Press play to render the sequence on this bank.' if source.whole else
                            'Select an entry to listen.' if source.autoplay else 'Double-click an entry, or press play.')
        if self.rows:
            view.setCurrentCell(0, 0)
        else:
            self.show_details(None)

    def draw_thumbnails(self):
        source = self.source
        for _ in range(4):
            if source is None or self.thumbnail_row >= len(self.rows):
                self.thumbnails.stop()
                return
            row = self.rows[self.thumbnail_row]
            item = self.row_table.item(self.thumbnail_row, self.preview_column)
            if row.preview is not None and item is not None:
                try:
                    item.setIcon(waveform_icon(row.preview(), ICON.width(), ICON.height()))
                except Exception:
                    pass
            self.thumbnail_row += 1

    def choose_row(self, row):
        self.show_details(row if 0 <= row < len(self.rows) else None)
        source = self.source
        if self.ready and source is not None and source.autoplay and self.auto.isChecked() and row >= 0:
            self.render('play')

    def show_details(self, row):
        source = self.source
        pairs = source.details(row) if source is not None else []
        self.detail_table.setRowCount(len(pairs))
        for i, (name, value) in enumerate(pairs):
            key = QTableWidgetItem(name)
            key.setForeground(self.palette().placeholderText())
            self.detail_table.setItem(i, 0, key)
            self.detail_table.setItem(i, 1, QTableWidgetItem(value))
            self.detail_table.item(i, 1).setToolTip(value)
        # With a text box below, the properties take exactly the room they
        # need and the text has the rest.
        if self.text.isHidden():
            self.detail_table.setMinimumHeight(0)
            self.detail_table.setMaximumHeight(16777215)
        else:
            self.detail_table.setFixedHeight(self.detail_table.verticalHeader().defaultSectionSize() * len(pairs) + 4)

    def step(self, amount):
        whole = self.source is not None and self.source.whole
        view = self.source_table if whole else self.row_table
        row = max(0, min(view.rowCount() - 1, view.currentRow() + amount))
        if view.rowCount():
            view.setCurrentCell(row, 0)
            if whole or not (self.source.autoplay and self.auto.isChecked()):
                self.render('play')

    def rename_selection(self):
        row = self.row_table.currentRow()
        if self.label_set is None or self.save_labels is None or not 0 <= row < len(self.rows) or not self.rows[row].key:
            return
        entry = self.rows[row]
        old = self.label_set.label_for(entry.key) or ''
        name, accepted = QInputDialog.getText(self, 'Name audio entry',
                                              'Label (empty restores the original name):', text=old)
        if accepted:
            self.label_set.rename(entry.key, name.strip(), kind=entry.kind or 'SFX')
            self.save_labels()
            column = 1 if self.source.numbered else 0
            fallback = self.source.default_name(row) if hasattr(self.source, 'default_name') else entry.cells[0]
            self.row_table.item(row, column).setText(name.strip() or fallback)

    # --- playing ------------------------------------------------------------

    def toggle_play(self):
        current = (self.source_table.currentRow(), self.row_table.currentRow())
        if self.source is not None and self.source.whole:
            current = (current[0], -1)
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.buffer and self.loaded == current and state == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
        elif self.buffer and self.loaded == current:
            self.player.setPosition(0); self.player.play()
        else:
            self.render('play')

    @staticmethod
    def clock_text(ms):
        cs = max(0, ms) // 10
        return f'{cs // 6000}:{(cs // 100) % 60:02d}.{cs % 100:02d}'

    def position_changed(self, value):
        duration = self.player.duration()
        self.clock.setText(f'{self.clock_text(value)} / {self.clock_text(duration)}')
        self.wave.set_position(value / max(1, duration))

    def playback_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        set_glyph(self.play_button, 'pause' if playing else 'play')
        if self.loaded is not None and not self.pending:
            self.status.setText('Playing' if playing else 'Paused' if state == QMediaPlayer.PlaybackState.PausedState
                                else 'Stopped')

    def stop(self):
        self.generation += 1
        self.player.stop()
        set_glyph(self.play_button, 'play')

    def render(self, purpose):
        source, row = self.source, self.row_table.currentRow()
        if source is None or (not source.whole and not 0 <= row < len(self.rows)):
            self.status.setText('Select an entry to play.')
            return
        self.stop()
        destination = None
        suffix = '.wav'
        if purpose == 'export':
            name = file_stem(f'{self.export_name} {source.title(row)}' if not source.whole else source.title(row), 'sound')
            destination, selected = QFileDialog.getSaveFileName(
                self, 'Export sound', name + '.wav', 'WAV audio (*.wav);;OGG Vorbis audio (*.ogg)')
            if not destination:
                return
            suffix = '.ogg' if '*.ogg' in selected else '.wav'
            destination = str(Path(destination).with_suffix(suffix))
        self.status.setText('Rendering...')
        rate = self.rate.value()
        self.pending = destination
        self.rendering = (self.source_table.currentRow(), -1 if source.whole else row, source.title(row))
        from formats.audio.audio_export import encode_audio
        self.pool.start(RenderJob(self.generation, lambda: encode_audio(source.play(row, rate), suffix), self.rendered))

    def rendered(self, generation, data, error):
        if generation != self.generation:
            return
        if error:
            self.pending = None
            self.status.setText(error)
            return
        if self.pending:
            destination, self.pending = self.pending, None
            try:
                Path(destination).write_bytes(data)
                self.status.setText('Exported ' + destination)
            except OSError as exc:
                self.status.setText(str(exc))
            return
        self.player.setSource(QUrl())
        if self.buffer:
            self.buffer.close(); self.buffer.deleteLater()
        self.buffer = QBuffer(self); self.buffer.setData(QByteArray(data))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.player.setSourceDevice(self.buffer)
        self.wave.set_wav(data)
        self.loaded = self.rendering[:2]
        self.now.setText(self.rendering[2])
        self.player.play()
        self.status.setText('Playing')

    def export_midi(self):
        source = self.source
        if source is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export MIDI', file_stem(self.export_name, 'sequence') + '.mid',
                                              'MIDI (*.mid)')
        if path:
            try:
                Path(path).write_bytes(source.midi())
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))

    def hideEvent(self, event):
        self.stop()
        self.thumbnails.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.preview_column >= 0 and self.thumbnail_row < len(self.rows):
            self.thumbnails.start()
