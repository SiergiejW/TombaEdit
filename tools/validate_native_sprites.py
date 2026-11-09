"""Read-only retail native sprite trace smoke test; supply your own disc images.

python tools/validate_native_sprites.py --output work/native-sprite-validation.json
python tools/validate_native_sprites.py rom/game.cue --groups 1 6 --codes 34FF 31FF
This records bounded coverage, never a universal visual-correctness claim.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roms', nargs='*', type=Path)
    parser.add_argument('--groups', nargs='+', type=int, default=[1])
    parser.add_argument('--codes', nargs='+', default=['34FF'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    from PyQt6.QtWidgets import QApplication
    from formats.archive.ldar import Project, area_number, table_name
    from formats.sprites.native_render import packet_renderer
    from gui.main_window.window import _prepare_preview
    app = QApplication.instance() or QApplication([])
    roms = args.roms or [ROOT / 'rom' / name for name in (
        'Ore! Tomba (Japan).cue', 'Tomba! (USA).cue',
        'Tombi! (Europe) (En,Es,Pt,Sv,Da).cue')]
    report = []
    for rom in roms:
        project = Project(rom)
        path = next(path for path in project.ldars if area_number(path) == 0 and table_name(path)[0] in (None, 0))
        for index in args.groups:
            if index >= len(project.ldars[path]):
                continue
            for value in args.codes:
                code = int(value, 16)
                nodes = [a for group in project.ldars[path] for a in group.assets if a.code == code]
                if not nodes:
                    continue
                node = nodes[0]
                start = time.perf_counter()
                result = _prepare_preview(project, node, index)
                assert result['native_sprite_mode']
                evidence, packets = result['sprite_evidence'], result['sprite_primitives']
                traced = {frame for frame, item in evidence.items() if item['status'] == 'traced'}
                assert traced == set(packets) == set(result['sprite_pages'])
                assert not traced.intersection(result['sprite_unavailable'])
                renderer = packet_renderer(packets, result['vram'])
                for frame in traced:
                    assert renderer.picture(frame) is not None, (rom.name, frame)
                counts = dict(Counter(item['status'] for item in evidence.values()))
                entry = dict(rom=rom.name, load_table=path, group=index, code=f'{code:04X}',
                             elapsed_seconds=round(time.perf_counter() - start, 3),
                             coverage=counts, assigned_animation_starts=len(result['animation_users']),
                             provenance=result.get('native_build'), notes=result['notes'])
                report.append(entry)
                print(rom.name, f'{code:04X}', f'group {index}', counts, flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    if not report:
        raise SystemExit('No requested sprite bank was found.')


if __name__ == '__main__':
    main()
