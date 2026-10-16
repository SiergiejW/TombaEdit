"""Disposable decoded SPR previews. No executable objects are deserialized."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zlib
from functools import lru_cache
import numpy as np


@lru_cache(maxsize=1)
def revision():
    digest = hashlib.sha256(b'sprite-preview-v1')
    if getattr(sys, 'frozen', False):
        stat = Path(sys.executable).stat()
        digest.update(repr((stat.st_size, stat.st_mtime_ns)).encode())
    else:
        root = Path(__file__).resolve().parents[2]
        paths = [root / name for name in ('gui/main_window/window.py', 'psx/graphics.py',
                 'formats/archive/gam.py', 'formats/archive/ldar.py', 'game/builds.py', 'game/sampler_builds.py')]
        paths += sorted((root / 'formats/level').glob('*.py'))
        paths += sorted((root / 'formats/sprites').glob('*.py'))
        paths += sorted((root / 'game').glob('*.py'))
        for path in paths:
            digest.update(path.read_bytes())
    return digest.hexdigest()


def cache_path(project, node, context):
    from PyQt6.QtCore import QStandardPaths
    disc = project.disc
    stat = disc.path.stat()
    identity = (revision(), str(disc.path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                disc.start, disc.stride, disc.payload_offset, node.ldar, node.group,
                node.record_offset, node.code, node.offset, node.size, context)
    key = hashlib.sha256(repr(identity).encode()).hexdigest()
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / 'sprites' / (key + '.json.gz')


def encode(value, arrays=None):
    from formats.sprites.wpp import Picture
    from formats.annotate import Region
    arrays = {} if arrays is None else arrays
    if isinstance(value, np.ndarray):
        if id(value) in arrays:
            return ['array_ref', arrays[id(value)]]
        number = arrays[id(value)] = len(arrays)
        return ['array', number, value.dtype.str, value.shape, base64.b64encode(value.tobytes()).decode('ascii')]
    if isinstance(value, bytes):
        return ['bytes', base64.b64encode(value).decode('ascii')]
    if isinstance(value, dict):
        return ['dict', [[encode(k, arrays), encode(v, arrays)] for k, v in value.items()]]
    if isinstance(value, (tuple, list, set)):
        tag = 'tuple' if isinstance(value, tuple) else 'set' if isinstance(value, set) else 'list'
        return [tag, [encode(v, arrays) for v in value]]
    if isinstance(value, Picture):
        return ['picture', encode(vars(value), arrays)]
    if isinstance(value, Region):
        return ['region', encode(vars(value), arrays)]
    if isinstance(value, np.generic):
        return value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f'Unsupported cached sprite value: {type(value).__name__}')


def decode(value, arrays=None):
    arrays = {} if arrays is None else arrays
    if not isinstance(value, list):
        return value
    tag = value[0]
    if tag == 'array_ref':
        return arrays[value[1]]
    if tag == 'array':
        dtype = np.dtype(value[2])
        if dtype.hasobject:
            raise ValueError('Object arrays are not sprite data')
        array = np.frombuffer(base64.b64decode(value[4]), dtype).reshape(value[3]).copy()
        arrays[value[1]] = array
        return array
    if tag == 'bytes':
        return base64.b64decode(value[1])
    if tag == 'dict':
        return {decode(k, arrays): decode(v, arrays) for k, v in value[1]}
    if tag in ('tuple', 'list', 'set'):
        return {'tuple': tuple, 'list': list, 'set': set}[tag](decode(v, arrays) for v in value[1])
    if tag == 'picture':
        from formats.sprites.wpp import Picture
        return Picture(**decode(value[1], arrays))
    if tag == 'region':
        from formats.annotate import Region
        return Region(**decode(value[1], arrays))
    raise ValueError('Unknown cached sprite value')


def load(path, node):
    try:
        with gzip.open(path, 'rb') as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            return None
        result = decode(json.loads(raw))
        if not isinstance(result, dict) or 'sprites' not in result or 'vram' not in result:
            return None
        result['node'] = node
        return result
    except (OSError, ValueError, TypeError, KeyError, IndexError, EOFError, RecursionError, OverflowError, zlib.error):
        return None


def save(path, result):
    name = None
    try:
        raw = json.dumps(encode({k: v for k, v in result.items() if k != 'node'}), separators=(',', ':')).encode()
        if len(raw) > 64 * 1024 * 1024:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
            name = stream.name
            stream.write(gzip.compress(raw, compresslevel=1))
        os.replace(name, path)
        # Keep this disposable cache bounded, independently of review JSON.
        files = sorted(path.parent.glob('*.json.gz'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        total = 0
        for index, old in enumerate(files):
            total += old.stat().st_size
            if old != path and (index >= 128 or total > 256 * 1024 * 1024):
                old.unlink()
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    finally:
        if name and os.path.exists(name):
            try:
                os.unlink(name)
            except OSError:
                pass
