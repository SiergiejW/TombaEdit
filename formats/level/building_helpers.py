"""Premade reconstructed building CLUTs, scoped to exact source index pixels."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).with_name('building_helper_cluts.json')


@lru_cache(maxsize=4)
def _load(path, modified):
    try:
        data=json.loads(Path(path).read_text(encoding='utf8'))
        if data.get('format')!=1:return {}
        result={}
        for entry in data['entries']:
            words=entry['words']
            if (entry['type']!='reconstructed_helper_not_original' or len(words)!=256 or words[0]!=0
                    or any(type(v) is not int or not 0<=v<=65535 for v in words)):
                continue
            result[entry['group']]=entry
        return result
    except (OSError,ValueError,KeyError,TypeError):
        return {}


def entries():
    try:return _load(str(DATA),DATA.stat().st_mtime_ns)
    except OSError:return {}


def palette_for(group, indices):
    entry=entries().get(group)
    if entry is None or hashlib.sha256(indices.tobytes()).hexdigest()!=entry['indices_sha256']:
        return None
    estimated_visible = len(set(entry['filled_indices']) & set(np.unique(indices).tolist()))
    estimates = (f'{estimated_visible} estimated visible colours' if estimated_visible else
                 f"{len(entry['filled_indices'])} unused slots estimated")
    label=(f"HELPER CLUT: {entry['name']} · ground-truth reconstruction · "
           f"{entry['observed_pixel_coverage']:.0%} reference-covered pixels · "
           f"{estimates} · not original")
    return label,np.array(entry['words'],dtype=np.uint16)
