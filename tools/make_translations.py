"""Translate the text of Japanese discs with a local model and keep a JSON file of it for each build.

    python tools/make_translations.py "rom/Ore! Tomba (Japan).cue" "rom/PrePre Vol. 8 (Japan).cue" ...

Every message of every text bank of each disc that has no translation yet goes to the model (CAT-Translate 7b by
default). What the model has said is kept in a local cache (rom/translator/translation-cache-ja.json, which is not
part of the program) after every few messages, so a run can be stopped and started again where it stopped.
Messages that still show an unknown glyph as [gNNN] are left alone: they are translated once the glyph is read.

For each disc the tool then writes the file of its build, formats/text/translations/<build>.json, from the cache:
the messages of that build in the order of the disc, with their English, and the same messages bank by bank, so
that the translations of two builds can be put side by side with any tool. Two discs of one build give one file.
The program reads these files by itself; see formats/text/premade.py.

The model runs from rom/translator, with the portable runtime found there (CUDA PyTorch and bitsandbytes) when it
exists.
"""
import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding='utf8', errors='replace')
    except (AttributeError, ValueError):
        pass
sys.path.insert(0, str(ROOT))

FOLDER = ROOT / 'formats' / 'text' / 'translations'
CACHE = ROOT / 'rom' / 'translator' / 'translation-cache-ja.json'
GPU_ERROR = 3                                   # the worker's exit code when the graphics card failed
LEGACY = FOLDER / 'ja-CAT-Translate-7b.json'    # where the first runs kept everything: one file for all builds


def use_runtime(model):
    for candidate in (Path(model).resolve().parent / 'runtime', ROOT / 'rom' / 'translator' / 'runtime'):
        if (candidate / 'torch' / '__init__.py').is_file():
            sys.path.insert(0, str(candidate))
            return candidate
    return None


def read_disc(path):
    """(build name, [(bank name, file, offset, [(index, text)])]) for a disc: every entry of every text bank."""
    from formats.archive.ldar import Project
    from formats.text import export
    from game.builds import executable
    project = Project(path)
    found = executable(project)
    name = found.build.name if found is not None else Path(path).stem
    banks = []
    for bank in export.collect(project) or []:
        banks.append((bank.name, bank.source, bank.offset,
                      [(i, export.plain(d)) for i, d in enumerate(bank.wfm.dialogues)]))
    return name, banks


def translatable_texts(banks):
    """The different messages of a disc worth translating, in disc order, and how many had unknown glyphs."""
    from formats.text.translation import translatable, TranslationError
    ordered, skipped = {}, 0
    for _name, _source, _offset, entries in banks:
        for _index, text in entries:
            try:
                if translatable(text):
                    ordered.setdefault(text, None)
            except TranslationError:
                skipped += 1
    return list(ordered), skipped


def slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def load_cache(path):
    import json
    path = Path(path)
    if path.is_file():
        data = json.loads(path.read_text(encoding='utf8'))
        return dict(data.get('entries', {})), data.get('model', '')
    if path == CACHE and LEGACY.is_file():
        # The first runs kept everything in one file next to the build files: take it over.
        data = json.loads(LEGACY.read_text(encoding='utf8'))
        print(f'taking over the {len(data.get("entries", {}))} translations of {LEGACY.name}', flush=True)
        return dict(data.get('entries', {})), data.get('model', '')
    return {}, ''


