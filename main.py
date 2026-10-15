"""TombaEdit entry point. Usage: python main.py [disc.bin|disc.cue|disc.iso]."""
import sys
import traceback
from pathlib import Path
from version import version


def main():
    if '--version' in sys.argv:
        print(version)
        return 0
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    # Set before QApplication: inserting a GL viewer must not recreate the
    # native top-level window or make the application disappear.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from gui.main_window.window import MainWindow
    app = QApplication(sys.argv)
    from icons.icons import icon
    app.setWindowIcon(icon("app"))
    app.setApplicationName("TombaEdit")
    app.setApplicationVersion(version)
    app.setOrganizationName("TombaEdit")
    def report_error(kind, value, tb):
        from PyQt6.QtWidgets import QMessageBox
        report = "".join(traceback.format_exception(kind, value, tb))
        log = Path(__file__).resolve().parent / "crash.log"
        try:
            with log.open("a", encoding="utf-8") as stream:
                stream.write(report + "\n")
        except OSError:
            pass
        QMessageBox.critical(None, "TombaEdit error", f"{kind.__name__}: {value}\n\nDetails: {log}")
        app.exit(1)
    sys.excepthook = report_error
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: window.open_path(sys.argv[1]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())



