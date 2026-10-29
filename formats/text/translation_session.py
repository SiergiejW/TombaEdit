"""One shared, cancellable background translation queue per disc."""
from collections import deque
from pathlib import Path
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QSettings, QTimer, pyqtSignal
from formats.text.translation import worker, translatable, TranslationError
from formats.text import export


class Signals(QObject):
    ready = pyqtSignal(object)


class Task(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = Signals()

    def run(self):
        try:
            value, error = self.work(), ''
        except Exception as exc:
            value, error = None, str(exc)
        self.signals.ready.emit((value, error))


class TranslationSession(QObject):
    changed = pyqtSignal()

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self.project = project
        settings = QSettings()
        self.folder = str(settings.value('translation/model', '') or '')
        self.enabled = settings.value('translation/enabled', False, type=bool)
        self.banks, self.results, self.failures, self.texts = {}, {}, {}, {}
        self.queue = deque()
        self.busy = self.reading = self.discovered = self.closed = False
        self.error = self.discovery_error = ''
        self.active = None
        self.model_test = None
        self.selected = ''
        self.pool = QThreadPool.globalInstance()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.start)

    @property
    def translations(self):
        return self.results.setdefault(self.folder, {})

    def configure(self, enabled=None, folder=None):
        if folder is not None:
            self.folder = str(Path(folder).resolve()) if folder else ''
        if enabled is not None:
            self.enabled = bool(enabled)
        settings = QSettings()
        settings.setValue('translation/model', self.folder)
        settings.setValue('translation/enabled', self.enabled)
        self.error = ''
        self.failures.clear()
        self.rebuild_queue()
        if self.enabled and self.folder:
            self.discover()
        self.changed.emit()

    SAMPLE = 'こんにちは'

    def test_model(self, folder, done):
        """Translate a short sentence with the model in `folder`, in the
        background, then call `done(ok, message)`: the English it gave, or
        why it could not be used. Loading a model takes a while; the first
        entry waits for it in the same worker, so the model loads once."""
        folder = str(Path(folder).resolve())
        task = Task(lambda: worker.translate(folder, self.SAMPLE))

        def finished(response):
            value, failure = response
            if failure:
                done(False, failure)
            elif value.startswith('Translation unavailable:'):
                done(False, value[len('Translation unavailable:'):].strip())
            elif not value.strip():
                done(False, 'The model returned no text for a test sentence.')
            else:
                done(True, value.strip())
            if self.model_test is task:
                self.model_test = None
        task.signals.ready.connect(finished)
        self.model_test = task      # the signal must outlive this call
        self.pool.start(task)

    def discover(self):
        if self.closed or self.reading or self.discovered or self.project is None:
            return
        self.reading = True
        path = str(self.project.disc.source)
        def read():
            from formats.archive.ldar import Project
            return export.collect(Project(path))  # Own reader; no shared seeks/cache mutation.
        self.reader = Task(read)
        self.reader.signals.ready.connect(self.banks_ready)
        self.pool.start(self.reader)

    def banks_ready(self, result):
        if self.closed:
            return
        self.reading, self.discovered = False, True
        banks, self.discovery_error = result
        for bank in banks or []:
            key = (bank.source, bank.offset)
            if key not in self.banks:
                self.banks[key] = bank
                self.texts[key] = [export.plain(d) for d in bank.wfm.dialogues]
        self.rebuild_queue()
        self.changed.emit()

    def register(self, bank):
        key = (bank.source, bank.offset)
        self.banks[key] = bank
        self.texts[key] = [export.plain(d) for d in bank.wfm.dialogues]
        self.rebuild_queue()
        if self.enabled and self.folder:
            self.discover()
        self.changed.emit()

    def originals(self):
        return dict.fromkeys(text for texts in self.texts.values() for text in texts)

    def request_text(self, text):
        """Prioritise the selected entry even while whole-disc preloading is off."""
        self.selected = text
        self.rebuild_queue()
        self.changed.emit()

    def rebuild_queue(self):
        self.timer.stop()
        self.queue.clear()
        if self.closed or not self.folder or self.error:
            return
        wanted = dict.fromkeys([self.selected] + (list(self.originals()) if self.enabled else []))
        for text in wanted:
            if text in self.translations or text in self.failures or self.active == (self.folder, text):
                continue
            try:
                if translatable(text):
                    self.queue.append(text)
            except TranslationError:
                continue
        if self.queue:
            self.timer.start(0)

    def start(self):
        if self.closed or self.busy or not self.queue or self.error:
            return
        self.busy = True
        folder, text = self.folder, self.queue.popleft()
        self.active = (folder, text)
        self.request = Task(lambda: (folder, text, worker.translate(folder, text)))
        self.request.signals.ready.connect(self.ready)
        self.pool.start(self.request)
        self.changed.emit()

    def ready(self, response):
        active = self.active
        self.busy, self.active = False, None
        if self.closed:
            return
        value, failure = response
        folder, text, result = value or (*active, 'Translation unavailable: ' + failure)
        if result.startswith('Translation unavailable:'):
            if folder == self.folder:
                self.failures[text] = result
                if 'shorter dialogue entry' not in result:
                    self.error = result
                    self.queue.clear()
        else:
            self.results.setdefault(folder, {})[text] = result
        self.changed.emit()
        if not self.error and self.queue:
            self.timer.start(0)

    def lookup(self, text):
        if not self.enabled:
            return text
        if text in self.translations:
            return self.translations[text]
        try:
            if not translatable(text):
                return text
        except TranslationError:
            pass
        return None

    def status(self):
        if not self.enabled:
            if self.error:
                return self.error
            if self.busy and self.active and self.active[1] != self.selected:
                return 'Finishing the current translation; your selected entry is next. Bulk preloading is off.'
            if self.busy or self.queue:
                return 'Translating the selected entry... The model loads on first use. Bulk preloading is off.'
            return 'Bulk preloading is off. Selecting an entry translates it; list previews stay original.'
        if not self.folder:
            return 'Choose a local model to preload English for all WFM banks.'
        if self.error:
            return self.error + ' Toggle automatic translation off and on to retry.'
        ready = total = unknown = 0
        for text in self.originals():
            try:
                if translatable(text):
                    total += 1
                    ready += text in self.translations
            except TranslationError:
                unknown += 1
        status = f'English ready: {ready}/{total} messages across {len(self.banks)} WFM banks.'
        if self.reading:
            status += ' Reading remaining banks...'
        elif self.busy or self.queue:
            status += ' Translating in the background...'
        if unknown:
            status += f' {unknown} messages need glyph characters.'
        if self.discovery_error:
            status += ' Some banks could not be read: ' + self.discovery_error
        return status

    def shutdown(self):
        self.closed = True
        self.queue.clear()
        self.timer.stop()


def session_for(project, parent=None):
    if not hasattr(project, '_translation_session'):
        project._translation_session = TranslationSession(project, parent)
    return project._translation_session
