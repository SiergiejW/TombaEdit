"""Portable, atomic label saves beside the app, independent of Qt settings."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from game.labels import LabelSet, from_document
from game.label_store import content_identity, document, SHARED_KEY


def labels_path():
    directory = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    return directory / 'tombaedit_labels.json'


def snapshot(labels):
    return deepcopy(document(labels))


class LabelAutosave:
    def __init__(self, path=None):
        self.path = Path(path) if path else labels_path()
        self.backup = self.path.with_suffix('.json.bak')

    @staticmethod
    def empty():
        return dict(schema='tombaedit.labels', version=1, **document(LabelSet(
            name='TombaEdit portable labels', build='shared')), builds={}, migrated_settings=[])

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or data.get('schema') != 'tombaedit.labels' or data.get('version') != 1:
            raise ValueError('Unsupported portable labels JSON')
        from_document(data)
        if not isinstance(data.get('builds'), dict) or not isinstance(data.get('migrated_settings', []), list):
            raise ValueError('Invalid portable label build list')
        for local in data['builds'].values():
            from_document(local)
        return data

    def read(self):
        if not self.path.exists():
            return self.empty()
        return self.validate(json.loads(self.path.read_text(encoding='utf-8-sig')))

    @staticmethod
    def atomic_write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
                name = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def write(self, data):
        self.validate(data)
        raw = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        if self.path.exists():
            old = self.path.read_bytes()
            if old == raw:
                return
            self.validate(json.loads(old.decode('utf-8-sig')))
            self.atomic_write(self.backup, old)
        self.atomic_write(self.path, raw)

    def migrate(self, settings):
        """Copy old registry names once without deleting the recovery source."""
        data = self.read()
        source = settings.fileName()
        if source in data.get('migrated_settings', []):
            return
        shared = {e['content']: e for e in data['entries']}
        keys = sorted(k for k in settings.allKeys() if k.startswith('labels/'))
        keys.sort(key=lambda k: k != SHARED_KEY)
        for key in keys:
            try:
                incoming = from_document(json.loads(settings.value(key, '')))
            except (ValueError, TypeError):
                continue
            for entry in document(incoming)['entries']:
                if content_identity(entry['content']):
                    shared.setdefault(entry['content'], entry)
            local = document(incoming)
            local['entries'] = [e for e in local['entries'] if not content_identity(e['content'])]
            if key != SHARED_KEY and (local['entries'] or local['bins'] or local['areas']):
                data['builds'].setdefault(key[len('labels/'):], local)
        data['entries'] = list(shared.values())
        data.setdefault('migrated_settings', []).append(source)
        self.write(data)

    def load(self, build, serial):
        data = self.read()
        result = from_document(data)
        local = data['builds'].get(build)
        if local is None and serial not in ('TOMBA.EXE', 'MAIN0.EXE'):
            local = data['builds'].get(serial)
        if local:
            local = from_document(local)
            result.entries.update(local.entries)
            result.bins.update(local.bins)
            result.areas.update(local.areas)
        return result

    def save(self, labels, previous=None):
        """Apply only this window's changes, preserving other builds and windows."""
        now = snapshot(labels)
        before = previous or document(LabelSet())
        data = self.read()
        shared = {e['content']: e for e in data['entries']}
        local = data['builds'].setdefault(labels.build, document(LabelSet(
            name=labels.name, build=labels.build, serial=labels.serial)))
        positional = {e['content']: e for e in local['entries']}
        old_entries = {e['content']: e for e in before['entries']}
        current = {e['content']: e for e in now['entries']}
        for key, entry in current.items():
            if old_entries.get(key) != entry:
                (shared if content_identity(key) else positional)[key] = entry
        for key in old_entries.keys() - current.keys():
            (shared if content_identity(key) else positional).pop(key, None)
        local['entries'] = list(positional.values())
        for section in ('bins', 'areas'):
            for key, value in now[section].items():
                if before[section].get(key) != value:
                    local[section][key] = value
            for key in before[section].keys() - now[section].keys():
                local[section].pop(key, None)
        data['entries'] = list(shared.values())
        self.write(data)
        return now
