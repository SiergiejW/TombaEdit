"""Disc STR browser with MDEC frames, XA soundtrack and exports."""
from pathlib import Path
from PyQt6.QtCore import (Qt, QTimer, QThreadPool, QRunnable, QObject,
                         pyqtSignal, QBuffer, QByteArray, QIODevice, QUrl)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QPushButton, QLabel, QSlider, QFileDialog, QMessageBox)
from formats.movie.psxstr import Movie
from formats.movie.movie_screen import MovieScreen, clock
from formats.movie import movie_export


class Signals(QObject):
    ready = pyqtSignal(int, object, str)


class Job(QRunnable):
    def __init__(self, generation, callback, receiver):
        super().__init__()
        self.generation, self.callback = generation, callback
        self.signals = Signals(); self.signals.ready.connect(receiver)

    def run(self):
        try:
            result, error = self.callback(), ''
        except Exception as exc:
            result, error = None, str(exc)
        try:
            self.signals.ready.emit(self.generation, result, error)
        except RuntimeError:
            pass


class MoviePanel(QWidget):
    def __init__(self, project, selected=None):
        super().__init__()
        self.project = project
        self.entries = [e for e in project.disc.files if e.path.upper().endswith('.STR')]
        self.movie = None; self.generation = 0; self.frame_busy = False
        self.last_frame = -1; self.frames = {}
        self.pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        split = QSplitter()
        self.list = QTableWidget(len(self.entries), 3)
        self.list.setHorizontalHeaderLabels(['Movie', 'Disc bytes', 'LBA'])
        self.list.verticalHeader().hide()
        self.list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i,e in enumerate(self.entries):
            for col,value in enumerate((Path(e.path).name, f'{e.size:,}', str(e.lba))):
                self.list.setItem(i,col,QTableWidgetItem(value))
        self.list.currentCellChanged.connect(self.choose)
        split.addWidget(self.list)
        right = QWidget(); right_layout = QVBoxLayout(right)
        self.screen = MovieScreen(); right_layout.addWidget(self.screen,1)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.valueChanged.connect(self.show_frame); right_layout.addWidget(self.timeline)
        transport = QHBoxLayout()
        for title,callback in [('First',lambda:self.show_frame(0)),('Previous',lambda:self.step(-1)),
                               ('Play / Pause',self.toggle),('Stop',self.stop),
                               ('Next',lambda:self.step(1)),('Last',self.last)]:
            button = QPushButton(title); button.clicked.connect(callback); transport.addWidget(button)
        self.clock = QLabel('0:00.0 / 0:00.0'); transport.addWidget(self.clock)
        right_layout.addLayout(transport)
        exports = QHBoxLayout()
        for title,callback in [('Save frame...',self.save_frame),('Save all frames...',self.save_frames),
                               ('Save video...',self.save_video),('Save sound...',self.save_audio),
                               ('Save .STR...',self.save_str)]:
            button=QPushButton(title);button.clicked.connect(callback);exports.addWidget(button)
        right_layout.addLayout(exports)
        self.status = QLabel('Select a movie.');self.status.setWordWrap(True)
        right_layout.addWidget(self.status)
        split.addWidget(right);split.setSizes([320,900]);layout.addWidget(split)
        self.player=QMediaPlayer(self);self.output=QAudioOutput(self);self.output.setVolume(.75)
        self.player.setAudioOutput(self.output)
        self.buffer=None
        self.timer=QTimer(self);self.timer.setInterval(15);self.timer.timeout.connect(self.tick)
        if self.entries:
            row=next((i for i,e in enumerate(self.entries) if e.path==selected),0)
            self.list.setCurrentCell(row,0)

    def choose(self,row,_col,*unused):
        if row<0 or row>=len(self.entries):return
        self.stop();self.generation+=1;self.movie=None;self.frames.clear();self.last_frame=-1
        self.screen.show_message('Indexing movie...');self.status.setText('Reading MDEC frame and XA sound sector indexes...')
        e=self.entries[row];disc=self.project.disc
        callback=lambda:Movie(Path(e.path).name,disc.path,disc.start+e.lba,
                              e.size//2048,disc.stride,disc.payload_offset)
        self.pool.start(Job(self.generation,callback,self.indexed))

    def indexed(self,generation,movie,error):
        if generation!=self.generation:return
        if error:
            self.screen.show_message('Movie unavailable');self.status.setText(error);return
        self.movie=movie
        self.timeline.blockSignals(True);self.timeline.setRange(0,len(movie.frames)-1)
        self.timeline.setValue(0);self.timeline.blockSignals(False)
        self.status.setText(f'{len(movie.frames)} frames | {movie.width} x {movie.height} | {movie.fps:.2f} fps | '+
                            ('XA sound' if movie.has_audio else 'video only'))
        self.clock.setText(f'0:00.0 / {clock(movie.duration)}')
        self.show_frame(0)

    def show_frame(self,index):
        if not self.movie or not self.movie.frames:return
        index=max(0,min(index,len(self.movie.frames)-1))
        self.timeline.blockSignals(True);self.timeline.setValue(index);self.timeline.blockSignals(False)
        self.clock.setText(f'{clock(index/self.movie.fps)} / {clock(self.movie.duration)}')
        if index in self.frames:
            self.screen.show_frame(self.frames[index]);self.last_frame=index;return
        if self.frame_busy:return
        movie=self.movie;self.frame_busy=True
        self.pool.start(Job(self.generation,lambda: (index,movie.frame(index)),self.decoded))

    def decoded(self,generation,result,error):
        if generation!=self.generation:return
        self.frame_busy=False
        if error:self.status.setText(error);return
        index,rgb=result;self.frames[index]=rgb
        if len(self.frames)>90:self.frames.pop(next(iter(self.frames)))
        if index==self.timeline.value():
            self.screen.show_frame(rgb);self.last_frame=index
        else:self.show_frame(self.timeline.value())

    def step(self,diff):self.show_frame(self.timeline.value()+diff)
    def last(self):
        if self.movie:self.show_frame(len(self.movie.frames)-1)

    def toggle(self):
        if self.timer.isActive():self.timer.stop();self.player.pause();return
        if not self.movie:return
        if self.movie.has_audio and self.buffer is None:
            self.status.setText('Decoding XA soundtrack...')
            self.pool.start(Job(self.generation,self.movie.wav,self.audio_ready))
            return
        self.player.play() if self.movie.has_audio else None
        self.timer.start()

    def audio_ready(self,generation,data,error):
        if generation!=self.generation:return
        if error:self.status.setText(error);return
        self.buffer=QBuffer(self);self.buffer.setData(QByteArray(data))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.player.setSourceDevice(self.buffer,QUrl('movie.wav'))
        self.player.setPosition(round(self.timeline.value()/self.movie.fps*1000))
        self.player.play();self.timer.start()
        self.status.setText('Playing with XA sound')

    def tick(self):
        if not self.movie:return
        if self.movie.has_audio:
            index=round(self.player.position()*self.movie.fps/1000)
        else:
            index=self.timeline.value()+1
            self.timer.setInterval(max(1,round(1000/self.movie.fps)))
        if index>=len(self.movie.frames):self.stop();return
        self.show_frame(index)

    def stop(self):
        self.timer.stop();self.player.stop()
        if self.buffer:
            self.player.setSource(QUrl());self.buffer.close();self.buffer.deleteLater();self.buffer=None

    def save_frame(self):
        if not self.movie:return
        path,_=QFileDialog.getSaveFileName(self,'Save frame',f'{self.movie.name}_{self.timeline.value():05d}.png','PNG (*.png)')
        if path:
            self.export_job(lambda:movie_export.save_png(path,self.movie.frame(self.timeline.value())))

    def save_frames(self):
        if not self.movie:return
        directory=QFileDialog.getExistingDirectory(self,'Save all frames')
        if directory:
            m=self.movie;self.export_job(lambda:movie_export.write_sequence(directory,Path(m.name).stem,(m.frame(i) for i in range(len(m.frames)))))

    def save_video(self):
        if not self.movie:return
        path,_=QFileDialog.getSaveFileName(self,'Save video',Path(self.movie.name).stem+'.mp4','MP4 (*.mp4);;MKV (*.mkv);;AVI (*.avi)')
        if path:
            m=self.movie;self.export_job(lambda:movie_export.write_video(path,m,(m.frame(i) for i in range(len(m.frames))),m.wav()))

    def save_audio(self):
        if not self.movie or not self.movie.has_audio:return
        path,_=QFileDialog.getSaveFileName(self,'Save soundtrack',Path(self.movie.name).stem+'.wav','Wave audio (*.wav)')
        if path:self.export_job(lambda:Path(path).write_bytes(self.movie.wav()))

    def save_str(self):
        if not self.movie:return
        path,_=QFileDialog.getSaveFileName(self,'Save original STR',self.movie.name,'STR movie (*.str)')
        if path:self.export_job(lambda:Path(path).write_bytes(self.movie.sectors_bytes()))

    def export_job(self,callback):
        self.status.setText('Exporting...')
        self.pool.start(Job(self.generation,callback,self.exported))

    def exported(self,generation,result,error):
        if generation==self.generation:self.status.setText(error or 'Export complete.')

    def hideEvent(self,event):
        self.stop();super().hideEvent(event)
