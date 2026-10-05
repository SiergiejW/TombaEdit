# Format notes

What TombaEdit knows about each format, and how it was established. Addresses
are for the US retail executable, `SCUS_942.36`. Where a description comes
from reading the game's code, the routine is named so it can be checked.

## Disc and file links

`disc.py` reads ISO9660 primary directories directly from MODE1/2048,
MODE1/2352, and MODE2/2352 data tracks. CUE `FILE`, `TRACK`, and `INDEX 01` determine
the data track and its physical start. Logical reads cross sector boundaries
without including sync/header/ECC bytes. Directory cycles, invalid extents and
unsupported interleaved/multi-extent records are rejected.

`catalog.py` locates the executable's File Link Array using the disc's actual
LDSYS extent and size. It validates BCD minute/second/frame records and matches
LBAs against ISO files. Conversion is `(minute * 60 + second) * 75 + frame - 150`.
The US executable resolves to byte offset `0x699A0`. This is discovered,
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
padding. Every asset range on the US disc passes the strict decoder.

VRAM is 1024 × 512 **16-bit words**. Apply the base uploads, then the selected
section uploads in order. Use replacement, including zero pixels, rather than
the old exporter's bitwise OR operation. WMD texture-page and CLUT fields select
PSX pages/palettes. PSX colour zero is transparent, while `0x8000` remains
visible black. STP blending itself is not reproduced yet.

The first load group of `SYS/LDSYS.BIN` is loaded at boot. Its uploads to
the lower half of VRAM stay for the whole game: texture pages 20 and 21 with
the item and effect sprites that SPR slot 4 draws, and their palette rows.
Section VRAM is built on top of them.

Every section uploads a 256 × 32 block of palettes at (128, 480). Its first
column holds Tomba's outfits, one row each.

The loader (routine 80021D70) files each resource pointer by the high nibble
of its type code and the slot in the next nibble: SPR at `1F8002C8`, FOUR at
`1F800310`, WMD at `1F800330`, WPP at `1F800348`, WHM at `1F800308` and APD
at `1F800358`, four bytes per slot.

## WFM3

The implementation follows `wfm3spec.txt`: 144-byte master header,
16-bit absolute glyph offsets, eight-byte glyph headers, low-nibble-first 4bpp
glyphs, a relative dialogue-offset table, and 16-bit dialogue words. Glyph IDs
use twelve bits; sound/blink flags are preserved. Control argument counts differ:
for example FFF9 and FFF7 take one word, while FFFA/FFF8/FFF6 take two. Unknown
controls stop decoding explicitly because their argument lengths are unknown.

## WMD

The decoder was checked against OBJ dumps of the same models. A 32-bit
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
AREA00 objects against those OBJ files found identical triangle positions.
This does not verify APD placement, runtime transforms, or PSX blending.

## SPR

A bank starts with a table of four-byte entries, part count and offset, one
per frame; the offset of the first frame gives the table's length. A part is
sixteen bytes laid out like the texture half of a `POLY_FT4`:

| Offset | Field |
| --- | --- |
| 0 | U, V of the first corner |
| 2 | CLUT word |
| 4 | U, V of the second corner |
| 6 | Texture page word, relative |
| 8 | U, V of the third corner |
| 10 | Width, height |
| 12 | U, V of the fourth corner |
| 14 | Signed X, Y offset from the object's origin |

The draw routine at 800487B0 shows how the object completes a part. The
object's word at `+1E` is added to the part's page word, which is why one
bank can be drawn from different pages. Bit 0 of `+2E` draws the part as
stored, to the right of the origin; with the bit clear the X offset and width
are subtracted instead, mirroring the frame. Bit 0 of `+0D` replaces the
part's CLUT with the word at `+08`, and bit 7 enables semi-transparency.

## Animation scripts

