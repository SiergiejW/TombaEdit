"""An optional, asynchronous offline translation pane for WFM dialogue."""
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFileDialog
from gui.widgets.image_view import text_view
from formats.text.translation import worker, model_metadata, translatable, TranslationError


class Signals(QObject):
    ready = pyqtSignal(int, str)


class Request(QRunnable):
    def __init__(self, serial, folder, text):
        super().__init__()
        self.serial, self.folder, self.text = serial, folder, text
        self.signals = Signals()

    def run(self):
        try:
            result = worker.translate(self.folder, self.text)
        except Exception as exc:
            result = f'Translation unavailable: {exc}'
        self.signals.ready.emit(self.serial, result)


class TranslationPane(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.folder = str(self.settings.value('translation/model', '') or '')
        self.serial, self.text = 0, ''
        self.pending = None
        self.busy = False
        self.pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.enabled = QCheckBox('Translate Japanese to English offline')
        self.enabled.setChecked(self.settings.value('translation/enabled', False, type=bool))
        tools.addWidget(self.enabled, 1)
        choose = QPushButton('Choose model...')
        choose.clicked.connect(self.choose_model)
        tools.addWidget(choose)
        layout.addLayout(tools)
        self.source = text_view('')
        self.output = text_view('Enable translation and choose a local model. No text is sent online.')
        layout.addWidget(QLabel('Decoded text'))
        layout.addWidget(self.source, 1)
        layout.addWidget(QLabel('English · machine translation'))
        layout.addWidget(self.output, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.start)
        self.enabled.toggled.connect(self.toggle)

    def choose_model(self):
        folder = QFileDialog.getExistingDirectory(self, 'Local Japanese-to-English model (CAT safetensors or Argos)', self.folder)
        if not folder:
            return
        try:
            model_metadata(folder)
        except TranslationError as exc:
            self.output.setPlainText(str(exc))
            return
        self.folder = folder
        self.settings.setValue('translation/model', folder)
        self.enabled.setChecked(True)
        self.set_text(self.text)

    def toggle(self, enabled):
        self.settings.setValue('translation/enabled', enabled)
        self.set_text(self.text)

    def set_text(self, text):
        self.serial += 1
        self.text = text
        self.source.setPlainText(text)
        self.pending = None
        self.timer.stop()
        if not self.enabled.isChecked():
            self.output.setPlainText('Enable translation and choose a local model. No text is sent online.')
            return
        try:
            japanese = translatable(text)
        except TranslationError as exc:
            self.output.setPlainText(str(exc))
            return
        if not japanese:
            self.output.setPlainText(text)
        elif not self.folder:
            self.output.setPlainText('Choose a local CAT-Translate safetensors model or an extracted Argos model folder.')
        else:
            self.output.setPlainText('Translating offline... The model loads on first use.')
            self.pending = (self.serial, self.folder, text)
            self.timer.start()

    def start(self):
        if self.busy or self.pending is None:
            return
        self.busy = True
        request = Request(*self.pending)
        self.pending = None
        request.signals.ready.connect(self.ready)
        self.request = request
        self.pool.start(request)

    def ready(self, serial, result):
        self.busy = False
        if serial == self.serial:
            self.output.setPlainText(result)
        if self.pending is not None:
            self.timer.start()
