# Tomba 1 collision and level assembly

This describes the US retail build, `SCUS_942.36`, SHA1
`81cbc79f0230aeb4252e058039f47ac95a777f5a`. It was established by inspecting
the executable and the area X overlays and executing the collision routines
in isolated MIPS memory. The decompilation's collision file still delegates
these functions to assembly; its file names alone do not establish the format.
No game bytes or copied assembly are included in the application.

## The level is not its collision mesh

WMD stores the visible polygons. The game does not collide with those
triangles. WHM stores independent two-dimensional path/Y boundaries, divided
into depth slices. A depth coordinate chooses the slice, then the collision
test operates in two dimensions. This explains why fitting a triangle mesh
to WHM, or drawing every record as a vertical line, produces incorrect art.

The level preview applies LDAR's base resources followed by the section's
resources, replacing slots and VRAM rectangles in load order. A resource
which remains loaded need not be active in the current section. In particular,
the village's shared collision bank survives into the hut sections but must
not be displayed as their active collision.

## WHM byte layout

All numbers are little endian. Header:

| Offset | Size | Interpretation |
| --- | --- | --- |
| 0 | 1 | Layout tag `11` |
| 1 | 1 | Number of planes |
| 2 | 2 | Header word, not used as the section's world origin |
| 4 | 2 | Width of the path, in world units |
| 6 | 2 | Header height word, not used as a span Y offset |
| 8 | 2 per plane | Absolute byte offsets of plane tables |

Each plane has `width / 8` unsigned 16-bit column offsets, relative to that
plane's table. A column offset points to a 16-bit record count, followed by
that many eight-byte records. Columns may share a record list. Plane offsets
must be read explicitly rather than assuming the data immediately follows
the header.

| Record offset | Type | Meaning |
| --- | --- | --- |
| 0 | u16 | Attribute and control flags |
| 2 | s16 | Base Y |
| 4 | s16 | Signed Y delta |
| 6 low nibble | u4 | Horizontal start within the column |
| 6 next nibble | u4 | Horizontal width |
| 7 | u8 | Additional contact control |

Y is negative upwards. The signed delta is never an absolute end height.
For example, base `-50`, delta `-300` ends at `-350`, not `-300`.

## Boundary types

| Attribute mask | Confirmed role | Evidence |
| --- | --- | --- |
| `0001` | Floor / standing boundary | `8004339C`, `80045310` |
| `0002` | Ceiling boundary | `80043B3C`, `80045570` |
| `0004` | Side boundary that can push the object left | `80043740` |
| `0008` | Side boundary that can push the object right | `80043740` |
| `0010` | Filled rectangle rather than a boundary line | `800443CC` |

These flags combine. A solid rectangle's directional bits determine which
responses are used. Floor snapping skips filled records; the floor line is
usually a separate record immediately beside the solid record.

A non-filled boundary runs from `(column * 8 + start, base Y)` to
`(column * 8 + start + width, base Y + delta)`. Side boundaries with width
zero are vertical. A solid record fills that horizontal interval between
base Y and base Y + delta. The viewer displays its exterior outline, merging
adjoining solid rectangles so their internal column seams are not drawn.
Individual source rectangles remain selectable and appear in yellow.

No smoothing changes the stored collision. Lines are antialiased for display,
but small differences in endpoints remain where the game stores them.

## Height tests and rounding

The standing evaluator `8004339C` takes `x & 7` and computes, for nonzero
width and delta:

```
Y = signed16(baseY + trunc(deltaY * ((x & 7) - start) / width))
```

Signed MIPS division truncates towards zero, unlike Python floor division.
Thus a delta of `-5`, start `2`, width `4`, at local X `3`, yields `-101`
from a base of `-100`, not `-102`. The viewer's line represents the underlying
boundary; the game samples it at integer positions.

For zero delta the standing height is the base. For zero width, positive
delta uses the base and negative delta uses base + delta. That is a flat
standing test, not an invalid division. The standing routine extrapolates
across the column and has additional approach/tolerance handling. Other
ceiling and side routines enforce the packed horizontal interval, and some
use the remainder of `(world path coordinate - start) / width`. Consequently
the different queries are not interchangeable with one generic point-in-mesh
test. The model viewer is a boundary inspector, not a replacement physics
engine.

The high contact byte is also consumed: values 1 and 2 alter floor approach
tolerance using the local horizontal position. It is not another coordinate.

## World placement and section routing

Lookup routine `80042654` receives path and depth coordinates. Objects obtain
them through pointers at object offsets `+40` and `+44`; normal allocation
points these at X and Z. The first entrance is read through the area table at
`8007BF78`. Routine `800243E8` copies its orientation flag to `1F8001C8`.
When bit 0 is set, allocation swaps the pointers: the path is world Z and
depth is world X, counted in the opposite direction.

