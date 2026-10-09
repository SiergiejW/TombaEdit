# Format notes

What TombaEdit knows about each format, and how it was established. Addresses
are for the US retail executable, `SCUS_942.36`. Where a description comes
from reading the game's code, the routine is named so it can be checked.
Other builds have the same routines and tables at other addresses;
[Builds](#builds) lists them.

## Disc and file links

`disc.py` reads ISO9660 primary directories directly from MODE1/2048,
MODE1/2352, and MODE2/2352 data tracks. CUE `FILE`, `TRACK`, and `INDEX 01` determine
the data track and its physical start. Logical reads cross sector boundaries
without including sync/header/ECC bytes. Directory cycles, invalid extents and
unsupported interleaved/multi-extent records are rejected. A CloneCD control
file (`.ccd`) stands for the `.img` of the same name.

`catalog.py` locates the executable's File Link Array using the disc's actual
LDSYS extent and size. It validates BCD minute/second/frame records and matches
LBAs against ISO files. Conversion is `(minute * 60 + second) * 75 + frame - 150`.
The US executable resolves to byte offset `0x699A0`. This is discovered,
not a hardcoded regional offset. Trailing unverified records are excluded.

Three other shapes of the table exist. The Japanese demo spaces its records
24 bytes apart. The February 1998 preview leaves 24 unused indices between
its system and area files. The Pure Pure 09 sampler stores 64-byte records
holding ISO file names (`\TOMBA\A00000.GAM;1`), which the game resolves with
`CdSearchFile` when it starts. The builds without `SYS/LDAR*.BIN` files keep
their load groups in the executable, where `formats/archive/embedded.py`
finds them by the same record layout.

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
at `1F800358`, four bytes per slot. These scratchpad addresses are the same
in every build.

Family 9 is a sound bank (WVD). Retail opens its sound banks by name; the
earlier builds list them in their load groups. A code overlay's record can
give a length longer than the file, counting the cleared memory after it.

The 1997 builds have no slots 14 and 15 for a town's cell map and picture and
file them under placement slots instead (85FF and 81FF on the sampler).
Placement lists are short and a multiple of sixteen bytes long, so a family 8
resource that is neither is named by what it starts with: a TIM header is the
picture, a width and height that fit the length is the cell map.

## WVD

Two sections, each an offset table: the SPU sample bodies of every bank, and
the VAB header of every bank. Builds from 1998 put the bodies first; the 1997
builds put the headers first. The header section is the one whose first entry
starts with `pBAV`.

## WFM3

The implementation follows `wfm3spec.txt`: 144-byte master header,
16-bit absolute glyph offsets, eight-byte glyph headers, low-nibble-first 4bpp
glyphs, a relative dialogue-offset table, and 16-bit dialogue words. Glyph IDs
use twelve bits; sound/blink flags are preserved. Control argument counts differ:
for example FFF9 and FFF7 take one word, while FFFA/FFF8/FFF6 take two. Unknown
controls stop decoding explicitly because their argument lengths are unknown.

The 1997 builds use WFM1. Its header is the first sixteen bytes of the WFM3
one, with the glyph offsets straight after it instead of 128 reserved bytes
later. A glyph's rows each start on a 16-bit word, so a row of ten pixels
takes six bytes where WFM3 packs the pixels end to end. Control FFF4 appears
inside running text and takes no arguments.

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

The 1997 builds lay a textured primitive out as the GPU packet it becomes:
the RGB/command word, then one word per corner with U and V in its low half,
then an eight-byte `<hhh>` position per corner. The high half of the first
corner's word is the CLUT and of the second's the texture page. A Gouraud
primitive has an RGB word for every corner, each in front of its corner's
word: colour, U V and CLUT, colour, U V and page, and so on. That makes
FT3 40 bytes, FT4 52, GT3 48 and GT4 64, against 32, 40, 40 and 52 later.
Untextured primitives are identical in both. A bank is read in the later
layout first and in this one if its batches do not fit.

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

WPP is not the only sprite pixel source. Kokka uses the packed pictures in
slot 2; many other sprites use pixels already resident in section VRAM.
Both the Pictures and Assembled frames tabs keep VRAM visible. A CLUT chosen
in Pictures applies to the whole bank, including all assembled parts;
Assembled frames also offers individual sprite and selected-part overrides.
These are preview and export choices, without modifying disc data.

WPP slot 3 holds GAM-compressed TIM images behind a bare offset table. In
the 1997 builds a bank can also be one TIM on its own, neither packed nor
indexed.

## WHM

WHM is two-dimensional path/Y collision selected by depth, separate from the
visible WMD mesh. Records store an attribute, base Y, signed Y delta and a
packed horizontal interval/contact control. They describe floors, ceilings,
directional side boundaries and filled rectangles. The world transform,
inactive banks, turned mansion walls and alternate mountain route are
selected by the executable's collision lookup, rather than inferred from
mesh bounds.

[Collision research and validation](collision.md) documents the full byte
layout, signed rounding, control fields, X/INS behavior, table addresses,
verified special cases and limits of the static preview.

## CLM

Towns are not built from models. Slot 15 (8FFF) of a town section is a TIM
image, 8 bits a pixel with a 256 colour palette: the whole town, drawn in
advance. Slot 14 (8EFF or 8E80) is a map over it: a 16-bit width and height
in cells, then one byte per 8 × 8 pixel cell, row by row. Zero is where
nothing can walk. The non-zero values mark the walkable ground and special
spots such as doorways; values with bit 7 set appear around doorways and
obstacles, and their exact meaning is not established. Placement positions in a town are pixel positions on the
picture. In areas without a picture the same slots hold other data.

Dwarf Village also has cutaway house interiors within section 00. These
are SPR 3BFF frames 404, 405 and 406 in AREA02/D006.GAM, not the Elder's
Hut or prison sections. Frame 404 is the hollow-tree room with the stone
chimney and fireplace. Its 112 x 160 artwork uses texture page base 2 and
the 256-colour CLUT at (128, 511), word 7FC8. Tomba and NPCs are separate
sprites drawn over the artwork according to the current game event.

The US INFO.BIN overlay defines three scenery styles at 800EDAB8 and their
animation table at 800F0420. Its scenery scripts use base 2, with
the style supplying CLUT 7FC8, 780A or 7F88. The NPC scripts at 800F00C0
use base 16 from the table at 800EDB28, including frames 425 to 430.
Reading the entire bank through
one guessed page produces garbled scenery. The sprite viewer applies
these per-frame settings, and the level viewer's Town view selector opens
the three house artworks. This preview does not simulate the event's
character positions. These overlay addresses are verified for US retail;
the decoder checks the executable and overlay before using them.

The same Dwarf house bank and INFO overlay are loaded in AREA19 section 00.
That resource variant exposes the same three cutaways. AREA05 sections 00
and 02 (normal and purified Baccus Village) use SPR 3DFF frames 9 and 11 in
D005.GAM and D205.GAM: the bar room and the house with a stove. Frame 10 is
the bar's separate covering artwork, not another room. Baccus's INFO2
style table is at 800FDDC4, with animation pointers at 80102004. Initializer
800EF658 reads variant +B4 and palette state +B6: room art uses base 2 and
CLUT 7F48 at (128, 509), rather than the outside scenery's 7FC8. Using the
outside palette on the interiors produces the scrambled colours.

AREA19 section 02 (Hidden Village) uses SPR 3DFF frames 0, 1 and 2 in
D208.GAM. These are three wooden cutaway houses. Its style table is at
800FDE34 and its animation pointers at 80102930. The artwork uses base 2
and CLUT 7FC8, the palette state produced by initializer 800F03E0 with +B6
zero. These five town contexts expose thirteen room views, eight distinct
artworks. The US retail scan finds seven town-picture load contexts in
total. AREA08 sections 00 and 02 are the other two: Baccus Pier. Its SPR
3DFF bank contains fences, not house interiors. Reusing Dwarf's NPC bank
or INFO2 there is insufficient evidence for a room and does not create
room entries. The Village of Civilization's available sections have no
town-picture bank or matching cutaway sprite bank; their separate section
interiors remain available through the Section selector.

`python -m tests.validate_town` checks these pages, palettes, frames and
bank pointers against bounded execution of the actual US initializers.
The room selector and SPR viewer share the decoded settings. Character
overlays and event-dependent room composition are not simulated.

## APD and object initialisation

Placement records are sixteen bytes (routine 8005AA98): section, layer, type,
two variant bytes, a flag byte, three signed 16-bit coordinates and further flags.
Records can be relative to the previous absolute one. The layer selects a
table of initialisation routines and the type an entry in it. The level
editor runs that routine on a blank object in an emulator holding the
executable, the area overlay and the loaded banks, then reads the model
pointer, sprite bank, animation script and drawing words back out of the
object.

Object memory starts with the spawn routine's model pointer and a scale of
4096 on each axis. Initializers can replace scale and rotation; the editor
applies both before translating the model. The Ol' Pond AP box uses a scale
of 3072 and Y rotation 3072 (one turn is 4096). Its six relative placements
then form a closed 36-unit cube. Several panels include a second inward
face. Closed-shell winding checks count each coincident panel once, and
OpenGL uses the resulting outward orientation for culling. Lit GLB export
converts clockwise faces to glTF counterclockwise faces, preserving UV and
colour corner order and supplying normals.

Every independent emulated handler call restores a clean CPU context.
Stopping in a MIPS delay slot otherwise leaves a pending branch that can
redirect the next object's initializer. Object and bank memory still retain
the state needed for consecutive animation updates.

The Ol' Pond layer 5/type 04/variant 03 object is a conditional collectible
with banana artwork. Its initializer tests the byte at `8009C114` in US
retail. The editor resolves its pose with that byte set to FF and lists it
under Event previews, hidden by default, rather than claiming it is present
in the initial state. The corresponding relative address is also verified
in the US demo and February preview.

## Backdrops

### Flat town and interior views

Town TIM scenes, cutaway house artwork and fixed-picture interiors use a
2D orthographic viewport. Flat XY geometry can use it too. Sections with
full WMD level geometry keep the 3D camera. Model assets placed in an
otherwise flat room do not turn its picture into a perspective scene.
The same viewport remains attached while switching modes. Middle/right
drag pans, the wheel zooms, and F or a double-click frames the selected
object. Initial framing uses the room artwork rather than distant spawn
markers. Orbit, origin, culling and GLB controls are hidden in 2D.

Flat rendering uses a painter pass, without a Z buffer or depth scaling.
Ordinary sprite ordering follows projected depth divided by four plus the
signed object byte `+0F`, with four reserved ordering buckets in front
(US `80048B14` and `80048B4C`). The editor keeps the relative initial depth
from the object initializer. Fixed rectangles and screen sprites use bucket
804 plus their ordering offset (`8004E014`, `8004E338`); screen mode 2
reads the offset from word `+0E`. This screen-sprite rule applies to layer 7
draw mode 1, not to every sprite that follows the camera. AREA09's clock-room
furniture follows the camera but queues through `80018C40` on the ordinary
actor draw list. Its clock at APD `82FF +00B0` has bias 92 and initial depth
100, giving editor bucket 121 in front of the room picture at 804. Treating
camera anchoring as a draw mode incorrectly put the clock at 896 behind
the picture. Town TIM art is the base layer. Larger
buckets paint behind smaller ones, with stable APD ordering for ties.
This preserves the decoded initial drawing priorities; event-driven
spawns and dynamic actor sorting are still outside the initial-state preview.
Picking walks this painter order from front to back and tests texture alpha,
so an invisible texel cannot intercept a click on a visible object behind it.

Solid WMD assets keep internal depth during the flat painter pass. Each
asset gets a fresh depth buffer, so a door's rear primitives cannot cover
its textured front, while another scene object still follows the decoded
draw priority. Flat picking likewise chooses the nearest opaque face within
each asset. The orthographic scene camera is unchanged.

APD modes 2/3 retain their parent link, not just an added spawn position.
The initial-pose trace copies initialized parents to separate object records,
fixes their coordinate pointers and supplies the child's `+90` parent pointer
and `+30` relative coordinates. Attached sprites get their first update before
their pose is captured. X09 `8011ADBC` places the chandelier 76 units beneath
its chain using the parent's angle; reading the APD child coordinates alone
put it outside the room. Mirrored SPR parts use their four UV corners rather
than a forward crop, which restores the right chair and chandelier artwork.

Some model CLUTs are uploaded by area code. The clock door has two rows at
VRAM `(128, 508)` and `(128, 509)`, copied from X09 `8012A5CC` by the call
at `8011C1B4`. The preview decodes literal LoadImage setups in the loaded
overlay and applies unique rows referenced by its WMD banks. Ambiguous or
dynamic uploads are left unchanged. This previews the stored model colours
without simulating the event flags that control when the door appears.

Selection uses the actual sprite rectangle or mesh polygon edges, without
a bounding box. Geometry edges use Tomba2Edit's orange `(0.80, 0.50, 0.05)`;
asset edges use its amber `(0.75, 0.55, 0.10)`. The active triangle/quad is
yellow and sprite rectangles are yellow. Billboard outlines follow the same
camera-facing transform as their image, and animation updates their edges.

APD layer 7 holds the scenery behind a level. Its objects live in their own
pool of 6C-byte records and are run through the handler table at 8007D57C
(routine 8003438C). A handler sets up a sprite like any other object, then on
every update turns the placement into a position on the 320 x 240 screen
using the camera words at `1F800176` and `1F800186`. Each type scales the
camera by its own factor: the village's cloud bank follows an eighth of the
camera's sideways movement and none of its height, the mansion's backdrop a
quarter of both. The level editor measures the factor by running the update
with the camera moved a known amount.

A backdrop's animation step can name a second frame in the word after the
first; the mansion's strips pair a water frame with a strip of trees and sky.
Draw mode 4, which only the mansion's areas use (routine 8011E778 of area
4's overlay), draws both from the same anchor with the second raised by the
object's word `+20`, 232 on every strip, so the trees stand above the water.
The mansion handler wraps its screen X in 512
pixels, which is what makes eight 64-pixel strips an endless loop.

Editor free-look stitches adjacent strips before repeating each parallax
layer horizontally. Finite scenery also repeats for a complete turn. The
vertical band is anchored at the horizon, independent of world camera
height or forward distance; pitch shifts it in the same direction as the
3D scene and stops at 60 degrees in either direction. This is an editor
panorama policy: the game itself uses a fixed path camera. Selected strips
receive an outline in screen space; selected world objects receive a bound
in the 3D viewport.

Queued backdrop objects are drawn by routine 8004DE40 according to their
byte `+0A`, APD byte 12. Mode 1 draws the object's sprite. Mode 2 (routine
8004E244) draws a fixed picture from the table at 8007EBEC, indexed by the
variant: 18-byte records of texture page, X and Y offset, U, V, width,
height, palette position and blend flag, ended by 7FFF. Each rectangle is
added to the front of one draw list, so the last in the table is drawn first
and the first ends up on top. A rectangle with the blend flag mixes the
texels whose colour has bit 15 set with what is under them, by the mode in
its texture page word: Baccus Lake's two shafts of light are added to the
picture this way. Mode 1 draws every part of a frame with the first part's
texture page; no frame drawn that way has parts on two pages. Such an object stays
with the level: its screen position is its placement less the camera words.
The Y camera word is the world Y of the bottom of the screen, so the picture
stands 240 units above where its placement reads.

