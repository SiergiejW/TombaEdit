"""Manual whole-SPR reviews, keyed by exact resource and loading context."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


STATUSES = {
    'wrong_clut': 'Wrong CLUT',
    'ok': 'Everything OK',
    'wrong_sprites': 'Wrong sprites',
    'wrong_animation': 'Wrong animation',
    'partially_correct': 'Partially correct, remaining sprites look wrong',
    'other': 'Other',
}


def default_store():
    from game.label_autosave import labels_path
    from PyQt6.QtCore import QStandardPaths
    store = SpriteChecks(labels_path().with_name('sprite_checks.json'))
    previous = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation)) / 'sprite_checks.json'
    if not store.path.exists() and previous.is_file() and previous != store.path:
        store.write(store.path, SpriteChecks(previous).document())
    return store


def review_badge(entries):
    if not entries:
        return ''
    return '\u2705' if all(e.get('status') == 'ok' for e in entries) else '\u2757'


def review_statuses(kind='spr'):
    values = {key: value for key, value in STATUSES.items()
              if key != ('wrong_sprites' if kind == 'anim' else 'wrong_animation')}
    if kind == 'anim':
        values['partially_correct'] = 'Partially correct, remaining animations look wrong'
    return values


def review_target(project, asset, data, context, frame_count, review_kind='spr'):
    from game.label_store import local_identity
    identity = dict(build=local_identity(project),
                    spr_sha256=hashlib.sha256(data).hexdigest(),
                    ldar=asset.ldar, group=asset.group,
                    record_offset=asset.record_offset, vram_context=context)
    if review_kind != 'spr':
        identity['review_kind'] = review_kind
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return dict(id=key, **identity, rom=project.disc.source.name,
                source=asset.source.path if asset.source else None,
                type=f'0x{asset.code:04X}', offset=asset.offset,
                bytes=len(data), sprites=frame_count)


def entry_target(bank, kind, entry):
    identity = (bank['id'], kind, entry)
    return dict(bank, id=hashlib.sha256(json.dumps(identity).encode()).hexdigest(),
                parent_review_id=bank['id'], entry_kind=kind, entry_id=entry)


class SpriteChecks:
    def __init__(self, path):
        self.path = Path(path)

    def document(self):
        if not self.path.exists():
            return dict(schema='tombaedit.sprite-checks', version=1, entries=[])
        doc = json.loads(self.path.read_text(encoding='utf-8-sig'))
        if (not isinstance(doc, dict) or doc.get('schema') != 'tombaedit.sprite-checks' or doc.get('version') != 1
                or not isinstance(doc.get('entries'), list)):
            raise ValueError('Unsupported sprite checks JSON. The existing file was not changed.')
        for entry in doc['entries']:
            if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
                raise ValueError('Invalid sprite check entry. The existing file was not changed.')
        return doc

    def get(self, key):
        return next((entry for entry in self.document()['entries'] if entry['id'] == key), None)

    @staticmethod
    def write(path, document):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
                name = stream.name
                json.dump(document, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            os.replace(name, path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def set(self, target, status, preview=None):
        self.set_many([target], status, preview)

    def set_many(self, targets, status, preview=None):
        if status is not None and status not in STATUSES and status != 'looks_off':
            raise ValueError('Unknown sprite check status')
        targets = {target['id']: target for target in targets}
        if not targets:
            return
        doc = self.document()
        doc['entries'] = [entry for entry in doc['entries'] if entry['id'] not in targets]
        if status is not None:
            updated = datetime.now(timezone.utc).isoformat()
            doc['entries'].extend(dict(target, status=status, preview=preview or {}, updated_at=updated)
                                  for target in targets.values())
        self.write(self.path, doc)

