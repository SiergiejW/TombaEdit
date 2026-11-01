"""Derive premade helper CLUTs from user-owned coloured building references.

Matches colour-independent pixel-equality patterns, then verifies complete 8x8
index/colour correspondences. No reference pixels or ROM textures are bundled.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from formats.archive.ldar import Project
from formats.level.cut_village_view import byte_indices, colours


def signatures(a):
    h,w=a.shape
    equal=np.stack([a[:h-2,:w-2]==a[dy:h-2+dy,dx:w-2+dx]
                    for dy,dx in ((0,1),(1,0),(1,1),(0,2),(2,0),(2,2))],-1)
    windows=sliding_window_view(equal,(4,4),axis=(0,1)).reshape(h-5,w-5,-1)
    return np.packbits(windows,axis=-1),windows.sum(-1)


def source_lookup(indices):
    sig,count=signatures(indices)
    lookup=defaultdict(list)
    for y,x in zip(*np.nonzero((count>=12)&(count<=80))):
        if y+8<=indices.shape[0] and x+8<=indices.shape[1]:
            lookup[sig[y,x].tobytes()].append((int(y),int(x)))
    return lookup


def match(indices,lookup,path):
    with Image.open(path) as image:
        rgba=np.asarray(image.convert('RGBA'),dtype=np.uint32)
    if min(rgba.shape[:2])<8:return {},[],0
    rgb=rgba[:,:,0]|rgba[:,:,1]<<8|rgba[:,:,2]<<16|rgba[:,:,3]<<24
    sig,count=signatures(rgb)
    votes=defaultdict(Counter)
    heldout=[]
    matched=0
    for y,x in zip(*np.nonzero((count>=12)&(count<=80))):
        if y+8>rgb.shape[0] or x+8>rgb.shape[1]:continue
        positions=lookup.get(sig[y,x].tobytes(),())
        if len(positions)!=1:continue
        sy,sx=positions[0]
        one=indices[sy:sy+8,sx:sx+8].ravel()
        two=rgb[y:y+8,x:x+8].ravel()
        if len(np.unique(one))<12:continue
        pairs=np.unique(np.stack([one,two],-1),axis=0)
        # The whole patch must give a one-to-one index/colour map, not just similar edges.
        if len(np.unique(pairs[:,0]))!=len(pairs) or len(np.unique(pairs[:,1]))!=len(pairs):continue
        matched+=1
        target=heldout if matched%7==0 else None
        for index,color in pairs:
            if index and color>>24:
                if target is not None:target.append((int(index),int(color)&0xFFFFFF))
                else:votes[int(index)][int(color)&0xFFFFFF]+=1
    return votes,heldout,matched


def fill(indices,anchors):
    """Harmonic fill over index adjacency; supplied anchors remain unchanged."""
    adjacency=np.zeros((256,256),dtype=np.float64)
    for a,b in ((indices[:,:-1],indices[:,1:]),(indices[:-1,:],indices[1:,:])):
        a,b=a.ravel().astype(int),b.ravel().astype(int)
        valid=(a!=0)&(b!=0)&(a!=b)
        np.add.at(adjacency,(a[valid],b[valid]),1)
    adjacency+=adjacency.T
    palette=np.zeros((256,3),dtype=np.float64)
    known=sorted(anchors)
    for index,color in anchors.items():palette[index]=color
    unknown=[i for i in range(1,256) if i not in anchors and adjacency[i].sum()>0]
    if unknown and known:
        laplacian=np.diag(adjacency.sum(1))-adjacency
        palette[unknown]=np.linalg.lstsq(laplacian[np.ix_(unknown,unknown)],
                                        -laplacian[np.ix_(unknown,known)]@palette[known],rcond=None)[0]
    isolated=[i for i in range(1,256) if i not in anchors and adjacency[i].sum()==0]
    if isolated:palette[isolated]=palette[known].mean(0)
    return np.clip(palette,0,255)


def word(rgb):
    r,g,b=np.rint(np.asarray(rgb)*31/255).astype(int).clip(0,31)
    return int(r|(g<<5)|(b<<10)) or 0x8000


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cue',required=True)
    parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('formats/level/building_helper_cluts.json'))
    parser.add_argument('--preview',type=Path,default=Path('work/cut_village_research/helper_cluts'))
    args=parser.parse_args()
    project=Project(args.cue)
    targets=((61,'Wood / Lumberjack Town','wood-overlay-restored.png'),
             (76,'Stone / Stonetown','stone-overlay-restored.png'),
             (80,'Iron Town','iron-overlay-restored.png'),(86,'Reunited town',None))
    entries=[]
    unavailable=[]
    args.preview.mkdir(parents=True,exist_ok=True)
    for group,name,primary in targets:
        indices=byte_indices(project.vram('SYS/LDAR17.BIN',1,group)[:256,128:512])
        lookup=source_lookup(indices)
        anchors={};records=[];checks=[]
        paths=sorted(args.references.glob('*.png'),key=lambda p:(p.name!=primary,p.name))
        for path in paths:
            votes,heldout,matched=match(indices,lookup,path)
            if not matched:continue
            used=0
            for index,counts in votes.items():
                color,count=counts.most_common(1)[0]
                if index in anchors or count<8 or count/sum(counts.values())<0.98:continue
                anchors[index]=np.array([color&255,color>>8&255,color>>16&255],dtype=np.float64)
                used+=1
            checks.extend(heldout)
            records.append(dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                matched_patches=matched,anchored_indices=used))
            print(group,path.name,matched,'patches;',used,'new anchors',flush=True)
        frequency=np.bincount(indices.ravel(),minlength=256)
        coverage=sum(frequency[i] for i in anchors)/max(1,frequency[1:].sum())
        if len(anchors)<32 or coverage<0.6:
            if group == 86:
                rgb = np.array([[min(255, i*1.10+6), min(255, i*.92+3), i*.72] for i in range(256)])
                words = [0] + [word(c) for c in rgb[1:]]
                entries.append(dict(group=group, name='Reunited town · warm stone / timber proposal',
                    type='reconstructed_helper_not_original', proposal=True,
                    indices_sha256=hashlib.sha256(indices.tobytes()).hexdigest(), words=words,
                    observed_indices=[], filled_indices=list(range(1,256)),
                    used_indices=(np.flatnonzero(frequency[1:])+1).astype(int).tolist(),
                    observed_pixel_coverage=0.0, sources=[],
                    method='Artistic warm stone/timber RGB ramp over texture index order; all colours proposed, not original.'))
                Image.fromarray(colours(np.array(words,dtype=np.uint16))[indices]).save(args.preview/'group_86_proposal.png')
                (args.preview/'group_86_proposal.clut').write_bytes(np.array(words,dtype='<u2').tobytes())
                print('86: artistic warm stone/timber proposal; no recovered colour claim', flush=True)
                continue
            unavailable.append(dict(group=group,name=name,observed_indices=len(anchors),
                                    observed_pixel_coverage=round(float(coverage),6),
                                    reason='Insufficient ground-truth pixel coverage for a reliable default helper',sources=records))
            print(f'{group}: no trustworthy helper ({len(anchors)} anchors); retaining grey fallback',flush=True)
            continue
        rgb=fill(indices,anchors)
        words=[0]+[word(c) for c in rgb[1:]]
        comparisons=[(words[i],word([c&255,c>>8&255,c>>16&255])) for i,c in checks if i in anchors]
        agreement=sum(a==b for a,b in comparisons)/max(1,len(comparisons))
        entry=dict(group=group,name=name,type='reconstructed_helper_not_original',
                   label=f'HELPER CLUT: {name} · ground truth · reconstructed, not original',
                   indices_sha256=hashlib.sha256(indices.tobytes()).hexdigest(),words=words,
                   observed_indices=sorted(anchors),filled_indices=[i for i in range(1,256) if i not in anchors],
                   used_indices=(np.flatnonzero(frequency[1:])+1).astype(int).tolist(),
                   observed_pixel_coverage=round(float(coverage),6),heldout_color_agreement=round(agreement,6),
                   heldout_comparisons=len(comparisons),sources=records,
                   method='Exact 8x8 index/colour patch correspondences; dominant >=98% at >=8 votes; '
                          'every seventh match held out; unobserved colours harmonic-filled; quantized RGB555')
        entries.append(entry)
        image=Image.fromarray(colours(np.array(words,dtype=np.uint16))[indices])
        image.save(args.preview/f'group_{group}_helper.png')
        (args.preview/f'group_{group}_helper.clut').write_bytes(np.array(words,dtype='<u2').tobytes())
        print(group,'FINAL',len(anchors),'anchors; pixel coverage',round(coverage,5),'heldout',round(agreement,5),flush=True)
    result=dict(format=1,description='Premade building helper palettes derived from user-supplied ground-truth reconstructions. '
                'These are not recovered original game CLUTs. Zero is transparent; unobserved entries are estimated.',
                entries=entries,unavailable_groups=unavailable)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':main()