Scenery in other layers can work the same way. A handler that rewrites its
object's position as placement less camera on every update, as the Lake's
waves in layer 3 do, is giving a screen position too, and its placement uses
the same top-of-screen Y as the picture behind it. Objects drawn from the
screen lists are never mirrored.

## Models animated in place

APD layer 8 objects are models from WMD slot 2, in a pool of 45 run through
the handler table at 8007C68C (routine 8002DB4C). Several handlers animate by
editing the model itself: the mansion's water steps the V coordinates of its
polygons by 60 hex every ten frames. The level editor runs the handler with
the model in memory and decodes each version the model goes through.

Handler tables hold addresses inside the area overlays for types that only
one area uses. The overlays share their first 2DE6C bytes; code after that is
specific to the area, so such an entry is only meaningful with that area's
overlay loaded.

## Stock formats

These are Sony's own, used by most games on the console, and are opened
wherever they are found.

**TIM** is the word `0x10`, a flag word and one or two blocks. The low bits
of the flags give the depth (0: 4 bits, 1: 8 bits, 2: 15-bit colour, 3:
24-bit colour) and bit 3 says a palette block comes first. A block is its
own length, a VRAM position, a size in VRAM words and the words. A palette
block holds as many palettes as fit in it. Two headerless forms occur
inside archives and are read as TIMs: a palette block followed by a
position, a size and pixels, and a position and size followed by words.

