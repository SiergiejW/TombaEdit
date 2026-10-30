"""Offline translations kept with the program, so that nobody needs a translation model to read a known disc.

The folder formats/text/translations/ holds a file for each build, <build>.json, a JSON object

    {"format": 1, "language": "ja", "model": "CAT-Translate-7b", "build": "Japanese retail",
     "builds": {"Japanese retail": 1524},           # how many different messages it translates
     "messages": 7176, "translated": 1524,
     "entries": {"<the Japanese message as the viewer shows it>": "<English>", ...},   # in the order of the disc
     "banks": [{"bank": "WFM D0FF", "file": "AREA00/A003.GAM", "offset": "0x...",
                "messages": [{"index": 0, "original": "...", "translation": "..."}, ...]}, ...]}

made by tools/make_translations.py: `entries` is what the program reads, `banks` the same messages bank by bank for
any other tool. A disc of a known build reads the file of its build first. A message is found by its text, not by
where it is, so a translation also serves a disc of another build that has the same words (the Japanese demo and the
samplers share most of theirs). A message whose text changed (a glyph read differently since) has no premade
translation until the files are made again.
"""
import json
import os
import tempfile
from pathlib import Path

FOLDER = Path(__file__).with_name('translations')
FORMAT = 1


class Premade:
    def __init__(self, entries=None, files=(), by_build=None):
        self.entries = entries or {}
        self.files = list(files)        # [(file name, model, {build: count})]
        self.by_build = by_build or {}  # build name -> its own entries

    def get(self, text, build='', default=None):
        """The translation of a message: the file of `build` first, then the files of the other builds."""
        own = self.by_build.get(build)
        if own is not None and text in own:
            return own[text]
        return self.entries.get(text, default)

    def __len__(self):
        return len(self.entries)

    def __contains__(self, text):
        return text in self.entries

    @property
    def builds(self):
        names = {}
        for _file, _model, builds in self.files:
            for name, count in builds.items():
                names[name] = max(names.get(name, 0), count)
        return names

    @property
    def models(self):
        return sorted({model for _file, model, _builds in self.files if model})

    def covers(self, build_name):
        """True when a file was made from a disc of this build."""
        return build_name in self.builds


_loaded = {}


def load(folder=None):
    """Every translation file of the folder, merged; the later file name wins where two give the same message."""
    folder = Path(folder) if folder else FOLDER
    files = sorted(folder.glob('*.json')) if folder.is_dir() else []
    key = (str(folder), tuple((path.name, path.stat().st_mtime_ns) for path in files))
    if _loaded.get('key') == key:
        return _loaded['value']
    entries, sources, by_build = {}, [], {}
    for path in files:
        try:
            data = json.loads(path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get('format') != FORMAT or not isinstance(data.get('entries'), dict):
            continue
        own = {k: v for k, v in data['entries'].items() if isinstance(k, str) and isinstance(v, str)}
        entries.update(own)
        builds = data.get('builds') if isinstance(data.get('builds'), dict) else {}
        build = data.get('build')
        if isinstance(build, str):
            by_build.setdefault(build, {}).update(own)
        sources.append((path.name, str(data.get('model', '')), builds))
    _loaded.clear()
    _loaded.update(key=key, value=Premade(entries, sources, by_build))
    return _loaded['value']


def save(path, entries, model, builds, language='ja'):
    """Write a plain translation file, replacing the one there; the entries are sorted so that a new run changes
    only the lines it changes. (tools/make_translations.py writes the richer file of a build itself.)"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(format=FORMAT, language=language, model=model, builds=dict(sorted(builds.items())),
                entries=dict(sorted(entries.items())))
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=0, separators=(',', ': '))
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
