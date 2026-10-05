# TombaEdit

A disc browser and asset viewer for **Tomba! / Tombi!** on the PlayStation,
written in Python with PyQt6. It reads a disc image directly, follows the
game's own load tables to find every resource, and shows levels, models,
sprites, text, collision, palettes, music and movies without extracting
anything first.

TombaEdit is read-only: it exports assets but does not rebuild discs.

## Running

Python 3.10 or newer.

```powershell
python -m pip install -r requirements.txt
python main.py
python main.py "rom\Tomba! (USA).cue"
```

`python -m PyInstaller main.spec` builds a standalone Windows executable.

## The disc tree

**File → Open BIN / CUE / ISO** loads an image; dropping one on the window does
the same. CloneCD images open from either the `.img` or the `.ccd` beside it. The tree on the left is the disc's ISO9660 directory. Each `AREAnn`
folder starts with a *Sections* node holding the area's load groups: the base
group shared by the whole area, then one group per section in the order the
game loads them. Files that a load group reads from can be expanded to the
resources inside them.

The filter box matches names, resource types, section names and offsets.
`F2` names the selected file or resource. Names are stored against the
content of the resource, so they follow it between regional releases, and can
be exported and imported as JSON from the *Labels* menu.

**Export decoded file** writes the decompressed bytes of the selection.
**Export original disc file** writes the file that contains it, as it is on
the disc.

Selecting a tree item, model, polygon, scene object, sprite, picture,
palette or collision span prints a line to the console with its type, offsets
and whatever identifies it inside its file, which is convenient when working
alongside a hex editor or a debugger.

## Viewers

| Resource | Type codes | Viewer |
| --- | --- | --- |
| Load group | | Level editor: section geometry with placed models and sprites |
| WMD | 50–55 | Models, with polygon and UV inspection and glTF export |
| FOUR | 40–45 | Vertex deformations applied to their source model |
| SPR | 30–3F | Sprite frames and their parts |
| WPP | 60–63 | Packed pictures for Tomba's own frames, and the frames assembled |
| GRPX | 10, 11 | VRAM as the section sees it |
| WHM | 70, 71 | Collision spans by depth plane |
| CLM | 8E, 8F | Town pictures and their cell maps |
| APD | 80–8B | Placement records |
| WFM | D0, D1 | Dialogue rendered with the game font, and the glyph atlas |
| SEQ, WVD | B0–B3 | Sequenced music and sample banks, with playback |
| STR | | Movies, with frame, audio and video export |
| CLUT files | | Palette cells with their PlayStation and RGB values |
| INS, `X` files | F0 | Code overlays with functions, tables and animation scripts marked |

Files in the console's stock formats open whatever game they belong to, and
are recognised by their contents, not their names:

| File | Viewer |
| --- | --- |
| TIM | Picture, at any depth, through any palette the file holds |
| TMD | Model, textured from the TIM files in its folder |
| VAB, or a `.VH`/`.VA` header with its `.VB` | Sample bank |
| SEQ, MIDI | Music, played on any bank on the disc |
| XA streams | Every channel, cut into clips |
| CD audio stored as a file | The track |
| STR movies under any name | Movie; MDEC bitstream versions 1 to 3 |
| Archives | Contents: each entry in the viewer for its kind |
| Text files | Text, as ASCII or Shift-JIS |

### 3D views

Models, deformations and levels share one camera. A view opens looking along
the game's depth axis, so a level appears as it does in play; levels start
tilted slightly downwards.

| Input | Action |
| --- | --- |
| Middle drag | Orbit |
| Shift + middle drag | Pan |
| Right drag | Look around; `WASD` moves, `Q`/`E` go down and up, Shift is faster |
| Wheel | Zoom, or change the fly speed while looking around |
| `F`, or double-click a row | Frame the selected model |
| Left click | Select a polygon; its texture page opens with the UVs outlined and in view |

With **Orbit Selection** on, a middle drag circles the selected model rather
than the middle of the view. In the model viewer the selection is
highlighted by dimming the other models; **Show all** clears it. The level
editor does not dim. **Texture Mode** switches between textures and
bare vertex colours, **Spread Parts** lays a bank of models out on a grid,
and the model list hides or isolates individual models without moving the
camera. glTF export writes the visible models with their textures, either
unlit with the game's colours or lit for use elsewhere. Exported files are
offered under the area, section and resource that is open, with the model's
name added when one is exported alone, and the models keep their names inside
the file. Sprite and picture exports are named the same way.

