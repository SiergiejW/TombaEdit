# Native sprite viewing

Tombi-Decomp's retail milestone is pinned to
[`51e0f8a3d5d3b79eb42fea1d074a43ac3798db31`](https://github.com/afsenovilla/Tombi-Decomp/commit/51e0f8a3d5d3b79eb42fea1d074a43ac3798db31),
2026-11-09. Exact MIT-licensed animation and drawing references, including
the Japanese and USA branches, are preserved under
[`decomp/sprite-runtime`](decomp/sprite-runtime/manifest.json).
That manifest is separate from the older cut-content research snapshot.

## Implemented scope

- The default SPR view runs the selected disc's original initializer and
  draw routines. The decomp supplies their documented layouts and semantics;
  the editor does not compile or execute the PC/Android port.
- Each assigned animation entry retains its genuine address and complete
  step fields during draw capture. Object overrides, custom draw routines,
  UVs, shading and blend commands come from original instruction execution.
- Incomplete initializer/draw calls are rejected. Event flags are not tried
  until a plausible picture appears. Conflicting drawing variants remain
  ambiguous. No same-list inference, page guessing, grey palette, palette
  lending, majority texture choice or other-area substitution enters native
  previews.
- Native VRAM starts from explicit load-table uploads and tracks which words
  were uploaded. Unknown texture/CLUT words reject a frame; an uploaded
  all-zero palette is retained. Conditional WPP/town palette helpers used by
  the broader reconstructed viewer are excluded.
- PNG and animation sidecars identify executable, overlay and SPR hashes,
  selected load group, reference revision, evidence and captured draw
  commands. Native palette overrides are disabled.
- WPP reconstruction now respects every non-player part's CLUT and retains
  genuine empty palettes. It no longer borrows Tomba's outfit rows for
  unrelated banks. The matched player countdown palette selection remains.
- Animation timers/jumps/holds preserve `AnimAdvance` semantics, including
  65,536 calls for timer zero. JP retail's player table stops at 74 entries.
  Inferred adjacent scripts stay outside the normal linked list. GIF format
  losses are explicit; PNG strips preserve the native controls in JSON.

## Remaining work

This is not an assertion that every sprite, animation or CLUT is completely
and pixel-perfectly reproduced. Initialization runs in an isolated, bounded
environment with visibility/audio/game-service stubs. The editor's software
rasterizer has not been proved identical to the PSX GPU. Blended pixels of
an isolated transparent PNG have no gameplay framebuffer behind them.

Later object updates can change a script, palette, texture page, geometry or
other fields. Replaying each initial script entry with initialization fields
does not execute those later updates. Complete system-screen initialization,
event/controller-spawned objects, per-frame WPP uploads, palette evolution,
early-build drawing and alternate gameplay states remain outside this native
bank view. Missing or conflicting states stay unresolved rather than being
described as genuine output. A sprite can have several valid appearances;
there need not be a single universal palette for its frame number.

The advanced reconstructed mode and the level editor retain their broader
research behavior. They have not been certified by the native-bank work.

## Validation

Tests cover native versus inferred script links, zero/long timers,
NEXT/JUMP/END/JUMP_END completion, JP table bounds, GIF limitations,
per-piece CLUTs, transparent palettes, incomplete trace rejection, conflicting
contexts, native UI/export evidence and uploaded-versus-unknown VRAM.

The animation cursor was additionally compared with 240 calls to the
original JP/USA/PAL executable routines, including timer wrap and transition
boundaries. Real-disc native packet capture and software rendering were
checked for the three retail releases. These are bounded regression checks,
not an exhaustive all-frame visual equivalence audit.

Run the tests with writable isolated Qt INI settings; Windows registry
settings can be unavailable inside a restricted runner. The source tree's
existing `.gitignore` excludes `tests/`, so local regression files do not
appear in ordinary Git status.
