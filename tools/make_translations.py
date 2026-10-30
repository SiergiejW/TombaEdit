"""Translate the text of Japanese discs with a local model and keep it in formats/text/translations/.

    python tools/make_translations.py "rom/Ore! Tomba (Japan).cue" "rom/PrePre Vol. 8 (Japan).cue" ...

Every message of every text bank of each disc that has no translation yet goes to the model (CAT-Translate 7b by
default), and the result is written after every few messages, so a run can be stopped and started again where it
stopped. Messages that still show an unknown glyph as [gNNN] are left alone: they are translated once the glyph is
read. The model runs from rom/translator, with the portable runtime found there (CUDA PyTorch and bitsandbytes)
when it exists. The result is a JSON file the program reads by itself; see formats/text/premade.py.
"""
import argparse
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


def use_runtime(model):
    for candidate in (Path(model).resolve().parent / 'runtime', ROOT / 'rom' / 'translator' / 'runtime'):
        if (candidate / 'torch' / '__init__.py').is_file():
            sys.path.insert(0, str(candidate))
            return candidate
    return None


def read_disc(path):
    """(build name, [message texts in order]) for a disc."""
    from formats.archive.ldar import Project
    from formats.text import export
    from formats.text.translation import translatable, TranslationError
    from game.builds import executable
    project = Project(path)
    found = executable(project)
    name = found.build.name if found is not None else Path(path).stem
    banks = export.collect(project)
    texts = []
    skipped = 0
    for bank in banks or []:
        for dialogue in bank.wfm.dialogues:
            text = export.plain(dialogue)
            try:
                if translatable(text):
                    texts.append(text)
            except TranslationError:
                skipped += 1
    print(f'  {name}: {len(banks or [])} banks, {len(texts)} messages, {len(set(texts))} different, '
          f'{skipped} left for later (unknown glyphs)', flush=True)
    return name, texts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('discs', nargs='*', help='the .cue (or .bin/.iso) of each disc')
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--model', default=str(ROOT / 'rom' / 'translator' / 'CAT-Translate-7b'))
    parser.add_argument('--out', default=str(ROOT / 'formats' / 'text' / 'translations' / 'ja-CAT-Translate-7b.json'))
    parser.add_argument('--save-every', type=int, default=20)
    parser.add_argument('--limit', type=int, default=0, help='stop after this many new translations (to try it out)')
    parser.add_argument('--dry-run', action='store_true', help='only count what would be translated')
    args = parser.parse_args()
    if args.worker:
        print(f'model {args.model}; runtime {use_runtime(args.model)}', flush=True)
        return work(args)
    if not args.discs:
        parser.error('name at least one disc')

    import json
    from formats.text import premade
    out = Path(args.out)
    entries, builds = {}, {}
    if out.is_file():
        data = json.loads(out.read_text(encoding='utf8'))
        entries, builds = dict(data.get('entries', {})), dict(data.get('builds', {}))
        print(f'{len(entries)} translations already in {out.name}', flush=True)
    pending = {}
    for disc in args.discs:
        print(disc, flush=True)
        name, texts = read_disc(disc)
        builds[name] = len(set(texts))
        for text in texts:
            if text not in entries:
                pending.setdefault(text, None)
    todo = list(pending)
    print(f'{len(todo)} messages to translate', flush=True)
    if args.dry_run:
        return
    if not todo:
        premade.save(out, entries, Path(args.model).name, builds)
        return
    # The model runs in a process of its own: PyTorch's libraries and Qt's, which reading a disc loads, do not
    # live in one process on Windows.
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf8') as handle:
        json.dump(dict(todo=todo, builds=builds), handle, ensure_ascii=False)
    try:
        code = subprocess.call([sys.executable, str(Path(__file__).resolve()), '--worker', handle.name,
                                '--model', args.model, '--out', args.out, '--save-every', str(args.save_every),
                                '--limit', str(args.limit)])
    finally:
        Path(handle.name).unlink(missing_ok=True)
    sys.exit(code)


def work(args):
    """The translating half: runs the model over the messages in the file `--worker` names."""
    import json
    from formats.text import premade
    from formats.text.translation import translate
    out = Path(args.out)
    entries = json.loads(out.read_text(encoding='utf8')).get('entries', {}) if out.is_file() else {}
    given = json.loads(Path(args.worker).read_text(encoding='utf8'))
    todo, builds = given['todo'], given['builds']
    model = Path(args.model).name
    done, started = 0, time.time()
    try:
        for text in todo:
            try:
                result = translate(args.model, text).strip()
            except Exception as exc:
                print(f'  failed: {exc}', flush=True)
                continue
            if not result or result.startswith('Translation unavailable'):
                print(f'  no translation: {result[:80]}', flush=True)
                if result.startswith('Translation unavailable') and done == 0:
                    break           # the model itself did not load: say so once and stop
                continue
            entries[text] = result
            done += 1
            if done % 10 == 1 or done < 6:
                rate = (time.time() - started) / done
                left = (len(todo) - done) * rate
                print(f'  {done}/{len(todo)} | {rate:.1f} s each | about {left / 60:.0f} min left | '
                      f'{text[:30].replace(chr(10), " ")} -> {result[:60].replace(chr(10), " ")}', flush=True)
            if done % args.save_every == 0:
                premade.save(out, entries, model, builds)
            if args.limit and done >= args.limit:
                break
    finally:
        premade.save(out, entries, model, builds)
        print(f'saved {len(entries)} translations in {out}', flush=True)


if __name__ == '__main__':
    main()