**TMD** is `0x41`, a flag word, an object count and a 28-byte record per
object giving the start and count of its vertices, normals and primitives.
A primitive is four bytes (packet length, own length in words, flags, mode)
and a body of, in order: a word per corner with U, V and on the first two
the CLUT and texture page; colour words; 16-bit vertex and normal indices.
Mode bit 2 is textured, bit 3 a quad, bit 4 shaded per vertex. Flag bit 0
means unlit, and then colours take the place of normals. The length of
every file checked equals the end of its last list, to the byte.

**VAB** is a header (`pBAV`, sixteen-byte program records, 512 bytes of tone
records per program, a table of waveform sizes in units of eight bytes) and
a body of SPU waveforms end to end. It ships as one file or as a header
(`.VH`, also `.VA`) and a body (`.VB`). Each waveform opens with an empty
block and ends with a flagged one, which is how a body is told from the
padding that often separates it from its header.

**SEQ** is `pQES`, a version, ticks per quarter note, a tempo, a time
signature and one MIDI track with running status, tempo changes written
without their length byte. Version 0 has a 32-bit length before the events.
A standard MIDI file is played by merging its tracks into that form.

**XA** audio is not file data: it occupies Form 2 sectors, 2324 bytes each
where a file read returns 2048, and several channels are interleaved by
sector. Each sector's subheader names its file and channel and carries a
coding byte: stereo, half rate and 8-bit are each a two-bit field in which
only the value 1 selects them; the values 2 and 3 are reserved, occur on
real discs, and play as 0. A file is taken for a stream by sampling its
sectors: sound sectors and no data sectors. Sectors with no sync pattern at
all are CD audio.

