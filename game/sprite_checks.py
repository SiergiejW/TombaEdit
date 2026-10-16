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
    'partially_correct': 'Partially correct, remaining sprites look wrong',
    'other': 'Other',
}


def review_target(project, asset, data, context, frame_count):
    from game.label_store import local_identity
    identity = dict(build=local_identity(project),
                    spr_sha256=hashlib.sha256(data).hexdigest(),
                    ldar=asset.ldar, group=asset.group,
                    record_offset=asset.record_offset, vram_context=context)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return dict(id=key, **identity, rom=project.disc.source.name,
                source=asset.source.path if asset.source else None,
                type=f'0x{asset.code:04X}', offset=asset.offset,
                bytes=len(data), sprites=frame_count)


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
        if status is not None and status not in STATUSES:
            raise ValueError('Unknown sprite check status')
        doc = self.document()
        doc['entries'] = [entry for entry in doc['entries'] if entry['id'] != target['id']]
        if status is not None:
            doc['entries'].append(dict(target, status=status,
                                       preview=preview or {},
                                       updated_at=datetime.now(timezone.utc).isoformat()))
        self.write(self.path, doc)

