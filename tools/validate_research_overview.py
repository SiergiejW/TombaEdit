"""Check the research overview against JP retail and, optionally, another build.

Run with QT_QPA_PLATFORM=offscreen for a headless Qt check.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication, QTextBrowser
from formats.archive.ldar import Project
from formats.level.cut_research import view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jp_cue')
    parser.add_argument('--other-cue')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    jumps = []
    widget = view(Project(args.jp_cue), lambda *value: jumps.append(value))
    widget.show()
    app.processEvents()
    browser = widget.findChild(QTextBrowser)
    assert 'Electric eel and rubber gloves' in browser.toPlainText()
    assert 'Masakari Chief' in browser.toPlainText()
    url = QUrl('fig:eel')
    before = browser.document().resource(QTextDocument.ResourceType.ImageResource, url)
    assert before is not None and not before.isNull()
    loop = QEventLoop()
    QTimer.singleShot(450, loop.quit)
    loop.exec()
    after = browser.document().resource(QTextDocument.ResourceType.ImageResource, url)
    assert before != after, 'Eel animation did not advance'
    browser.anchorClicked.emit(QUrl('tomba://village/17'))
    assert jumps[-1] == ('village', ('SYS/LDAR17.BIN', 1))
    browser.anchorClicked.emit(QUrl('tomba://asset/eel'))
    assert jumps[-1][0] == 'asset'
    browser.anchorClicked.emit(QUrl('tomba://asset/chief'))
    assert jumps[-1][1].code == 0x32FF and jumps[-1][1].offset == 0x2A24C
    browser.anchorClicked.emit(QUrl('tomba://asset/chief-alt'))
    assert jumps[-1][1].code == 0x37FF and jumps[-1][1].offset == 0x2B814
    widget.close()
    if args.other_cue:
        other = view(Project(args.other_cue), lambda *value: jumps.append(value))
        browser = other.findChild(QTextBrowser)
        assert 'Open Japanese retail to view this image' in browser.toPlainText()
        assert 'tomba://' not in browser.toHtml()
        other.close()
    print('Passed: JP overview, animated eel, direct navigation and non-JP build guard.')


if __name__ == '__main__':
    main()
