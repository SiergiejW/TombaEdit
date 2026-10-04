"""WVD samples and Sony SEQ playback using Tomba2Edit's SPU synthesizer."""
import io
import struct
import wave
from pathlib import Path
from PyQt6.QtCore import (QObject, QRunnable, QThreadPool, pyqtSignal,
                         QByteArray, QBuffer, QIODevice, QUrl)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QComboBox, QLabel, QSpinBox, QFileDialog, QMessageBox)
from formats.audio import seq, sfx, wvd
from gui.widgets.image_view import text_view


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
            self.signals.done.emit(self.generation, self.callback(), '')
        except Exception as exc:
            self.signals.done.emit(self.generation, None, str(exc))


class AudioView(QWidget):
    def __init__(self, data, project, source=''):
        super().__init__()
        self.data, self.project = data, project
        self.is_seq = data.startswith(b'pQES')
        self.bank_data = [] if self.is_seq else wvd.banks(data)
        self.generation = 0
        self.pool = QThreadPool.globalInstance()
        self.pending = None
        layout = QVBoxLayout(self)
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
        self.bank.currentIndexChanged.connect(self.selection_changed)
        bar.addWidget(QLabel('Sound bank:')); bar.addWidget(self.bank, 1)
        self.sample = QComboBox(); bar.addWidget(self.sample)
        self.rate = QSpinBox(); self.rate.setRange(4000, 176400); self.rate.setValue(22050)
        self.rate.setSuffix(' Hz'); self.rate.setVisible(not self.is_seq); bar.addWidget(self.rate)
        layout.addLayout(bar)
        controls = QHBoxLayout()
        play = QPushButton('Play'); play.clicked.connect(lambda: self.render('play'))
        stop = QPushButton('Stop'); stop.clicked.connect(self.stop)
        export = QPushButton('Export WAV...'); export.clicked.connect(lambda: self.render('export'))
        controls.addWidget(play); controls.addWidget(stop); controls.addWidget(export)
        if self.is_seq:
            midi = QPushButton('Export MIDI...'); midi.clicked.connect(self.export_midi); controls.addWidget(midi)
        controls.addStretch(); layout.addLayout(controls)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.details = text_view(''); layout.addWidget(self.details)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self); self.output.setVolume(.5)
        self.player.setAudioOutput(self.output)
        self.player.errorOccurred.connect(lambda error, message: self.status.setText(message))
        self.buffer = None
        self.selection_changed()

    def selection_changed(self):
        self.stop()
        self.sample.clear()
        if self.is_seq:
            # A WVD may carry several VABs; expose them independently.
            try:
                self.bank_data = wvd.banks(self.project.payload(self.project.disc.entries[self.bank.currentData()]))
                for i,b in enumerate(self.bank_data):
                    self.sample.addItem(f'Instrument bank {i}', i)
            except (KeyError, ValueError) as exc:
                self.status.setText(str(exc)); return
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
            for _,number,offset,size in samples:
                self.sample.addItem(f'Sample {number:03d} | {size:,} bytes', (offset,size))
            self.details.setPlainText('\n'.join(f'Sample {n:03d} | offset {o:06X} | {s:,} bytes | loop {sfx.loops(bank,o,s)}' for _,n,o,s in samples))
            self.status.setText('Sample pitch depends on the note used by the game. Choose a preview sample rate.')

    def stop(self):
        self.generation += 1
        self.player.stop()

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
