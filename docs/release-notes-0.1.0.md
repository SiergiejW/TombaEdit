# TombaEdit 0.1.0

Changes since **0.0.2 — Sprite and animation reviews** (16 October 2026, commit `aacaf4e`), the [previous published release](https://github.com/SiergiejW/TombaEdit/releases).

## Japanese text and offline translation

- Added optional offline Japanese-to-English translation with user-selected CAT-Translate-7b safetensors or extracted Argos models. Translation stays local; model weights and the optional CAT runtime are not bundled or downloaded automatically.
- Added background translation of all discovered WFM banks, progress reporting and priority for the selected entry. Disabling bulk translation restores original list previews while individual-entry translation remains available.
- Translated text can appear directly in the display window using saved English Tomba glyphs, with an option to show the original Japanese.
- Added original-text and translation exports for either the current WFM bank or all banks: JSON, plain TXT, script TXT with control codes, and CSV.
- Added whole-disc text search in a small popup, with original/translated text selection, case matching and whole-word matching. Double-clicking a result opens the exact bank and entry.
- Entry lists now expose the full message with horizontal scrolling.
- Added access to PrePre 8's embedded dialogue in `TOMBA.EXE`, including text export and recovered Japanese character readings. Reconstructed readings are identified in the viewer and exports.
- Completed character decoding for all 413 entries in PrePre 9 / Pure Pure 09's four WFM banks, and corrected their dialogue and event-title preview palettes.

## Text usage evidence

- Added usage filters, per-entry evidence and purple **Possibly unused** entries, with matching counts in the file tree. Original and bilingual JSON exports include usage evidence.
- Pure Pure 09's four banks now have static selector results for all 413 entries, including the `CLEAR!` completion banner. Modified scripts, native code, placements or text resources invalidate the matching precomputed study.
- Added **Observed in-game** evidence where a matching emulator state directly confirms a selected entry. Such observations remain scoped to the verified build and scene.

## Levels, models and sprites

- Improved PrePre 8/9 resource loading, level population, sprite palette selection and prototype background handling.
- Improved level rendering of layered sprite transparency, runtime palette animation, section background colours and event-dependent object poses.
- Added the pause-menu Game Map viewer using the game's actual map model.
- Added GIF export for the whole level view, selected sprites, or animated model textures/UVs, with resolution and animation-range options.
- Added **CLUTs...** inspection for playing sprite animations. Palette overrides are shared with the sprite viewer, animation playback and saved GIFs.
- Unnamed sprite frames can inherit labels from named, verified animations without replacing existing frame labels.
- Improved shared sprite-bank context selection, including Tomba's outfit palettes and banks used in multiple areas.
- APD placement maps now show object/sprite previews at 50% opacity beneath selectable points, with zoom, pan and Fit controls.
- Improved object framing, polygon-aware orbit targets, UV-panel behaviour and persistent object-class labels.
- Added bounded disc-analysis caching and background analysis to reduce repeated scene tracing and loading work.
- Updated bundled labels and sprite-review data, including an **Empty** review status for banks that render blank in the selected context.

## Notes and limitations

- **Possibly unused is a research classification, not confirmation that text never appears in-game.** Other builds still have partial usage coverage.
- PrePre 8 still contains two undecoded dwarf-language symbol entries. Some recovered kanji readings have no surviving matching glyph artwork.
- Prototype rendering and sprite palette selection remain under investigation; this release does not claim perfect visual accuracy for every object or scene.
- Sprite and animation tabs approximate blending with transparency; the level view implements the console's blend modes.
- Machine translations can be inaccurate. Script translation exports are inspection material, not ROM-ready replacement scripts.
- TombaEdit remains read-only and does not rebuild discs.