### Level editor

Selecting a section's load group builds its scene: the section geometry, the
models and sprites that its APD records place, and orange markers where an
object's graphics are not known. Positions come from the APD records. What an
object looks like is found by running that object's own initialisation code
from the game executable in an isolated emulator, which yields its model or
its sprite bank, animation script, texture page and palette. This is done for
the US release; other releases show geometry, directly linked models and
markers.

- **Animate** plays the animation scripts of placed sprites at the game's
  30 steps a second. Models that the game animates by rewriting
  their texture coordinates, such as water surfaces, play the same way.
  **Save GIF** writes one cycle of the selected object: a sprite's frames, or
  for such a model its texture, either cropped to the moving UVs or as the
  whole page with them outlined.
- **Background** draws the section's backdrop sprites, the sky, clouds and
  distant scenery, behind the level. The game positions them on the screen
  from the camera, each following a fraction of its movement. Here they
  behave as distant scenery: sliding the view sideways makes each drift by
  its own fraction, turning the camera carries the backdrop across, looking
  up or down shows more of it, and moving towards the level leaves it still.
  Looping scenery repeats. Interiors and
  other sections with a fixed picture behind them show it in place, with
  their foreground pieces over it. Behind all of it the view is cleared to
  the colour at the top edge of the scenery, standing in for the game's own
  sky colour, which is not stored with the section.
- **Collision** overlays the section's WHM data: green walkable surfaces,
  magenta surfaces with special attributes, and orange outlines around solid
  ranges. Each plane is drawn at the depth where the objects that use it
  stand. Sections whose path runs into the screen, such as two of the
  mansion's four walls, have their collision turned a quarter to match. Origin
  and orientation come from the section's tables in the executable.
- **Town Map** applies to towns such as Dwarf Village, which are a single
  pre-rendered picture rather than geometry. The picture is the backdrop of
  the scene and placements are positions on it. The toggle tints it by the
  town's map of 8 × 8 pixel cells, one colour per cell value, with the values
  that have bit 7 set in blue. **Collision** outlines the same map: green
  around the walkable ground, magenta between cells of different values.
  Town characters are created by the town's own code rather than by placement
  records, so only the few placed objects appear.
- *Show* limits the scene to geometry, models, sprites or unresolved objects,
  and *Open asset* jumps to any resource the group loads.

The scene is the state right after loading. Conditions, scripted spawns and
movement are not simulated.

### Sprites

A sprite frame is a list of parts, each a rectangle of a texture page with an
offset from the object's origin. Parts store their texture page relative to a
base that the drawing object supplies, so the same bank can be used with
different pages. With *Texture page base* on Auto the viewer uses the base of
a placed object that shows the frame, the game's object table for banks that
no object in the section uses, and otherwise the base that leaves the fewest
empty pixels. The value can be set by hand.

**Sprite bounds** draws a box around every sprite and **Part bounds**
outlines the parts it is assembled from, one colour per part. Both apply to
single sprites and to sheets, and saved pictures include them while ticked.

Some palettes are only written while the game runs. Parts that name an empty
palette row are drawn in grey so the art can still be seen; **Grey without
palette** turns that off. A bank whose texture page is empty as well has
nothing to show in that section.

A bank can hold several characters whose art sits on different pages, as the
town banks do. Auto then has one base for the whole bank unless placed
objects say otherwise, and the frames of the other characters need the base
set by hand. The viewer opens on a
sheet of the whole bank; selecting a row shows that frame and its parts.

The section's VRAM runs along the bottom of the tab, with every control of
the VRAM view. Selecting a sprite or a piece puts the crosshair on the
palette it is drawn through and outlines, in the piece's colour, the
rectangle of VRAM its pixels come from. Putting the crosshair on another
palette redraws through it whatever *Crosshair recolours* names: the
selected pieces, the sprite, or the whole bank. *Reset CLUTs* undoes it.
Saved pictures show what is on screen.

