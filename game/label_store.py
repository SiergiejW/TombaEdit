"""Settings persistence using the same labels schema as Tomba2Edit."""
import json
import re
from game.labels import LabelSet, from_document, load, labels_dir
from pathlib import Path

SHARED_KEY = 'labels/shared-content-v1'


def content_identity(key):
    return re.fullmatch(r'[0-9a-f]{16}(?:[0-9a-f]{48})?', key) is not None


def document(labels):
    return dict(name=labels.name, build=labels.build, serial=labels.serial,
                bins=labels.bins, areas={f'{k:02X}': v for k, v in labels.areas.items()},
                entries=[dict(content=e.content, start=f'{e.start:X}', end=f'{e.end:X}',
                              type=e.kind, name=e.name) for e in labels.entries.values()])


def from_json(text):
    return from_document(json.loads(text))


def shared_content(settings, preferred=''):
    """One content library, migrating old per-disc entries without copies.

    Folder/section labels remain scoped to their build because they are
    positional. Exact byte hashes, including named ADPCM samples, are global.
    Existing shared entries win conflicts; otherwise prefer the open build.
    """
    try:
        shared = from_json(settings.value(SHARED_KEY, '') or json.dumps(document(LabelSet())))
    except (ValueError, TypeError):
        shared = LabelSet()
    old_sets = []
    keys = sorted(k for k in settings.allKeys() if k.startswith('labels/') and k != SHARED_KEY)
    keys.sort(key=lambda k: k != 'labels/' + preferred)
    for key in keys:
        try:
            old = from_json(settings.value(key, ''))
        except (ValueError, TypeError):
            continue
        portable = {k: v for k, v in old.entries.items() if content_identity(k)}
        if portable:
            for digest, entry in portable.items():
                shared.entries.setdefault(digest, entry)
            old_sets.append((key, old))
    if old_sets:
        # Save the complete shared copy before retiring redundant entries.
        settings.setValue(SHARED_KEY, json.dumps(document(shared), ensure_ascii=False))
        settings.sync()
        status = settings.status() if hasattr(settings, 'status') else 0
        if int(getattr(status, 'value', status)) != 0:
            return shared
        for key, old in old_sets:
            old.entries = {k: v for k, v in old.entries.items() if not content_identity(k)}
            settings.setValue(key, json.dumps(document(old), ensure_ascii=False))
    return shared


def builtin_library(serial, directory=None):
    """Content names from every shipped set; positional names only locally."""
    result = LabelSet(serial=serial, build=serial)
    paths = sorted(Path(directory or labels_dir()).glob('*.json'))
    paths.sort(key=lambda p: p.stem == serial)
    for path in paths:
        try:
            incoming = load(path)
        except ValueError:
            continue
        result.entries.update({k: v for k, v in incoming.entries.items()
                               if content_identity(k) or incoming.serial == serial or path.stem == serial})
        if incoming.serial == serial or path.stem == serial:
            result.bins.update(incoming.bins)
            result.areas.update(incoming.areas)
    return result