**STR** movies carry `0x80010160` at the start of each video sector. The
frame header names the bitstream version. Versions 1 and 2 store each
block's DC as ten bits; version 3 codes it as MPEG-1 does, a size from one
of two tables and that many bits of difference from the previous block of
the same component, in steps of four.

## Archives

`formats/archive/containers.py` reads six table layouts:

| Layout | Table | Met in |
| --- | --- | --- |
| pairs | (offset, length); the first offset is the table's length | the sampler's `.LPK` and `.APK`, `ANGEL.BIN` |
| offsets | ascending offsets; the first is the table's length | DSC `.PAK` |
| counted | a count, the file's length, then (offset, length) | PUYO3 `.DAT` |
| sectors | (sector, length), no count | MEL2 `.FAR` |
| LVL | `Indx`, then 24-byte records: name, sector, sectors, length | Abe's Oddysee |
| RAQ | 32-byte records: name, flags, sector, sectors, behind a copyright line | MEL2 `.RAQ` |

The file is also searched once for TIM, VAB, SEQ and TMD headers. What the
search finds inside a table entry takes the entry's name; an entry holding
several is listed as each; anything outside every entry is listed by offset.
A table that names nothing recognisable is taken to be a coincidence and the
search stands alone.

Two packings are undone. The sampler's `.LPK` entries are LZSS exactly as
in Okumura's `lzss.c`: flag bytes read low bit first, a set bit for a
literal, otherwise twelve bits of position in a 4096-byte ring written from
`0xFEE` and four bits of length less three. MEL2's entries start `LZSD`,
then a 32-bit count of the bytes from that count to the end, then blocks of
Gage's byte pair encoding: a run-length coded table giving some byte values
a pair to stand for, a 16-bit big-endian length, and data in which pairs
expand recursively. The routine is at `800795F4` in `MEL2/PSX.EXE`.