Tomba's own frames are not in VRAM. The game keeps them packed in a WPP bank
and uploads one picture at a time; the phoenix is stored the same way.
Opening a WPP bank lists its pictures, with the same saving choices as a
sprite bank: one picture, a sheet with its layout, the selected rows or all
of them. *Assembled frames* draws the pictures through the matching SPR bank,
and the sprite viewer does the same for those SPR banks. The palette list
of the picture viewer offers the palettes the matching SPR bank names where
VRAM holds them, and for Tomba the outfit rows of the selected section's
palette block.

### VRAM

The VRAM view shows the 1024 × 512 words a section has loaded, on top of
the item and effect graphics the game loads once at boot. It is a tab of
its own for models and load groups and the lower pane of the sprite tab.

Two things are chosen separately. *Pixels* is how the words are cut up:
4-bit and 8-bit for indexed textures, 16-bit for palettes and direct-colour
pictures, 24-bit for decoded movie frames. *Colours* applies to the two
indexed readings: through the palette at the crosshair, as grey, or in false
colour that sets neighbouring indices apart. Changing the reading keeps the
same words in the middle of the view.

The crosshair marks a palette row, starting on one the open resource draws
with. Moving it never scrolls or zooms the view and never changes the
reading; it can be hidden with its checkbox.

| Input | Action |
| --- | --- |
| Ctrl + wheel | Zoom about the pointer |
| Wheel, Shift + wheel | Scroll down or sideways |
| Left or middle drag | Pan |
| Ctrl + left click or drag, or the right button | Put the crosshair on the palette row under the pointer |
| Left drag on the crosshair | Move it |
| Arrow keys | Next palette or row; with Shift a texture page or sixteen rows |
The CLUT box takes a CLUT word and lists the palettes used by the open model
or sprite bank. A red marker points at a newly chosen palette for a moment.
**Page grid** outlines the texture pages.

### Hex view

Every resource has a hex tab. *Bytes per row* re-flows the bytes; drag the
number sideways with the left button held, or type a value. A sprite bank at
16 bytes a row lines its parts up in columns, and a code overlay at 4 or 8
shows its words.

Where the layout of a resource is known, its byte ranges are coloured by what
they hold: counts, offsets, positions, palettes, sizes and so on. Selecting a
byte shows the field it belongs to with an explanation and its value as 16
and 32-bit numbers, and the list on the right jumps to any range.

Code overlays, the `X` files, are classified word by word. Functions are
marked from their stack prologue to their return, with instruction and call
counts. The entry table at the start, pointer tables, animation scripts
reached through those tables, text and zero fill are named. Addresses are
shown for the base that area overlays are linked at.

### Sound

Banks, sequences and streams share one layout. The middle pane lists what
the selection holds: the waveforms of a bank with a thumbnail of each, the
clips of an XA file, or the programs a sequence calls for. Where a file has
several banks, or a sequence could be played on several, they are listed on
the left. The right pane shows the properties of the selected row, and for a
sequence its events.

The player along the bottom shows what is loaded and its waveform; clicking
the waveform seeks. A waveform has no pitch of its own, so banks have a
preview rate. *Play on select* can be turned off to browse a bank silently.
`Space` plays and pauses.

A sequence is listed with every bank on the disc that has instruments for
it, ranked by how many of its notes each can sound, then by sharing its
folder. Selecting another bank and pressing play renders it again. MIDI
files are played the same way. Sound exports as WAV, sequences also as MIDI.

A file made of streaming sectors is read from the image directly: the
sound in an XA sector lies in the part an ordinary file read leaves out, so
this needs an image with whole 2352-byte sectors. Channels are cut into
clips where they skip a turn or mark the end of a record.

### Archives

A file that packs other files gets a *Contents* tab: a list of its entries
with their type, position and a line about each, beside the viewer for the
selected one. The list can be narrowed to one type, and entries exported
singly or all together as they would be on their own (a bank as a `.vab`,
a packed picture unpacked).

Six table layouts are read, and a file that follows none is searched for
TIM, VAB, SEQ and TMD headers, which finds resources in archives with no
index at all and inside executables. A bank stored as separate header and
waveform entries is put back together. Entries packed with LZSS or with
byte pairs are unpacked. Models are textured from the archive's own
pictures.