def write_builds(discs, cache, model, folder):
    """The file of each build, from what the cache holds. `discs` is [(build name, banks)]."""
    import json
    folder = Path(folder)
    made = {}
    for name, banks in discs:
        file = made.setdefault(name, dict(order={}, banks=[]))
        for bank in banks:
            file['banks'].append(bank)
            for _index, text in bank[3]:
                if text in cache:
                    file['order'].setdefault(text, cache[text])
    for name, file in made.items():
        # Two discs of one build share their banks: list each bank once.
        seen, banks = set(), []
        for bank_name, source, offset, entries in file['banks']:
            if (source, offset) in seen:
                continue
            seen.add((source, offset))
            banks.append(dict(bank=bank_name, file=source, offset=f'0x{offset:X}',
                              messages=[dict(index=i, original=text, translation=cache.get(text))
                                        for i, text in entries]))
        total = sum(len(b['messages']) for b in banks)
        data = dict(format=1, language='ja', build=name, model=model,
                    builds={name: len(file['order'])}, messages=total, translated=len(file['order']),
                    entries=file['order'], banks=banks)
        path = folder / f'{slug(name)}.json'
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf8')
        print(f'  {path.name}: {len(file["order"])} different messages translated, {total} entries in {len(banks)} banks',
              flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('discs', nargs='*', help='the .cue (or .bin/.iso) of each disc')
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--model', default=str(ROOT / 'rom' / 'translator' / 'CAT-Translate-7b'))
    parser.add_argument('--cache', default=str(CACHE), help='where the model\'s translations are kept between runs')
    parser.add_argument('--folder', default=str(FOLDER), help='where the file of each build is written')
    parser.add_argument('--save-every', type=int, default=20)
    parser.add_argument('--limit', type=int, default=0, help='stop after this many new translations (to try it out)')
    parser.add_argument('--dry-run', action='store_true', help='only count what would be translated')
    parser.add_argument('--files-only', action='store_true', help='write the build files from the cache, translate nothing')
    args = parser.parse_args()
    if args.worker:
        print(f'model {args.model}; runtime {use_runtime(args.model)}', flush=True)
        return work(args)
    if not args.discs:
        parser.error('name at least one disc')

    cache, model = load_cache(args.cache)
    model = model or Path(args.model).name
    print(f'{len(cache)} translations in the cache', flush=True)
    discs, pending = [], {}
    for disc in args.discs:
        print(disc, flush=True)
        try:
            name, banks = read_disc(disc)
        except Exception as exc:
            print(f'  skipped: {type(exc).__name__}: {exc}', flush=True)
            continue
        texts, skipped = translatable_texts(banks)
        print(f'  {name}: {len(banks)} banks, {len(texts)} different messages, {skipped} entries left for later '
              f'(unknown glyphs)', flush=True)
        discs.append((name, banks))
        for text in texts:
            if text not in cache:
                pending.setdefault(text, None)
    todo = list(pending)
    print(f'{len(todo)} messages to translate', flush=True)
    if args.dry_run:
        return
    code = 0
    if todo and not args.files_only:
        # The model runs in a process of its own: PyTorch's libraries and Qt's, which reading a disc loads, do
        # not live in one process on Windows. A graphics-card error ends that process (it cannot go on after
        # one); the cache keeps what was done, and a new process takes up the rest. A message that fails right
        # after a fresh start is left out.
        import json
        import subprocess
        import tempfile
        left_out = []
        for _attempt in range(80):
            todo = [text for text in todo if text not in cache and text not in left_out]
            if not todo:
                break
            with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf8') as handle:
                json.dump(dict(todo=todo, model=model), handle, ensure_ascii=False)
            try:
                code = subprocess.call([sys.executable, str(Path(__file__).resolve()), '--worker', handle.name,
                                        '--model', args.model, '--cache', args.cache, '--save-every', str(args.save_every),
                                        '--limit', str(args.limit)])
            finally:
                Path(handle.name).unlink(missing_ok=True)
            before = len(cache)
            cache, model = load_cache(args.cache)
            model = model or Path(args.model).name
            if code != GPU_ERROR:
                break
            if len(cache) == before:
                left_out.append(todo[0])
                print(f'  left out after a graphics-card error: {todo[0][:60]!r}', flush=True)
            else:
                print(f'  graphics-card error after {len(cache) - before} messages: starting the model again', flush=True)
        if left_out:
            print(f'{len(left_out)} messages could not be translated', flush=True)
    write_builds(discs, cache, model, args.folder)
    if Path(args.cache) == CACHE and LEGACY.is_file():
        LEGACY.unlink()         # the build files replace the one file for everything
        print(f'removed {LEGACY.name}', flush=True)
    sys.exit(code)


def work(args):
    """The translating half: runs the model over the messages in the file `--worker` names, into the cache."""
    import json
    from formats.text.translation import translate
    cache, _model = load_cache(args.cache)
    given = json.loads(Path(args.worker).read_text(encoding='utf8'))
    todo, model = given['todo'], given['model']
    path = Path(args.cache)

    def save():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(format=1, language='ja', model=model, entries=cache),
                                   ensure_ascii=False, indent=0), encoding='utf8')
    done, started = 0, time.time()
    crashed = False
    try:
        for text in todo:
            try:
                result = translate(args.model, text).strip()
            except Exception as exc:
                print(f'  failed: {str(exc)[:200]}', flush=True)
                if 'CUDA' in str(exc) or 'out of memory' in str(exc).lower():
                    crashed = True
                    break
                continue
            if not result or result.startswith('Translation unavailable'):
                print(f'  no translation: {result[:80]}', flush=True)
                if result.startswith('Translation unavailable') and done == 0:
                    break           # the model itself did not load: say so once and stop
                continue
            cache[text] = result
            done += 1
            if done % 10 == 1 or done < 6:
                rate = (time.time() - started) / done
                left = (len(todo) - done) * rate
                print(f'  {done}/{len(todo)} | {rate:.1f} s each | about {left / 60:.0f} min left | '
                      f'{text[:30].replace(chr(10), " ")} -> {result[:60].replace(chr(10), " ")}', flush=True)
            if done % args.save_every == 0:
                save()
            if args.limit and done >= args.limit:
                break
    finally:
        save()
        print(f'saved {len(cache)} translations in {path}', flush=True)
    if crashed:
        sys.exit(GPU_ERROR)


if __name__ == '__main__':
    main()