Memory card saves, found in the sampler's `TIM.LPK`, start `SC`, a frame
count and a block count, then a 64-byte Shift-JIS title, a palette at
`0x60` and 16 x 16 four-bit icon frames from `0x80`.

## Builds

`game/builds.py` describes each executable the level editor can run objects
from, keyed by its SHA-1:

| Executable | Build | Overlay base | Area word |
| --- | --- | --- | --- |
| `SCUS_942.36` | US retail | `800E7388` | `8009BCC8` |
| `SCUS_942.55` | US demo | `800DDCA0` | `80092640` |
| `SLPS_011.44` | Preview, 3 February 1998 | `800EDAA8` | `800A2440` |
| `SLPM_801.65` | Japanese demo | `800E7698` | `8009A810` |
| `TOMBA.EXE` | Pure Pure 09 sampler | `800ED548` | `800A2248` |
| `MAIN0.EXE` | European release, language 0 | `800E8028` | `8009C960` |

The European release starts from a small boot executable, `SCES_013.31`,
and runs one of nine programs, `EXE/MAIN0.EXE` to `MAIN8.EXE`, one for each
language. They are one engine built nine times. The text of a language
makes the program's data a little longer or shorter, and everything after
the data moves by that much: the variables, and the area overlays, which
load at `800E8028` plus 0, 20, 40, 38, 40, 28, 30, 10 and 30 (hexadecimal)
for languages 0 to 8. The program of language 5 also has 24 bytes less in
the middle of its code, which moves its tables down by as much. Each
program has its own file link table, starting at its own system load table
`SYS/LDnSYS.BIN`, and its own area overlays `AREAaa/Xnaa.BIN`.

