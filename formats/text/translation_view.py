"""Controls and the current entry of a shared offline translation session."""
import time
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFileDialog, QMessageBox
from gui.widgets.image_view import text_view
from formats.text.translation import model_metadata, translatable, TranslationError
from formats.text.translation_session import TranslationSession, say


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
        self.choose = QPushButton('Choose model...')
        self.choose.clicked.connect(self.choose_model)
        tools.addWidget(self.choose)
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
            metadata = model_metadata(folder)
        except TranslationError as exc:
            self.output.setPlainText(str(exc))
            self.report(False, folder, str(exc))
            return
        previous = self.session.folder
        self.session.configure(folder=folder)
        # Try the model now, so the answer comes with the choice and not with
        # the first entry that happens to be selected.
        self.started = time.monotonic()
        say(f'translation model: trying {Path(folder).name} ({"CAT-Translate" if metadata.get("backend") == "cat" else "Argos"}, '
            f'{metadata.get("weights", "ctranslate2")}) in {folder}')
        self.choose.setEnabled(False)
        self.progress.setText(f'Trying {Path(folder).name}... A large model can take a minute or more to load.')
        self.session.test_model(folder, lambda ok, message: self.tested(ok, folder, previous, metadata, message))

    def tested(self, ok, folder, previous, metadata, message):
        try:
            self.choose.setEnabled(True)
        except RuntimeError:
            # The pane was closed while a large model was loading: the answer has nowhere to be shown, but the
            # console still gets it.
            name = Path(folder).name or str(folder)
            say(f'translation model: {"ready" if ok else "FAILED"} | {name} | {message}')
            return
        kept = ''
        if not ok and previous and previous != self.session.folder:
            # Do not leave the app on a model that cannot translate.
            self.session.configure(folder=previous)
            kept = f'{Path(previous).name} is still the selected model.'
        self.progress.setText(self.session.status())
        self.report(ok, folder, message, 'CAT-Translate' if metadata.get('backend') == 'cat' else 'Argos', kept)

    def report(self, ok, folder, message, kind='', kept=''):
        """Tell the user whether the model they chose can translate."""
        name = Path(folder).name or str(folder)
        started = getattr(self, 'started', None)
        took = f' after {time.monotonic() - started:.1f}s' if started is not None else ''
        self.started = None
        if ok:
            say(f'translation model: ready | {name} ({kind}){took} | test sentence {self.session.SAMPLE} -> {message}')
        else:
            say(f'translation model: FAILED | {name}{took} | {message}' + (f' | {kept}' if kept else ''))
        if ok:
            QMessageBox.information(self, 'Translation model ready',
                f'{name} ({kind}) loaded and translated a test sentence.\n\n'
                f'{self.session.SAMPLE}  ->  {message}\n\n'
                'It stays selected for this and later sessions.')
        else:
            QMessageBox.warning(self, 'Translation model failed',
                f'{name} could not be used.\n\n{message}\n\n'
                + (kept or 'Choose a different folder, or fix the problem and choose this one again.'))

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
                elif self.session.model_off:
                    value = 'No premade translation, and the translation model is switched off (Display > Translate with a model).'
                elif not self.session.folder:
                    value = 'Choose a local model to translate this entry.'
                else:
                    value = self.session.error or 'Waiting for translation... The selected entry is prioritised; the model loads on first use.'
            except TranslationError as exc:
                value = str(exc)
        if self.output.toPlainText() != value:
            self.output.setPlainText(value)