### Collision

A WHM bank is divided into depth planes 90 units apart and columns 8 units
wide. Each column lists floor, ceiling and side boundaries, and filled
regions. Their base height, signed delta and packed horizontal interval
are decoded from the game's evaluator. The WHM viewer draws one plane or all of them from
the side, filters by attribute, and lets attribute values be named. The same
data is what the level editor overlays in 3D. Turn on **Collision** to use
its side panel: filter by bank, plane or attribute, click a line or record,
and press **F** or double-click to frame it. The mountain's alternate route
can be selected separately. See [collision research](docs/collision.md) for
verified details and the remaining gameplay fields.

## Supported releases

Disc browsing and the file viewers work for any release. Load groups need
the executable's file link table, which is located from the disc itself. The
level editor additionally needs to know where an executable keeps its object
routines and tables; `game/builds.py` lists them for these builds:

| Executable | Build | Areas on the disc |
| --- | --- | --- |
| `SCUS_942.36` | US retail | all |
| `SCUS_942.55` | US demo | 00 to 02 |
| `SLPS_011.44` | Preview dated 3 February 1998 | all |
| `SLPM_801.65` | Japanese demo, 1997 | 00 |
| `TOMBA/TOMBA.EXE` | Pure Pure 09 sampler (PCPX-96093), 1997 | 01 and 02 |

On these, placed objects are resolved to their models and sprites, placement
banks are filtered by section, and collision is put at its world position. An
executable that is not listed still opens: its levels show their geometry,
with every placed object as a marker.

The two builds from 1997 store several resources differently: text is WFM1,
textured model primitives are laid out as GPU packets, picture banks can be a
single TIM, sound banks list their headers first, and a town's picture and
cell map sit in placement slots. Each is read in its own form;
[the format notes](docs/formats.md) describe the differences.

The preview and the two 1997 builds have no `SYS/LDAR*.BIN` files; their load
groups are read out of the executable.

The cutaway house interiors of the towns come from tables in the town
overlays, which are found by their content. The sampler's Dwarf Village has
no interiors in its bank, only the scenery drawn over the town picture, and
the preview's load table for area 19 stops before Hidden Village.

Placed objects that stay markers are the same ones on every build: object
types with nothing to show in their first state, such as triggers and
effects waiting on an event.

### The Pure Pure 09 sampler

The disc carries demos of seven other games beside Tomba!, and its own
menu. Everything in a stock format opens: the menu's pictures and models
(`TIM.LPK`, `LPK.LPK`, LZSS-packed), its music (`PURE1.SEQ` on
`MUU_MUU.VH`), the memory card icons, every movie and XA stream, the
Nagano models and MIDI file, and the pictures, banks and sequences inside
the archives of Abe's Oddysee, Angel, DSC, MEL2 and PUYO3. MEL2's archives
are packed with byte pair encoding, which is unpacked.

What stays as bytes is each game's own: executables and code overlays,
Abe's animations and backgrounds, Nagano's motion data, PUYO3's graphics,
MEL2's scripts, and the tables at the head of DSC's archives.

Dialogue is decoded with a glyph table for the US font; other releases show
the glyph images and unmapped glyph numbers.

## Known gaps

- Semi-transparency, and textures the game uploads while running other than
  Tomba's frames. Objects that depend on them keep their markers.
- Object rotation and scaling in the level view. Sprites are drawn one texel
  to one world unit.
- The meaning of most collision attribute bits, of town cell values, and of
  the two unused words in an animation step.
- Event titles in the 24-pixel font are stored without spaces; no spacing is
  added to them.
- Movie video export needs `ffmpeg` on `PATH`; frames, audio and raw streams
  do not.

## Tests

```powershell
python -m unittest discover -s tests -v
python -m tests.validate_disc "rom\Tomba! (USA).cue"
python -m tests.validate_collision "rom\Tomba! (USA).cue"
python tests/gui_smoke.py "rom\Tomba! (USA).cue"
```

The unit tests build their inputs in memory and contain no game data.
`validate_disc` decodes every resource on a real disc, and `gui_smoke` drives
the window with a real OpenGL context.

[Format notes](docs/formats.md) describe each format and where the knowledge
of it comes from.
