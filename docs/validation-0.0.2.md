# Viewer validation for 0.0.2

Portable label recovery found 21 custom content names in the existing Windows
settings and 218 names in the source label files, producing 239 named entries
in the external tombaedit_labels.json. Original registry values and source files
were copied into work/label-recovery before migration. Existing 36 sprite reviews
were also preserved. This inventory does not prove that every unsaved past edit
was recoverable.

Thirty-one unit checks now include immediate label-save restart persistence,
previous-save backups, corrupt-file protection, one-time registry migration,
cross-build isolation, preservation of other windows' changes, packaged paths,
and independent SPR/ANIM review identities. A real-disc GUI check exercised F2
autosave, a fresh MainWindow reading the saved name, independent warning/check
markers in both tree columns, clearing a review, and fitting a long label column.

SPR loading was profiled and optimized on US retail AREA00 banks 34FF and
39FF. Without the profiler, bank 34FF preparation fell from 15.29 s to
4.21 s on the first uncached visit, then 0.11 s from the persistent cache.
Bank 39FF preparation fell from 5.00 s to 3.91 s uncached and 0.05 s cached.
The bank-rendering benchmark fell from 2.31 s to 0.70 s and from 0.95 s to
0.23 s respectively. These are local measurements, not timing guarantees.
The GUI now initializes the bank once instead of rendering it before and
after supplying its final page/palette context.

Every rendered frame in those two banks had the same SHA-256 pixel digest
before and after the optimization, with matching page, CLUT, origin and
animation-link maps. Native tracing with targeted engine hooks matched the
previous instruction-by-instruction hooks for 104 distinct placements in
retail and PrePre 8. All six PrePre 8 sections still built with collision.
Twenty-six unit checks passed, including overlapping GAM references, safe
cache round trips, ROM/context invalidation and shared texture/STP caching.

The sampler sweep built 169 section scenes across seven distinct sampler
executables, including all languages present in the two European sampler
families. No scene-building exceptions occurred. PrePre 8 was then checked
separately in all six sections with its own ABI, collision origins, native
controller spawns and background motion. Both PrePre 9 sections and their
variants use the earlier overlay profile.

PrePre 8 section 00 was opened through the Qt/OpenGL level viewer. Its
native resource pointers resolved placed sprites and models, its two
background classes used measured camera motion, and collision contained
1,680 span records. Object visibility remains an initial-state preview;
AI, player-triggered transitions and all event conditions are not simulated.

Sequence playback was exercised through QMediaPlayer, including seeking
while playback remains active. PrePre 8's music renders on S_AREA01.VH/VB;
PrePre 9's two embedded tracks render on WVD bank 2. Compilation-disc bank
searches exclude other games. Some notes in early tracks fall outside their
bank's tone ranges; the source bank is resolved, but complete SPU output
including all game-time overrides is not claimed.

The computed Psy-Q pitch table matches all 192 entries in US retail.
Nineteen unit checks cover archive parsing, collision, native animation
ownership, zero timers, five-bit blending, shared-diagonal coverage and
content-label migration. The GUI regression also checks static SPR frames,
animation autoplay, FOUR playback, WPP access, F2 naming, APD scene context,
INS disassembly, sequence bank selection and the piano roll.

A structural sprite audit covered 6,955 frames in US retail, 6,957 in
European retail, 6,663 in the February preview, 1,317 in the Japanese demo
and 1,583 in PrePre 9. It found no malformed frame/part records. This is
not a pixel-by-pixel comparison with the running game.

## Remaining visual verification

PrePre 8 WMD 5080, DATA001.GAM, mesh 010 has GT4 faces at 0x10F18 and
0x10F58. Their stored page is 0x0011 and their stored CLUTs are 0x78B8 and
0x79F8. Both palettes are present in the section VRAM. Their raw textured
commands are 0x3D. The viewer retains these values; no substitute palette
has been invented. Their differing appearance still needs a running-game
capture to establish whether runtime code changes those palettes or faces.

Menus and effects whose runtime palette setup is not decoded remain
explicitly uncertain. The application should not be described as rendering
every sprite, animation state or CLUT pixel-perfectly yet.

Interactive CD Sampler Disc 6 contains MENU/MOVIES/TOMBA.STR but no playable
Tomba executable or area files. Its TOMB2 directory is Tomb Raider II, so
no Tomba level sections should be generated from it.
