"""Optional real-disc validation: python -m tests.validate_disc path/to/disc.cue."""
import argparse
import json
from collections import Counter
from tombaedit.ldar import Project
from tombaedit.graphics import sprite_frames
from tombaedit.wfm import Wfm
from tombaedit.wmd import parse_wmd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("disc")
    args = parser.parse_args()
    project = Project(args.disc)
    counts = Counter(files=len(project.disc.files), ldars=len(project.ldars))
    errors = list(project.warnings)
    for path, groups in project.ldars.items():
        for group in groups:
            counts["groups"] += 1
            try:
                project.vram(path, group.index)
            except Exception as exc:
                errors.append(f"{path} group {group.index}: {exc}")
            for asset in group.assets:
                counts["assets"] += 1
                try:
                    data = project.asset_data(asset)
                    counts[asset.kind] += 1
                    if asset.kind == "SPR":
                        counts["sprite_frames"] += len(sprite_frames(data))
                    elif asset.kind == "WMD":
                        meshes = parse_wmd(data)
                        counts["mesh_objects"] += len(meshes)
                        counts["triangles"] += sum(len(a[0]) // 3 for m in meshes for a in m.batches.values())
                    elif asset.kind == "WFM":
                        wfm = Wfm(data)
                        counts["dialogues"] += len(wfm.dialogues)
                        counts["dialogue_diagnostics"] += sum(bool(d.warning) for d in wfm.dialogues)
                        counts["glyphs"] += len(wfm.glyphs)
                except Exception as exc:
                    errors.append(f"{path} group {group.index} {asset.label}: {exc}")
    print(json.dumps({"counts": counts, "errors": errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
