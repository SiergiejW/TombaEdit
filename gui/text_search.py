"""Modeless whole-disc phrase search, sharing the background text-bank reader."""
import re
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox,
    QLabel, QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, QAbstractItemView)
from formats.text import export


def searchable(text):
    # Japanese dialogue can wrap halfway through a word. English wraps
    # separate words; keep a space there so phrases remain searchable.
    text = re.sub(r'(?<=[\u3040-\u30ff\u3400-\u9fff])\r?\n(?=[\u3040-\u30ff\u3400-\u9fff])', '', text)
    return ' '.join(text.split())


class TextSearchDialog(QDialog):
    def __init__(self, parent, session, open_entry=None):
        super().__init__(parent)
        self.session, self.open_entry = session, open_entry
        self.setWindowTitle('Search for text · all WFM banks')
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(850, 440)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.phrase = QLineEdit()
        self.phrase.setPlaceholderText('Enter a phrase in Japanese or English…')
        self.phrase.setClearButtonEnabled(True)
        row.addWidget(self.phrase, 1)
        self.case = QCheckBox('Match case')
        self.words = QCheckBox('Whole words')
        row.addWidget(self.case); row.addWidget(self.words)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.where = QComboBox()
        for label, value in [('Original + translated text', 'both'), ('Original text', 'original'),
                             ('English translations', 'translated')]:
            self.where.addItem(label, value)
        row.addWidget(self.where)
        self.status = QLabel()
        row.addWidget(self.status, 1)
        self.open_button = QPushButton('Open entry')
        row.addWidget(self.open_button)
        layout.addLayout(row)
        self.results = QTreeWidget()
        self.results.setHeaderLabels(['Bank / location', 'Entry', 'Matching text'])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.results.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.results.setColumnWidth(0, 265); self.results.setColumnWidth(1, 105)
        self.results.header().setStretchLastSection(False)
        self.results.setColumnWidth(2, 900)
        layout.addWidget(self.results, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.search)
        self.phrase.textChanged.connect(self.schedule)
        self.case.toggled.connect(self.schedule)
        self.words.toggled.connect(self.schedule)
        self.where.currentIndexChanged.connect(self.schedule)
        self.session.changed.connect(self.schedule)
        self.results.itemActivated.connect(self.activate)
        self.open_button.clicked.connect(lambda: self.activate(self.results.currentItem()))
        self.phrase.returnPressed.connect(self.open_first)
        self.session.discover()
        self.search()
        self.phrase.setFocus()

    def schedule(self, *_):
        self.timer.start()

    def search(self):
        phrase = searchable(self.phrase.text())
        self.results.clear()
        if self.session.reading:
            loading = ' · reading remaining banks…'
        elif self.session.discovery_error:
            loading = ' · ' + self.session.discovery_error
        else:
            loading = ''
        if not phrase:
            self.status.setText(f'{len(self.session.banks)} banks available{loading}')
            self.open_button.setEnabled(False)
            return
        flags = 0 if self.case.isChecked() else re.IGNORECASE
        expression = re.escape(phrase)
        if self.words.isChecked():
            expression = r'(?<!\w)' + expression + r'(?!\w)'
        pattern = re.compile(expression, flags)
        where = self.where.currentData()
        total = 0
        self.results.setUpdatesEnabled(False)
        for key, bank in self.session.banks.items():
            texts = self.session.texts.get(key) or [export.plain(d) for d in bank.wfm.dialogues]
            for index, original in enumerate(texts):
                translated = self.session.translations.get(original)
                options = ([original] if where != 'translated' else []) + ([translated] if translated is not None and where != 'original' else [])
                match = next((text for text in options if pattern.search(searchable(text))), None)
                if match is None:
                    continue
                total += 1
                dialogue = bank.wfm.dialogues[index]
                row = QTreeWidgetItem([f'{bank.place} · {bank.name}', getattr(dialogue, 'name', f'{index:03d}'),
                                       match.replace('\n', ' ↵ ')])
                row.setData(0, Qt.ItemDataRole.UserRole, (key, index))
                row.setToolTip(0, f'{bank.source} @0x{bank.offset:X}')
                row.setToolTip(1, f'Entry index {index}, stream offset 0x{dialogue.offset:X}')
                row.setToolTip(2, match)
                self.results.addTopLevelItem(row)
        self.results.setUpdatesEnabled(True)
        self.status.setText(f'{total} matching entries · {len(self.session.banks)} banks{loading}')
        self.open_button.setEnabled(bool(total))
        if total:
            self.results.setCurrentItem(self.results.topLevelItem(0))

    def open_first(self):
        self.timer.stop()
        self.search()
        self.activate(self.results.currentItem())

    def activate(self, item, *_):
        if item is None:
            return
        key, index = item.data(0, Qt.ItemDataRole.UserRole)
        bank = self.session.banks.get(key)
        if bank is None:
            return
        if self.open_entry:
            self.open_entry(bank, index)
        else:
            from formats.text.wfm_viewer import DialogueView
            window = QDialog(self)
            window.setWindowTitle(f'{bank.name} · entry {index:03d}')
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            layout = QVBoxLayout(window)
            viewer = DialogueView(bank.wfm, bank.name, bank.source, bank.offset, self.session)
            layout.addWidget(viewer)
            viewer.entries.setCurrentRow(index)
            window.resize(1100, 680)
            window.show()
        # Keep the results available for following more matches.
