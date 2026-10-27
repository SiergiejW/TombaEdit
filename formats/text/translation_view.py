"""Controls and the current entry of a shared offline translation session."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFileDialog
from gui.widgets.image_view import text_view
from formats.text.translation import model_metadata, translatable, TranslationError
from formats.text.translation_session import TranslationSession


class TranslationPane(QWidget):
    def __init__(self, session=None):
        super().__init__()
        self.session = session or TranslationSession(parent=self)
        self.text = ''
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.enabled = QCheckBox('Auto-translate all WFM text')
        self.enabled.setToolTip('Preload English for every text bank on this disc, including unopened entries.')
        tools.addWidget(self.enabled, 1)
        choose = QPushButton('Choose model...')
        choose.clicked.connect(self.choose_model)
        tools.addWidget(choose)
        layout.addLayout(tools)
        self.progress = QLabel()
        self.progress.setWordWrap(True)
        layout.addWidget(self.progress)
        self.source = text_view('')
        self.output = text_view('')
        layout.addWidget(QLabel('Decoded original text'))
        self.decoding = QLabel()
        self.decoding.setWordWrap(True)
        self.decoding.hide()
        layout.addWidget(self.decoding)
        layout.addWidget(self.source, 1)
        layout.addWidget(QLabel('English · machine translation'))
        layout.addWidget(self.output, 1)
        self.enabled.toggled.connect(lambda value: self.session.configure(enabled=value))
        self.session.changed.connect(self.refresh)
        self.refresh()

    def choose_model(self):
        folder = QFileDialog.getExistingDirectory(self, 'Local Japanese-to-English model (CAT safetensors or Argos)', self.session.folder)
        if not folder:
            return
        try:
            model_metadata(folder)
        except TranslationError as exc:
            self.output.setPlainText(str(exc))
            return
        self.session.configure(folder=folder)

    def set_text(self, text, note=''):
        self.text = text
        self.source.setPlainText(text)
        self.decoding.setText(note)
        self.decoding.setVisible(bool(note))
        self.session.request_text(text)

    def refresh(self):
        self.enabled.blockSignals(True)
        self.enabled.setChecked(self.session.enabled)
        self.enabled.blockSignals(False)
        self.progress.setText(self.session.status())
        value = self.session.translations.get(self.text)
        if value is None:
            try:
                needs_translation = translatable(self.text)
                if not needs_translation:
                    value = self.text
                elif not self.session.folder:
                    value = 'Choose a local model to translate this entry.'
                else:
                    value = self.session.error or 'Waiting for translation... The selected entry is prioritised; the model loads on first use.'
            except TranslationError as exc:
                value = str(exc)
        if self.output.toPlainText() != value:
            self.output.setPlainText(value)