Its screen is 256 lines high. The routine that draws a fixed picture puts
it 24 rows lower than the other builds do and covers the top and bottom 16
rows of the screen with black bars.

A sprite bank is read through the table of loaded banks at 1F8002C8, four
bytes a slot. The bank in slot 9 is read by `SYSTEM/DSPSUB.BIN` alone, the
code of the menu, which the system load table brings in with the menu's
pictures and palettes: its sprites are the menu's panels, buttons and
lettering, and an area's own textures never hold their art.

Objects that other objects create while the game runs (splashes, bursts,
flames) are in no placement list, but each is an entry of the same tables
of object routines. Running such a routine on a made-up object, for each
type and variant it might be given, shows which bank, frames, texture page
and palette it uses. Most of the second half of the item bank belongs to
three such classes of layer 3 (0F, 4E and 5C), drawn from page 19, the page
every area loads its own effects on.

An entry also names the item tables. An item (APD layer 5) is set up from a
twenty-byte descriptor, found through a table of descriptor numbers by item
type: draw mode, texture page base, SPR slot, the flags of object byte +0D,
how the palette is chosen, how the animation is, the palette's position in
VRAM, a collision box and a pointer to the animations. The palette is the
one named, the row below it by the item's variant, one of a table by the
variant, or the row below by two event flags. The sprite viewer reads these
descriptors for the frames of items, which carry a stand-in palette in the
sprite bank itself.

An entry holds the six tables of object routines (APD layers 2 to 5, 7 and
8), the routines the emulator answers itself (the animation setter, the six
visibility tests, `GetClut`, the seven draw-list appenders, the sound call
and two flag tests), and the per-area tables for placement slots, entrances,
collision origins, plane limits, fixed pictures and sprite pages.
The sampler stores two of these differently: its fixed picture rectangles
are sixteen bytes, without the blend flag, and its object records are
twenty, with four size words ahead of the page, the animation, the SPR slot
and the script pointer.

The engine is the same in all of them, which is how the addresses were found.
The three object dispatchers (8001DFD4, 8003438C and 8002DB4C in retail)
are instruction for instruction identical once jump targets and the
operands of address loads are masked out, so each build's copy is located by
that pattern and its tables read from the same instructions. Other routines
were paired the same way, or through the calls made at matching positions of
routines already paired. Tables with no matching code were identified by
their content: the placement slot table is the only run of pointers to runs
of scratchpad addresses from `1F800358`.

An overlay's load address follows from the overlay alone. Its `jal` targets
beyond the executable minus the offsets of its own stack prologues agree on
one value, which is the base.

Differences that are not just addresses: the 1997 builds have no area
variants (retail maps areas 7, 12 and 19 onto 1, 4 and 2), and they store
plane limits in place rather than behind per-area pointers, one byte a
section and sixteen an area in the Japanese demo, one 16-bit word a section
and twelve an area in the sampler.

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
- [afsenovilla/Tombi-Decomp](https://github.com/afsenovilla/Tombi-Decomp), a matching decompilation
  of the European release: the sprite, backdrop and item routines described here were read
  against its source.
  Some reference descriptions conflict; real-disc validation takes precedence.

No game data is included with the application.
