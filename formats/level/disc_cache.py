"""What a disc's sections show, kept between sessions.

Working out which objects show which sprite frames runs the game's object
routines for a whole section, and finding the other copies of a bank reads
every load group of the disc. Both depend only on the disc and on this
program, so the results are written beside the sprite previews, one file
per section, and read back the next time instead of being worked out again.
"""
import gzip
import hashlib
import json
import os
import tempfile
import zlib
from pathlib import Path

LIMIT = 512 * 1024 * 1024       # bytes kept for all discs together


def folder(project):
    """Where this disc's analyses live, or None when there is no cache."""
    if '_analysis_folder' not in project.__dict__:
        try:
            from PyQt6.QtCore import QStandardPaths
            from formats.sprites.preview_cache import revision
            disc = project.disc
            stat = disc.path.stat()
            identity = (revision(), str(disc.path), stat.st_size, stat.st_mtime_ns,
                        disc.start, disc.stride, disc.payload_offset)
            key = hashlib.sha256(repr(identity).encode()).hexdigest()[:32]
            root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
            project._analysis_folder = root / 'analysis' / key if str(root) not in ('', '.') else None
        except (OSError, ImportError, AttributeError):
            project._analysis_folder = None
    return project.__dict__['_analysis_folder']


def _file(project, name):
    where = folder(project)
    if where is None:
        return None
    return where / (hashlib.sha256(repr(name).encode()).hexdigest()[:40] + '.json.gz')


def load(project, name):
    """The value saved under `name` for this disc, or None."""
    from formats.sprites.preview_cache import decode
    path = _file(project, name)
    if path is None or not path.exists():
        return None
    try:
        with gzip.open(path, 'rb') as stream:
            saved = json.loads(stream.read())
        if saved.get('name') != repr(name):
            return None
        return decode(saved['value'])
    except (OSError, ValueError, TypeError, KeyError, IndexError, EOFError, RecursionError, zlib.error):
        return None


def save(project, name, value):
    """Keep `value` (what formats.sprites.preview_cache can encode) under
    `name`; a value that cannot be kept is quietly left out."""
    from formats.sprites.preview_cache import encode
    path = _file(project, name)
    if path is None:
        return
    temporary = None
    try:
        raw = json.dumps(dict(name=repr(name), value=encode(value)), separators=(',', ':')).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            stream.write(gzip.compress(raw, compresslevel=1))
        os.replace(temporary, path)
        _trim(path.parent.parent)
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


_trimmed = {}       # cache root -> when it was last measured
TRIM_EVERY = 120    # seconds between measurements of the whole cache


def _trim(root):
    """Drop the oldest files once all discs together pass LIMIT.

    Measuring the cache walks every file, so it is done once in a while, not
    for every file saved, and from the directory listing without a call per
    file."""
    import time
    now = time.monotonic()
    if now - _trimmed.get(root, -TRIM_EVERY) < TRIM_EVERY:
        return
    _trimmed[root] = now
    files, total = [], 0
    try:
        with os.scandir(root) as folders:
            for folder_entry in folders:
                if not folder_entry.is_dir():
                    continue
                with os.scandir(folder_entry.path) as entries:
                    for entry in entries:
                        if entry.name.endswith('.json.gz'):
                            info = entry.stat()
                            files.append((info.st_mtime_ns, info.st_size, entry.path))
                            total += info.st_size
    except OSError:
        return
    if total <= LIMIT:
        return
    kept = 0
    for _, size, path in sorted(files, reverse=True):
        kept += size
        if kept > LIMIT:
            try:
                os.unlink(path)
            except OSError:
                pass
