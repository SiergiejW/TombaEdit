# Format notes and provenance

Reference material provided by the user was treated as format research, not as
instructions to execute the old scripts. The Python 2 ungammer and hardcoded
export scripts were read, not run or imported. All source projects were read-only.

## Disc and file links

`disc.py` reads ISO9660 primary directories directly from MODE1/2048,
MODE1/2352, and MODE2/2352 data tracks. CUE `FILE`, `TRACK`, and `INDEX 01` determine
the data track and its physical start. Logical reads cross sector boundaries
without including sync/header/ECC bytes. Directory cycles, invalid extents and
unsupported interleaved/multi-extent records are rejected.

`catalog.py` locates the executable's File Link Array using the disc's actual
LDSYS extent and size. It validates BCD minute/second/frame records and matches
LBAs against ISO files. Conversion is `(minute * 60 + second) * 75 + frame - 150`.
The supplied USA executable resolves to byte offset `0x699A0`. This is discovered,
not a hardcoded regional offset. Trailing unverified records are excluded.

## LDAR and GAM

Each LDAR record is 20 bytes: ignored word, 16-bit file ID, 16-bit type code,
32-bit RAM destination, then either a byte count plus zero, or four 16-bit VRAM
coordinates/dimensions. Nonzero file IDs begin a source stream; ID zero continues
the previous decompressed source at the current offset. A `FFFF` file ID with a
zero footer ends a group. The final RAM pointer array is checked against the
actual group boundaries. Group zero is the base; following groups correspond to
section indices starting at zero.

GAM has an eight-byte header (`GAM\0`, decoded length), then little-endian 16-bit
command words consumed LSB-first. Zero bits emit literals; one bits read an
8-bit backward distance and 8-bit count. References can overlap. Unlike the old
scripts, truncated input and invalid references produce diagnostics, not silent
padding. All supplied-disc asset ranges pass the strict decoder.

VRAM is 1024 × 512 **16-bit words**. Apply the base uploads, then the selected
section uploads in order. Use replacement, including zero pixels, rather than
the old exporter's bitwise OR operation. WMD texture-page and CLUT fields select
PSX pages/palettes; SPR pages use a configurable shard-relative base. PSX colour
zero is transparent, while `0x8000` remains visible black. STP blending itself
is not reproduced yet.

## WFM3

The implementation follows the supplied `wfm3spec.txt`: 144-byte master header,
16-bit absolute glyph offsets, eight-byte glyph headers, low-nibble-first 4bpp
glyphs, a relative dialogue-offset table, and 16-bit dialogue words. Glyph IDs
use twelve bits; sound/blink flags are preserved. Control argument counts differ:
for example FFF9 and FFF7 take one word, while FFFA/FFF8/FFF6 take two. Unknown
controls stop decoding explicitly because their argument lengths are unknown.

## WMD

The supplied WMD binaries were compared with the existing OBJ dumps. A 32-bit
object count is followed by that many absolute 32-bit object pointers. Each
object has eight batches, each beginning with a 32-bit primitive count:

| Batch | GPU family | Vertices | Colours | Textured |
| --- | --- | --- | --- | --- |
| 0 | FT3 / 24 | 3 | 1 | yes |
| 1 | FT4 / 2C | 4 | 1 | yes |
| 2 | GT3 / 34 | 3 | 3 | yes |
| 3 | GT4 / 3C | 4 | 4 | yes |
| 4 | F3 / 20 | 3 | 1 | no |
| 5 | F4 / 28 | 4 | 1 | no |
| 6 | G3 / 30 | 3 | 3 | no |
| 7 | G4 / 38 | 4 | 4 | no |

Textured primitives contain CLUT/page words, RGB/command words, and one
`<hhhBB>` XYZ/UV record per vertex. Untextured primitives contain RGB/command
words, eight-byte coordinate records, eight-byte normal records (one per colour),
and a final four-byte word. Primitive sizes and GPU families are checked, and
each object must end exactly at its next pointer. Quads split into triangles
`0,1,2` and `3,2,1`. The preview converts coordinates to `(x,-y,-z)`. Texture
modulation treats 128 as neutral; raw texture commands bypass vertex colour.

All 4,931 objects passed these boundary checks. A separate comparison of 153
AREA00 objects against the user's OBJ exports found identical triangle positions.
This does not verify APD placement, runtime transforms, or PSX blending.

## Sources

- User-provided `Tomba/archive/TOMBAdoc.md`, `wfm3spec.txt`, `WFM3tool.py`,
  `SPRtool.py`, `SPRtool2.py`, and `ungammer.py` (vervalkon's research/tools).
- User-provided `Tomba/ldar-tool/LDAR-tool/LDARtool.py`, `filetypes.py`, and
  `links.py`, plus the LDAR workflow diagram and type/area list.
- User-provided `Tomba/models/Tomba 1 model dump` (OBJ comparison).
- `Tomba310` / Tomba2Edit for the requested classic desktop interaction pattern.
- [hansbonini/psx_tomba](https://github.com/hansbonini/psx_tomba),
  [game formats](https://github.com/hansbonini/psx_tomba/blob/main/docs/game-formats.md),
  and [regional file analysis](https://github.com/hansbonini/psx_tomba/blob/main/docs/file-analysis.md).
  Some reference descriptions conflict; real-disc validation takes precedence.

No game assets, disc content, reference OBJ files, or adjacent-project source
files are copied into the application package.
