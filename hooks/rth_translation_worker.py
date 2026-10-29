"""Start frozen Windows workers before Qt's runtime hook loads QtCore."""
import sys

if sys.platform == 'win32' and '--multiprocessing-fork' in sys.argv:
    # The normal entry point's freeze_support runs after PyInstaller's Qt hook.
    # SentencePiece must instead start in a process that has not loaded Qt.
    from multiprocessing.spawn import freeze_support
    freeze_support()
