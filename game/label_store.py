"""Settings persistence using the same labels schema as Tomba2Edit."""
import json
from game.labels import from_document


def document(labels):
    return dict(name=labels.name, build=labels.build, serial=labels.serial,
                bins=labels.bins, areas={f'{k:02X}': v for k, v in labels.areas.items()},
                entries=[dict(content=e.content, start=f'{e.start:X}', end=f'{e.end:X}',
                              type=e.kind, name=e.name) for e in labels.entries.values()])


def from_json(text):
    return from_document(json.loads(text))
