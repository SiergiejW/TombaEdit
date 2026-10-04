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

Build a standalone Windows executable with `python -m PyInstaller main.spec`.
The app uses the same classic icon set as Tomba2Edit, bundled in `icons/`.

## Browse

1. **File → Open BIN / CUE / ISO**, or drop an image onto the window.
2. The single tree shows the real ISO9660 folders and the area sections under
   each area. Expand a file or section to see its LDAR resources.
3. Select a resource to open its viewer. Double-click a Resources table row to
   jump to that resource. The filter matches names, types, sections and offsets.
4. **Export decoded file (binary)** writes the decompressed GAM bytes or
   selected asset slice. **Export original disc file** writes its containing
   ISO file. Viewers have format-specific exports, including PNG, GLB, MIDI,
   WAV and movie frames.

Supported previews:

| Resource | Current behavior |
| --- | --- |
| GAM | Bounded LZ decoding, LDAR asset ranges, embedded WFM detection, hex |
| WFM3 / D0FF / D1FF | Dialogue list, font-local glyph decoding, rendered text and font atlas |
| SPR | Whole-bank sheet, non-draggable sprite table, piece records, individual and batch PNG export |
| WMD | Multi-model 3D view, model visibility list, polygon and UV inspection, lit or unlit GLB export |
| GRPX | Labeled VRAM upload; all 4-bit pages first, plus 4/8/16-bit page views |
| CLUT GAM | Clickable PlayStation colour cells and PSX/RGB values |
| WVD / SEQ | Sound-bank and sample lists, playback, WAV and MIDI export |
| STR | Movie browser with MDEC frames, XA audio, playback, PNG/WAV/raw STR export and video export when ffmpeg is installed |
| WPP, WHM, APD, CLM, FOUR, INS, unknown | Typed resources, source ranges, metadata, hex and binary export |

Geometry controls follow Tomba2Edit: middle drag orbits, Shift plus middle
drag pans, right drag looks around, WASD moves, and the wheel zooms. The
**Frame model** button recenters all visible models. Clicking a triangle or
quad displays its source record and UV outline. A VRAM selector allows base
resources to use a section's palette and texture uploads.

## Scope of version 0.1

- Browsing and exporting only; no editing, recompression or disc rebuilding yet.
- Labels can be renamed, imported and exported per game build.
- USA retail is verified. Disc browsing is independent of game version, but LDAR
  interpretation requires a verified executable file-link table anchored to
  `SYS/LDSYS.BIN`. Builds with embedded LDARs (including Japanese layouts) are
  not yet supported by the area view. Unrecognized builds retain disc browsing
  and show a diagnostic instead of using a USA filename map.
- Area/section labels follow the user's supplied reference. Additional LDAR
  entries retain their numeric IDs; they are not guessed to be named rooms.
- WFM text uses the game's font bitmaps and palette. The USA glyph dictionary
  decodes observed glyphs into letters; other builds can still have unknown
  glyphs. The current text frame is an approximation. Game-specific text
  effects, timing and blinking are not simulated.
- SPR frame assembly remains approximate. Dynamic WPP uploads and some sprite
  flags are not decoded yet, so parts of a bank can show the wrong pixels or
  palette. The page offset can be adjusted, but that does not replace the
  missing upload sequence.
- WMD displays stored mesh objects with textures and CLUTs. APD object
  placement, stored-normal lighting, collision rendering and exact PSX blending
  are not simulated, so it is not a complete game scene.
- Movie video export needs ffmpeg on PATH. PNG frames, WAV sound and raw STR
  export do not need it.

## Validation

```powershell
python -m unittest discover -s tests -v
python -m tests.validate_disc "rom\Tomba! (USA).cue"
python tests/gui_smoke.py "rom\Tomba! (USA).cue"
python tests/gui_media_smoke.py "rom\Tomba! (USA).cue"
```

19 synthetic regression tests cover ISO and raw-sector layouts, CUE track
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
  geometry, dialogue, sprite rendering, movie decoding, sound bank browsing,
  CLUT inspection and both palettes.

Counts include resources shared by multiple load groups; frame parsing is not
a claim that every sprite's dynamic texture state is reconstructed.

See [format notes](docs/formats.md) for implementation details and source credits.