Ordinary section origins come from pairs of signed shorts reached through
`8007E9F8[area]`, indexed by the full section number. There is no eight-section
limit on this origin table. The path column is the signed, truncated division
of path minus origin by 8, clamped at zero. The plane is the signed, truncated
division of depth minus origin by 90; turned sections reverse the subtraction.
A byte reached through `8007EAF4[area]` caps the plane, and negative planes
clamp to zero. A cap of zero means every depth uses plane zero. In such a
turned room the preview draws the single slice at the entrance's X, since
the origin does not uniquely locate a physical plane.

Special cases established from the lookup:

- Village sections 0, 1 and 2 use slot 1 through depth 270, and slot 0 beyond
  that, subtracting 270 before indexing slot 0. Slot 1 includes the exact
  depth-270 boundary; slot 0's first slice is selected starting at 271.
- The hut, section 3, uses its local slot 0. Behind the hut and the pond also
  use their local plane-zero bank. The loaded shared slot 1 is inactive there.
- Mansion and purified mansion sections 0..3 use origins at `8007E9E8`.
  The entrance orientation also selects slot 0 or slot 1. These are two
  different sets of collision around the same visible building.
- Stormy Mountain's second part, sections 1 and 5 of area 3, can select slot 1
  when the signed route state at `[800A53DC] + 2` is negative. That route uses
  the origin pair at `8007E9E4` and adds 90 to depth before indexing. The
  inspector offers Default route and Alternate mountain route separately.

The world view converts `(X, Y, Z)` to `(X, -Y, -Z)`, as the WMD viewer does.
The overlay uses the entrance orientation and the verified origin tables;
its planes are inspection slices, not solid extruded 3D surfaces.

## Gameplay attributes and X / INS

`INS` is the LDAR type for code, including the area's X overlay. It contains
real MIPS code, dispatch tables and animation data, not a list of placement
coordinates. The area overlay is loaded at `800E7388`. Its handlers interpret
APD layer/type/variant and choose sprite banks, animation scripts, texture
page bases, palettes, model pointers and model modifications. The level
preview executes these bounded initializers and decodes the resulting visual
links. Static WHM placement is selected by the main executable as above.

Collision results are written to scratchpad `1F800282` (attribute),
`1F80027E` (delta), `1F800280` (base Y) and `1F800284` (attribute bits 9..11).
Routine `80042FE4` translates these for Tomba's handler:

- Bits 5..8 are a four-bit surface code. With neither `1000` nor `2000` set,
  codes 0, 1, 2, 3 yield player byte `+BE` values 0, 2, `10`, `20`, plus
  attribute bit 15 copied into bit 0. Other values do not receive a new
  physical name merely because they are present in a bank.
- Codes 13, 14 and 15 are separately converted into player `+A1` values
  1, 2 and 3 by `80042978` and the related collision checks.
- With `2000` set, the surface code's upper two bits select a player `+A0`
  mode. With `1000` set, its lower two bits choose `+A0` masks `10`..`40`.
- `4000` is checked by the rotation/contact routines `80044B0C` and
  `80045780`. The former obtains a contact angle through `80023168` rather
  than treating it as a plain flat wall.
- X handlers consume these player fields. For example, `800EF27C` dispatches
  on `+BE`, and `8010667C` uses its bit 0 to set facing and clamp motion.
  The particle helper `800EA35C` is additionally gated by area, section and
  game state; a surface code is not a universal butterfly/leaf switch.

Standing and directional geometry are confirmed. Assigning every remaining
field a name such as hurt, leaves, butterflies or jump-up requires following
the relevant player state and event branches, or comparing live gameplay.
The inspector deliberately displays these numeric fields and supports the
existing WHM attribute labels rather than presenting guessed effects as facts.
Dynamic object hitboxes, event changes, full player movement and script-driven
collision rewrites are not simulated by the static level overlay.

FOUR is independent: it holds per-corner WMD morph deltas. Routine `80027A30`
subtracts `(delta * weight) >> 12`, wrapping signed 16-bit coordinates.
AREA00 handler `8011F7E4` links FOUR slots 2, 1 and 0 to WMD slot 1 objects
3, 2 and 1 respectively. Those links are verified for the deformation viewer;
they do not turn FOUR into a placement or collision file.

## Reproducible validation

```
python -m unittest discover -s tests -v
python -m tests.validate_collision "rom/Tomba! (USA).cue"
python tests/gui_collision_smoke.py "rom/Tomba! (USA).cue"
```

The collision oracle parses all 123 WHM banks, 241 planes and 95,268 records,
then compares 9,600 standing heights, 4,804 solid boundary queries, 195 section
lookups and four alternate-route lookups with the original MIPS routines.
The GUI test checks real OpenGL rendering, filters, line picking, F framing,
double-click framing, turned mansion collision, the alternate mountain route
and the standalone WHM view. Unit fixtures contain no game data.

Numeric parsing is independent of region. US absolute code and table addresses
are used only after the executable hash is verified. World collision placement
for other builds must be established separately.