An object's `+24` points at its current animation step (routines 800229FC to
80022C04). A step is eight bytes: frame number, two words not used by the
stepping code, and a control word. The low fourteen bits of the control word
are the step's duration in game frames. The top two bits say what follows:
`0000` the next step, `8000` nothing, the frame holds, and `4000` or `C000` a
jump through the pointer stored after the step, which is how loops are made.

## WPP

Picture banks for sprites whose frames are uploaded on demand. A bank is a
32-bit count, count + 1 offsets with the end of the bank last, and the
entries. Routine 8003A614 unpacks an entry: a flag byte covers the next eight
items, low bit first; a clear bit copies one byte, a set bit reads a count
and a value and repeats the value. The result is a 16-bit width in VRAM
words, a 16-bit height and 4-bit pixels, which 8003B0D4 uploads to the page
slot reserved for Tomba whenever his frame number changes. The SPR bank in
slot 0 has one frame per picture of the bank in WPP slot 0, and SPR slot 5
pairs with WPP slot 2.

WPP slot 3 holds GAM-compressed TIM images behind a bare offset table.

## WHM

Collision, looked up by routine 80042654. The header gives the plane count in
the high byte of its first word and the level width in the third. A table of
16-bit plane offsets follows. A plane has one 16-bit offset per eight units of
X, each leading to a span count and eight-byte spans: attribute, two signed
words, parameter.

An object's plane is its Z, less the section's origin from the table at
8007E9F8, divided by 90. Its column is its X less the origin's X, divided by
8. Objects stand at whole multiples of 90, so plane n is drawn at the origin
plus 90 n. Each entrance of a section has an eight-byte record in the table
at 8007BF78: Tomba's position and a flag word. Bit 0 of the flag makes the
lookup subtract instead, so that the planes run the other way from the
origin; routine 800243E8 copies it to `1F8001C8` on entry. With bit 4 of the
attribute set a span is a solid range between the two Y values. Otherwise it
is a surface whose first word is the Y at the column's left edge and whose
second is the rise across the column. Area 0 keeps its three nearest planes
in WHM slot 1 and continues 270 units deeper in slot 0.

## CLM

Towns are not built from models. Slot 15 (8FFF) of a town section is a TIM
image, 8 bits a pixel with a 256 colour palette: the whole town, drawn in
advance. Slot 14 (8EFF or 8E80) is a map over it: a 16-bit width and height
in cells, then one byte per 8 × 8 pixel cell, row by row. Zero is where
nothing can walk. The non-zero values mark the walkable ground and special
spots such as doorways; values with bit 7 set appear around doorways and
obstacles, and their exact meaning is not established. Placement positions in a town are pixel positions on the
picture. In areas without a picture the same slots hold other data.

## APD and object initialisation

Placement records are sixteen bytes (routine 8005AA98): section, layer, type,
two variant bytes, a flag byte, three signed 16-bit coordinates and further flags.
Records can be relative to the previous absolute one. The layer selects a
table of initialisation routines and the type an entry in it. The level
editor runs that routine on a blank object in an emulator holding the
executable, the area overlay and the loaded banks, then reads the model
pointer, sprite bank, animation script and drawing words back out of the
object.

## Sources

- vervalkon's research and tools: `TOMBAdoc.md`, `wfm3spec.txt`, `WFM3tool.py`,
  `SPRtool.py`, `SPRtool2.py` and `ungammer.py`.
- The LDAR tool (`LDARtool.py`, `filetypes.py`, `links.py`) with its type and
  area lists, and Woolmagician's table of type codes.
- A dump of the game's models as OBJ files, used to check the WMD decoder.
- Tomba2Edit, whose camera and viewer layout this tool follows.
- [hansbonini/psx_tomba](https://github.com/hansbonini/psx_tomba),
  [game formats](https://github.com/hansbonini/psx_tomba/blob/main/docs/game-formats.md),
  and [regional file analysis](https://github.com/hansbonini/psx_tomba/blob/main/docs/file-analysis.md).
  Some reference descriptions conflict; real-disc validation takes precedence.

No game data is included with the application.
