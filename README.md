# TombaEdit

A classic desktop browser for **Tomba! / Tombi! (PlayStation)**, built with PyQt6.
The default theme is Classic Dark; Settings → Theme also offers Classic Bright.

## Run

Python 3.10 or newer:

```powershell
python -m pip install -r requirements.txt
python main.py
# Or open a disc immediately:
python main.py "rom\Tomba! (USA).cue"
```

The supplied machine already has the required packages. No dependencies were
installed or changed during development. The application does not depend on the
adjacent Tomba or Tomba310 projects, nor on the old exported model dumps.

## Browse

1. **File → Open BIN / CUE / ISO**, or drop an image onto the window.
2. **Disc folders** shows the real ISO9660 directory. Expand a file to see its
   LDAR-defined resources; select the file for its metadata, decompressed GAM
   payload, embedded WFM resources, and hex view.
3. **Areas / sections** groups assets by LDAR, base load, and named section.
   Selecting a load group shows the source files, types, ranges, and VRAM.
4. Select a resource to open its viewer. Double-click a Resources table row to
   jump to that resource in the area tree. The filter matches names, types,
   sections, and displayed offsets.
5. **Export selected payload** exports decompressed bytes or the selected asset
   slice. **Export original disc file** exports its containing ISO file, using
   2048-byte logical data sectors. Image views also offer PNG export.

Supported previews:

| Resource | Current behavior |
| --- | --- |
| GAM | Bounded LZ decoding, LDAR asset ranges, embedded WFM detection, hex |
| WFM3 / D0FF / D1FF | Dialogue list, original glyph rendering, control-word listing, font atlas |
| SPR | Compound frames using section textures and CLUTs; frame and page-base controls |
| WMD | Direct mesh decoding, textured 3D preview, vertex colours, wireframe, object selector |
| GRPX | Reconstructed VRAM, 4/8/16-bit pages and selectable CLUT |
| WPP, WHM, APD, CLM, FOUR, SEQ, INS, unknown | Typed resources, source ranges, metadata, hex, export |

Geometry controls: left drag to orbit, right/middle drag to pan, wheel to zoom,
**Fit** to frame the selected objects. Level chunks open together; prop libraries
open on their first object. A VRAM selector allows base resources to use a
section's palette and texture uploads.

## Scope of version 0.1

- Browsing/export only; no editing, recompression, or disc rebuilding yet.
- USA retail is verified. Disc browsing is independent of game version, but LDAR
  interpretation requires a verified executable file-link table anchored to
  `SYS/LDSYS.BIN`. Builds with embedded LDARs (including Japanese layouts) are
  not yet supported by the area view. Unrecognized builds retain disc browsing
  and show a diagnostic instead of using a USA filename map.
- Area/section labels follow the user's supplied reference. Additional LDAR
  entries retain their numeric IDs; they are not guessed to be named rooms.
- WFM text uses the actual font bitmaps, with a neutral grayscale palette. It is
  readable in the preview but not converted to Unicode; IDs are local to each
  font. Bubble styling, colour effects, timing, and blinking are not simulated.
- SPR frame assembly is an initial preview based on the supplied SPR tools.
  Page base defaults to the first shard in the selected section and can be
  overridden. Dynamic WPP uploads (notably Tomba's own graphics), special sprite
  flags, and animation playback remain to be implemented. Transparent frames
  explain this in the viewer.
- WMD displays the stored mesh objects with their textures and CLUTs. APD object
  placement, lighting from stored normals, collision rendering, and exact PSX
  semi-transparency/ordering are not simulated. It is not a complete game scene.
- Audio/video are metadata/hex only. Logical-sector exports are not a raw XA/STR
  sector-preserving media extractor.

## Validation

```powershell
python -m unittest discover -s tests -v
python -m tests.validate_disc "rom\Tomba! (USA).cue"
python -m tests.gui_smoke "rom\Tomba! (USA).cue"
```

18 synthetic regression tests cover ISO and raw-sector layouts, CUE track
selection/pregaps, directory cycles, GAM overlap and corruption, LDAR
continuations, VRAM overwrite semantics, CLUTs, sprite page bases, WFM control
arguments, and mesh decoding. Tests contain no game data.

The supplied USA image was checked end-to-end:

- 1,085 disc files; 1,054 file links matched to the ISO directory.
- 20 LDARs, 248 load groups, 1,907 valid asset ranges; all VRAM groups reconstructed.
- 227 WMD resources / 4,931 objects / 309,226 triangles decoded.
- 334 SPR resources / 42,755 frame-table entries parsed.
- 48 WFM3 resources / 9,971 dialogue entries / 4,541 glyphs parsed. One dialogue
  retains an explicit control/boundary diagnostic.
- 153 mesh objects from AREA00 base and section 00 matched the supplied OBJ
  exports' triangle positions exactly (after coordinate conversion).
- GUI checked with a real OpenGL context: disc open, tree navigation, textured
  geometry, dialogue, sprite rendering, and both palettes.

Counts include resources shared by multiple load groups; frame parsing is not
a claim that every sprite's dynamic texture state is reconstructed.

See [format notes](docs/formats.md) for implementation details and source credits.
