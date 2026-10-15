"""Encode rendered audio without changing playback's WAV buffer."""
import shutil
import subprocess
import sys
from pathlib import Path


def encode_audio(wav, suffix):
    if suffix == '.wav':
        return wav
    if suffix != '.ogg':
        raise ValueError('Choose WAV or OGG audio.')
    bundled = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'ffmpeg.exe'
    encoder = str(bundled) if bundled.is_file() else shutil.which('ffmpeg')
    if not encoder:
        raise ValueError('OGG export requires ffmpeg. Install ffmpeg or choose WAV.')
    result = subprocess.run(
        [encoder, '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0',
         '-vn', '-c:a', 'libvorbis', '-q:a', '5', '-f', 'ogg', 'pipe:1'],
        input=wav, capture_output=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or not result.stdout.startswith(b'OggS'):
        raise ValueError(result.stderr.decode('utf-8', errors='replace').strip() or 'OGG encoding failed.')
    return result.stdout
