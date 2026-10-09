"""The dialog that exports a disc's text."""
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QDialogButtonBox,
    QLabel, QFileDialog, QLineEdit, QHBoxLayout, QPushButton)
from formats.archive.ldar import table_name
from formats.text import export
from game.areas import AREAS, language_name


class TextExportDialog(QDialog):
    """What to export, how to lay it out, and in which form."""

    def __init__(self, parent, project, area=None, language=None, stem='text'):
        super().__init__(parent)
        self.setWindowTitle('Export text')
        self.project, self.stem = project, stem
        layout = QVBoxLayout(self)
        form = QFormLayout()
        names = sorted({table_name(path) for path in project.ldars})
        areas = sorted({number for _, number in names if number >= 0})
        languages = sorted({tongue for tongue, _ in names if tongue is not None})
        self.scope = QComboBox()
        self.scope.addItem('Whole disc', None)
        for number in areas:
            self.scope.addItem(f'AREA{number:02d} - {AREAS.get(number, "")}'.rstrip(' -'), number)
        if area in areas:
            self.scope.setCurrentIndex(areas.index(area) + 1)
        form.addRow('Text of:', self.scope)
        self.language = QComboBox()
        self.language.addItem('Every language', None)
        for tongue in languages:
            self.language.addItem(language_name(tongue), tongue)
        if language in languages:
            self.language.setCurrentIndex(languages.index(language) + 1)
        if languages:
            form.addRow('Language:', self.language)
        self.kind = QComboBox()
        for kind, (label, suffix) in export.FORMATS.items():
            self.kind.addItem(f'{label} ({suffix})', kind)
        self.kind.setToolTip('JSON holds everything, for tools. The script keeps each control code as a tag. '
                             'Plain text keeps only what is read on screen. CSV is one row an entry.')
        form.addRow('Format:', self.kind)
        self.layout_box = QComboBox()
        for key, label in export.LAYOUTS.items():
            self.layout_box.addItem(label, key)
        form.addRow('Written as:', self.layout_box)
        self.controls = QCheckBox('Keep the script with control codes beside the plain text')
        self.controls.setChecked(True)
        self.controls.setToolTip('In JSON and CSV, each entry carries its script as well as its plain text.')
        form.addRow('', self.controls)
        self.raw = QCheckBox('Include the raw words of each entry (JSON)')
        self.raw.setToolTip('Glyph numbers and control words with their arguments, as they are stored.')
        form.addRow('', self.raw)
        self.unknown = QComboBox()
        self.unknown.addItem('[g0A3]  the glyph\'s number', '[g{:03X}]')
        self.unknown.addItem('\u25A1  a box', '\u25A1')
        self.unknown.addItem('?', '?')
        self.unknown.addItem('nothing', '')
        self.unknown.setToolTip('What to write for a glyph no character is known for. Characters are given to '
                                'glyphs on a bank\'s Glyphs tab.')
        form.addRow('Unread glyphs as:', self.unknown)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.target = QLineEdit()
        browse = QPushButton('Browse...')
        browse.clicked.connect(self.browse)
        row.addWidget(self.target, 1); row.addWidget(browse)
        layout.addLayout(row)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Export')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.layout_box.currentIndexChanged.connect(self.describe)
        self.kind.currentIndexChanged.connect(self.describe)
        self.describe()
        self.resize(560, self.sizeHint().height())

    def describe(self):
        one = self.layout_box.currentData() == 'one'
        self.note.setText('One file is written.' if one else
                          'A folder is filled with one file for each ' + ('area.' if self.layout_box.currentData() == 'area'
                                                                           else 'text bank.'))
        self.target.setPlaceholderText('File to write' if one else 'Folder to fill')

    def browse(self):
        kind = self.kind.currentData()
        if self.layout_box.currentData() == 'one':
            label, suffix = export.FORMATS[kind]
            path, _ = QFileDialog.getSaveFileName(self, 'Export text', self.stem + suffix, f'{label} (*{suffix})')
        else:
            path = QFileDialog.getExistingDirectory(self, 'Folder for the text')
        if path:
            self.target.setText(path)

    def accept(self):
        if not self.target.text().strip():
            self.browse()
        if self.target.text().strip():
            super().accept()

    def options(self):
        return dict(area=self.scope.currentData(), language=self.language.currentData(),
                    kind=self.kind.currentData(), layout=self.layout_box.currentData(),
                    controls=self.controls.isChecked(), raw=self.raw.isChecked(),
                    unknown=self.unknown.currentData(), target=Path(self.target.text().strip()))
