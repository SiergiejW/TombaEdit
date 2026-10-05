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
the same. The tree on the left is the disc's ISO9660 directory. Each `AREAnn`
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
| CLM | 8E, 8F | Collision maps as indexed images |
| APD | 80–8B | Placement records |
| WFM | D0, D1 | Dialogue rendered with the game font, and the glyph atlas |
| SEQ, WVD | B0–B3 | Sequenced music and sample banks, with playback |
| STR | | Movies, with frame, audio and video export |
| CLUT files | | Palette cells with their PlayStation and RGB values |
| INS and others | F0 | Records and hex |

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
| Left click | Select a polygon and show its record, page, CLUT and UVs |

With **Orbit Selection** on, a middle drag circles the selected model rather
than the middle of the view. **Texture Mode** switches between textures and
bare vertex colours, **Spread Parts** lays a bank of models out on a grid,
and the model list hides or isolates individual models without moving the
camera. glTF export writes the visible models with their textures, either
unlit with the game's colours or lit for use elsewhere.

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
  30 steps a second.
- **Collision** overlays the section's WHM data: green walkable surfaces,
  magenta surfaces with special attributes, and orange outlines around solid
  ranges, each drawn at the depth of its collision plane.
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

Tomba's own frames are not in VRAM. The game keeps them packed in a WPP bank
and uploads one picture at a time. Opening a WPP bank lists its pictures;
*Assembled frames* draws them through the matching SPR bank, and the sprite
viewer does the same for Tomba's SPR bank. The palette list holds the outfit
palettes of the selected section.

### VRAM

The VRAM tab shows the 1024 × 512 words a section has loaded, read as 4-bit
indices in grey or false colour, through a 16 or 256 colour palette, or as
15-bit pixels. The starting palette is one the open resource draws with, or
the first usable row of the section's palette block.

Right-click a palette row to read VRAM through it; dragging with the right
button follows the pointer. The CLUT box takes a CLUT word and lists the
palettes used by the open model or sprite bank. A red marker points at a
newly chosen palette for a moment. With **Crosshair** ticked the palette row
stays marked and the arrow keys move it by one palette or one row, or with
Shift by a texture page or sixteen rows. **Page grid** outlines the texture
pages. Wheel zooms, left or middle drag pans.

### Collision

A WHM bank is divided into depth planes 90 units apart and columns 8 units
wide. Each column lists spans: walkable surfaces with a height and a slope,
and solid vertical ranges. The WHM viewer draws one plane or all of them from
the side, filters by attribute, and lets attribute values be named. The same
data is what the level editor overlays in 3D.

## Supported releases

Disc browsing works for any release. Load groups need the executable's file
link table, which is located from the disc and has been checked on the US
retail disc (`SCUS_942.36`). Releases that embed their load tables elsewhere
show the directory tree and file viewers only. Object initialisation, sprite
texture pages and collision origins use addresses from the US executable and
are skipped for other builds.

Dialogue is decoded with a glyph table for the US font; other releases show
the glyph images and unmapped glyph numbers.

## Known gaps

- Semi-transparency, and textures the game uploads while running other than
  Tomba's frames. Objects that depend on them keep their markers.
- Object rotation and scaling in the level view. Sprites are drawn one texel
  to one world unit.
- The meaning of most collision attribute bits and of the two unused words in
  an animation step.
- Movie video export needs `ffmpeg` on `PATH`; frames, audio and raw streams
  do not.

## Tests

```powershell
python -m unittest discover -s tests -v
python -m tests.validate_disc "rom\Tomba! (USA).cue"
python tests/gui_smoke.py "rom\Tomba! (USA).cue"
```

The unit tests build their inputs in memory and contain no game data.
`validate_disc` decodes every resource on a real disc, and `gui_smoke` drives
the window with a real OpenGL context.

[Format notes](docs/formats.md) describe each format and where the knowledge
of it comes from.
