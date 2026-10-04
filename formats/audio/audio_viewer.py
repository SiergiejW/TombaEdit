"""WVD samples and Sony SEQ playback using Tomba2Edit's SPU synthesizer."""
import io
import struct
import wave
from pathlib import Path
from PyQt6.QtCore import (Qt, QObject, QRunnable, QThreadPool, pyqtSignal,
                         QByteArray, QBuffer, QIODevice, QUrl)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QComboBox, QLabel, QSpinBox, QFileDialog, QMessageBox, QSplitter,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSlider)
from formats.audio import seq, sfx, wvd
from gui.widgets.image_view import text_view
from gui.widgets.transport_icons import set_glyph


def wav_bytes(samples, rate, channels=1):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(channels); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes(samples)
    return stream.getvalue()


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


class AudioView(QWidget):
    def __init__(self, data, project, source=''):
        super().__init__()
        self.data, self.project = data, project
        self.is_seq = data.startswith(b'pQES')
        self.bank_data = [] if self.is_seq else wvd.banks(data)
        self.generation = 0
        self.pool = QThreadPool.globalInstance()
        self.pending = None
        self.ready = False
        layout = QVBoxLayout(self)
        split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel('Sound banks'))
        self.bank_list = QTableWidget(0, 2)
        self.bank_list.setHorizontalHeaderLabels(['Sound bank', 'Samples'])
        self.bank_list.verticalHeader().hide()
        self.bank_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bank_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.bank_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.bank_list.currentCellChanged.connect(lambda row, col, previous_row, previous_col: self.bank.setCurrentIndex(row))
        left_layout.addWidget(self.bank_list, 1)
        left_layout.addWidget(QLabel('Samples'))
        self.sample_list = QTableWidget(0, 4)
        self.sample_list.setHorizontalHeaderLabels(['Sample', 'Bytes', 'Offset', 'Loop'])
        self.sample_list.verticalHeader().hide()
        self.sample_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sample_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sample_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.sample_list.currentCellChanged.connect(self.choose_sample)
        left_layout.addWidget(self.sample_list, 2)
        split.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        bar = QHBoxLayout()
        self.bank = QComboBox()
        if self.is_seq:
            for entry in project.disc.files:
                if entry.path.upper().endswith('.WVD'):
                    self.bank.addItem(entry.path, entry.path)
            match = self.bank.findText(str(Path(source).with_suffix('.WVD')).replace('\\', '/'))
            if match >= 0:
                self.bank.setCurrentIndex(match)
        else:
            for i, bank in enumerate(self.bank_data):
                self.bank.addItem(f'Bank {i} | {len(sfx.samples(bank))} samples', i)
        self.bank_list.setRowCount(self.bank.count())
        for i in range(self.bank.count()):
            name = self.bank.itemText(i)
            count = '' if self.is_seq else str(len(sfx.samples(self.bank_data[i])))
            self.bank_list.setItem(i, 0, QTableWidgetItem(name))
            self.bank_list.setItem(i, 1, QTableWidgetItem(count))
        self.bank.currentIndexChanged.connect(self.selection_changed)
        self.bank.currentIndexChanged.connect(lambda row: self.bank_list.setCurrentCell(row, 0) if row >= 0 and self.bank_list.currentRow() != row else None)
        self.bank.hide()
        self.sample = QComboBox()
        self.sample.hide()
        self.rate = QSpinBox(); self.rate.setRange(4000, 176400); self.rate.setValue(22050)
        self.rate.setSuffix(' Hz'); self.rate.setVisible(not self.is_seq); bar.addWidget(self.rate)
        right_layout.addLayout(bar)
        controls = QHBoxLayout()
        previous = QPushButton(); set_glyph(previous, 'previous')
        previous.clicked.connect(lambda: self.step(-1))
        self.play_button = QPushButton(); set_glyph(self.play_button, 'play')
        self.play_button.clicked.connect(self.toggle_play)
        stop = QPushButton(); set_glyph(stop, 'stop'); stop.clicked.connect(self.stop)
        following = QPushButton(); set_glyph(following, 'next')
        following.clicked.connect(lambda: self.step(1))
        export = QPushButton('Export WAV...'); export.clicked.connect(lambda: self.render('export'))
        for button in (previous, self.play_button, stop, following):
            controls.addWidget(button)
        self.clock = QLabel('0:00.00 / 0:00.00')
        controls.addWidget(self.clock)
        controls.addStretch()
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100); self.volume.setValue(75)
        self.volume.setMaximumWidth(110)
        controls.addWidget(QLabel('Volume')); controls.addWidget(self.volume)
        right_layout.addWidget(QLabel('Playback'))
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderMoved.connect(self.player_seek)
        right_layout.addWidget(self.timeline)
        if self.is_seq:
            midi = QPushButton('Export MIDI...'); midi.clicked.connect(self.export_midi)
        right_layout.addLayout(controls)
        exports = QHBoxLayout(); exports.addWidget(export)
        if self.is_seq:
            exports.addWidget(midi)
        exports.addStretch(); right_layout.addLayout(exports)
        self.status = QLabel(); self.status.setWordWrap(True); right_layout.addWidget(self.status)
        self.details = text_view(''); right_layout.addWidget(self.details)
        split.addWidget(right)
        split.setSizes([300, 850])
        layout.addWidget(split)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self); self.output.setVolume(.5)
        self.player.setAudioOutput(self.output)
        self.volume.valueChanged.connect(lambda value: self.output.setVolume(value / 100))
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.errorOccurred.connect(lambda error, message: self.status.setText(message))
        self.buffer = None
        self.selection_changed()
        if self.bank.count():
            self.bank_list.setCurrentCell(self.bank.currentIndex(), 0)
        self.ready = True

    def selection_changed(self):
        self.stop()
        self.sample.clear()
        self.sample_list.blockSignals(True)
        self.sample_list.setRowCount(0)
        if self.is_seq:
            # A WVD may carry several VABs; expose them independently.
            try:
                self.bank_data = wvd.banks(self.project.payload(self.project.disc.entries[self.bank.currentData()]))
                for i,b in enumerate(self.bank_data):
                    self.sample.addItem(f'Instrument bank {i}', i)
            except (KeyError, ValueError) as exc:
                self.status.setText(str(exc)); self.sample_list.blockSignals(False); return
            self.sample_list.setRowCount(len(self.bank_data))
            for i in range(len(self.bank_data)):
                self.sample_list.setItem(i, 0, QTableWidgetItem(f'Instrument bank {i}'))
            resolution, tempo = seq.header(self.data,0)
            events = seq.events(self.data,0)
            rows = [f'Ticks/quarter: {resolution} | Tempo: {60000000/tempo:.2f} BPM',
                    f'{len(events)} MIDI events', 'Delta | Status | Data 1 | Data 2']
            rows += [f'{d:6d} | {s:02X} | {a:6d} | {b:6d}' for d,s,a,b in events]
            self.details.setPlainText('\n'.join(rows))
            self.status.setText('Select the matching instrument bank. Playback uses SPU samples and ADSR; reverb and exact console mixing are not emulated.')
        elif self.bank_data:
            bank = self.bank_data[self.bank.currentIndex()]
            samples = sfx.samples(bank)
            self.sample_list.setRowCount(len(samples))
            for _,number,offset,size in samples:
                self.sample.addItem(f'Sample {number:03d} | {size:,} bytes', (offset,size))
            for row, (_, number, offset, size) in enumerate(samples):
                values = [f'Sample {number:03d}', f'{size:,}', f'0x{offset:06X}',
                          'loop' if sfx.loops(bank, offset, size) else '']
                for col, value in enumerate(values):
                    self.sample_list.setItem(row, col, QTableWidgetItem(value))
            self.details.setPlainText('\n'.join(f'Sample {n:03d} | offset {o:06X} | {s:,} bytes | loop {sfx.loops(bank,o,s)}' for _,n,o,s in samples))
            self.status.setText('Sample pitch depends on the note used by the game. Choose a preview sample rate.')
        if self.sample_list.rowCount():
            self.sample_list.setCurrentCell(0, 0)
        self.sample_list.blockSignals(False)

    def choose_sample(self, row, column, old_row, old_column):
        if row < 0 or row >= self.sample.count():
            return
        self.sample.setCurrentIndex(row)
        if self.ready:
            self.render('play')

    def step(self, amount):
        row = max(0, min(self.sample_list.rowCount()-1, self.sample_list.currentRow()+amount))
        if row >= 0:
            self.sample_list.setCurrentCell(row, 0)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.buffer and self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
        else:
            self.render('play')

    def player_seek(self, value):
        self.player.setPosition(value)

    @staticmethod
    def clock_text(ms):
        cs = max(0, ms) // 10
        return f'{cs//6000}:{(cs//100)%60:02d}.{cs%100:02d}'

    def position_changed(self, value):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(value)
        self.clock.setText(f'{self.clock_text(value)} / {self.clock_text(self.player.duration())}')

    def duration_changed(self, value):
        self.timeline.setRange(0, value)
        self.position_changed(self.player.position())

    def playback_changed(self, state):
        set_glyph(self.play_button, 'pause' if state == QMediaPlayer.PlaybackState.PlayingState else 'play')

    def stop(self):
        self.generation += 1
        self.player.stop()
        set_glyph(self.play_button, 'play')

    def render(self, purpose):
        if self.sample.currentIndex() < 0:
            return
        self.stop()
        destination = None
        if purpose == 'export':
            destination, _ = QFileDialog.getSaveFileName(self,'Export audio','sound.wav','Wave audio (*.wav)')
            if not destination:
                return
        self.status.setText('Rendering audio...')
        data = self.data
        if self.is_seq:
            bank = self.bank_data[self.sample.currentIndex()]
            callback = lambda: wav_bytes(seq.pcm(seq.render(data,0,bank,0)[0]),seq.RATE,2)
        else:
            bank = self.bank_data[self.bank.currentIndex()]
            offset,size = self.sample.currentData(); rate = self.rate.value()
            def callback():
                values = sfx.decode(bank,offset,size)
                return wav_bytes(struct.pack(f'<{len(values)}h',*values),rate)
        self.pending = destination
        self.pool.start(RenderJob(self.generation,callback,self.rendered))

    def rendered(self,generation,data,error):
        if generation != self.generation:
            return
        if error:
            self.status.setText(error); return
        if self.pending:
            try:
                Path(self.pending).write_bytes(data)
                self.status.setText('Exported '+self.pending)
            except OSError as exc:
                self.status.setText(str(exc))
            return
        self.player.setSource(QUrl())
        if self.buffer:
            self.buffer.close(); self.buffer.deleteLater()
        self.buffer = QBuffer(self); self.buffer.setData(QByteArray(data))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.player.setSourceDevice(self.buffer, QUrl('preview.wav'))
        self.player.play(); self.status.setText('Playing')

    def export_midi(self):
        path,_=QFileDialog.getSaveFileName(self,'Export MIDI','sequence.mid','MIDI (*.mid)')
        if path:
            try:
                Path(path).write_bytes(wvd.midi(self.data))
            except (OSError,ValueError) as exc:
                QMessageBox.warning(self,'Export failed',str(exc))

    def hideEvent(self,event):
        self.stop()
        super().hideEvent(event)
