# -*- mode: python ; coding: utf-8 -*-
"""Build the TombaEdit desktop executable with its viewer assets."""
import os
import sys
import shutil
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = Path(SPECPATH)
icon_files = [(str(path), str(path.parent.relative_to(ROOT)))
              for path in (ROOT / 'icons').rglob('*') if path.is_file()
              and path.suffix.lower() in ('.png', '.ico')]
text_files = [(str(ROOT / 'formats' / 'text' / name), 'formats/text')
              for name in ('glyph_dictionary.json', 'glyphs_us.json')]
import PyQt6
plugins = Path(PyQt6.__file__).parent / 'Qt6' / 'plugins' / 'multimedia'
multimedia = [(str(path), 'PyQt6/Qt6/plugins/multimedia')
              for path in plugins.iterdir() if path.is_file()] if plugins.is_dir() else []
label_files = [(str(path), 'labels') for path in (ROOT / 'labels').glob('*.json')]
app_icon = ROOT / 'icons' / 'tomba' / ('tomba1.png' if sys.platform == 'darwin' else 'tomba1.ico')

a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=collect_dynamic_libs('unicorn') + ([(shutil.which('ffmpeg'), '.')] if shutil.which('ffmpeg') else []),
    datas=icon_files + text_files + multimedia + label_files,
    hiddenimports=['PyQt6.QtMultimedia', 'formats.movie.movie_panel',
                   'formats.audio.audio_viewer', 'formats.images.clut_viewer',
                   'formats.collision.structured_viewer',
                   'formats.collision.whm_viewer',
                   'formats.models.four_viewer', 'formats.level.viewer',
                   'formats.level.runtime', 'unicorn', 'unicorn.mips_const',
                   'formats.archive.data_viewer'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'pandas', 'PyQt6.QtQml',
              'PyQt6.QtQuick', 'PyQt6.QtPdf', 'PyQt6.QtWebEngineWidgets'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='TombaEdit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(app_icon),
)
if sys.platform == 'win32':
    # The level editor runs object code in unicorn, which commits its
    # translation buffer on demand from an exception handler it generates
    # at run time. The bootloader is built with Control Flow Guard, under
    # which Windows ends the process instead of calling a handler that was
    # not compiled into a module, so the executable is marked as built
    # without it, the way python.exe is.
    import struct
    GUARD_CF = 0x4000
    with open(exe.name, 'r+b') as stream:
        header = stream.read(4096)
        field = struct.unpack_from('<I', header, 0x3C)[0] + 24 + 70    # DllCharacteristics
        stream.seek(field)
        stream.write(struct.pack('<H', struct.unpack_from('<H', header, field)[0] & ~GUARD_CF))
if sys.platform == 'darwin':
    app = BUNDLE(exe, name='TombaEdit.app', icon=str(app_icon),
                 bundle_identifier='club.tomba.tombaedit')
