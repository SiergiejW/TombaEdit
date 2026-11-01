"""Vendor exact, licensed research references from a local decomp checkout.

Fetch upstream explicitly first; this tool never runs game code or changes the checkout.
Usage: python tools/sync_decomp_research.py REPO --ref origin/master --checked-date YYYY-MM-DD
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ('Civilization: complete cut-town evidence', 'docs/CIVILIZATION.md'),
    ('Cut-content inventory and status', 'docs/CUT_CONTENT.md'),
    ('Japanese retail build', 'docs/JP.md'),
    ('Known builds and disc versions', 'docs/BUILDS.md'),
    ('Format documentation', 'docs/FORMATS.md'),
    ('Engine format research', 'notes/formats.md'),
    ('Events and unused-content research', 'notes/secrets.md'),
    ('Native port and authored reconstruction', 'docs/PORT.md'),
    ('Upstream license', 'LICENSE'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo')
    parser.add_argument('--ref', default='origin/master')
    parser.add_argument('--checked-date', required=True)
    args = parser.parse_args()
    def git(*items):
        return subprocess.check_output(['git','-C',args.repo,*items])
    revision = git('rev-parse',args.ref).decode().strip()
    files = []
    # Read all sources before modifying the reference directory.
    sources = [(label,path,git('show',f'{revision}:{path}')) for label,path in DOCUMENTS]
    destination = ROOT/'docs/decomp'
    for label,path,data in sources:
        target = destination/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        files.append(dict(label=label,path=path,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    manifest = dict(repository='https://github.com/afsenovilla/Tombi-Decomp',revision=revision,
                    checked_date=args.checked_date,scope='Cut-village and related retail/build/format/port research; not a game-code import',
                    files=files)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    print(f'Synchronized {len(files)} exact reference files at {revision}')


if __name__ == '__main__':
    main()
