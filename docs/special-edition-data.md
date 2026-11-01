# Special Edition disc support and data comparison

The three supplied `rom/Special Edition/t_data_*.car` files are uncompressed
2352-byte Mode 2 PlayStation disc images. They can be opened directly; renaming
or extraction is unnecessary. The `.car` extension does not denote a separate
archive format in these files.

They contain revised data, especially controller prompts, palettes, fonts and
Japanese text. They do **not** supply an additional set of levels. The Japanese
image is a Japanese localization of the US-layout game, rather than a copy of
the original `Ore! Tomba` Japanese retail disc. The European image also has a
different executable revision from the local European retail reference.

## Compared inputs

The comparison uses the actual local images, not release filenames as proof of
their contents:

| Special Edition image | Files | Main reference | Byte-identical files | Changed files | Added / removed paths |
| --- | ---: | --- | ---: | ---: | --- |
| `t_data_u.car` | 1,085 | `Tomba! (USA).cue` | 932 | 153 | 0 / 0 |
| `t_data_j.car` | 1,085 | `Tomba! (USA).cue` | 878 | 207 | 0 / 0 |
| `t_data_e.car` | 2,287 | `Tombi! (Europe) (En,Es,Pt,Sv,Da).cue` | 1,288 | 998 | 1 / 1 |

The European path change is the boot executable `SCES_013.31` becoming
`SCES_013.30`. All three editions were additionally compared with every file
and parsed LDAR resource of `Ore! Tomba (Japan).cue` and both other retail
references. The machine report records hashes and exact changed paths.

## What differs

### US image

`SCUS_942.36` is byte-identical to US retail (SHA-1
`81cbc79f0230aeb4252e058039f47ac95a777f5a`). Its file-link and LDAR tables are
unchanged. Three of the 153 changed files decode to the same bytes after GAM
decompression; the other 150 have changed decoded content.

Every changed LDAR resource is a graphics/palette upload (`GRPX`, 126 load
occurrences) or a font/dialogue bank (`WFM`, 33 occurrences). Repeated palette
entries change from RGB555 `0x421F` to `0x22DE`. The WFM changes include replacing
PlayStation button glyphs with modern lettered button prompts; eleven of the
33 changed WFM ranges also alter dialogue token scripts. Message and glyph
counts remain unchanged in these banks. These are actual resource edits, even
though the executable is unchanged.

### Japanese image

This image uses the US filesystem, including `SCUS_942.36` and the US movie
filenames. Its executable SHA-1 is
`4e6c2154a9f899389dab59595fed8a01e1c11930`; its runtime layout follows the US
engine. Compared directly with original Japanese retail, there are 230
byte-identical files, 722 changed common paths, 133 added paths and 124 removed
paths. Those path differences mostly reflect the US disc layout and are not
133 new game assets.

Against US retail, the changed LDAR resources are `WFM` (38 load occurrences),
`GRPX` (127), `SPR` (19) and `INS` (53). Japanese dialogue, font data, menu
resources and associated code/load offsets differ. Some area overlays retain
the US bytes as a prefix and append 160 bytes; other overlays also have small
code changes. These code changes have not all been assigned gameplay meanings.

The 19 changed SPR occurrences are copies of one shared `39FF` bank. It still
has 267 frames and 7,868 bytes; only frames 31–33, 36–47 and 55 differ. The edits
move texture coordinates and change small glyph-sized rectangles, including
8×16 rectangles becoming 10×10. There are no added frames in this bank. This is
consistent with the revised UI/font data, although the exact visual meaning
of every changed frame has not been verified in its runtime texture context.

The image is a hybrid, retaining English title/menu banks while adding Japanese
menu text. For example, decoded `SYSTEM/DSPSUB.BIN` retains WFM banks at
`0xA22C` and `0xF8C0`, and contains appended Japanese `WFM2` banks at `0x28F9C`
and `0x313AC`; `SYSTEM/DSPSUB3.BIN` retains the English bank at `0x7420` and
contains a Japanese bank at `0x18AF8`. These appended banks are real extra data,
not new ISO filenames. The complete text collector finds 54 bank locations in
this image versus 51 in original Japanese retail: 30 `WFM2` Japanese banks and
24 `WFM3` English title/menu banks. Repeated copies are counted by source and
offset; this is not a count of distinct stories or new conversations.

### European image

All nine `EXE/MAIN0.EXE` through `MAIN8.EXE` programs differ from the local
European retail programs and are each 2,048 bytes shorter. Their engine tables
and runtime addresses differ, so support uses the verified executable hashes
and address profiles for this revision.

The supplied European reference boots `SCES_013.31`, whereas this image boots
`SCES_013.30`. Without an original `SCES_013.30` retail image for comparison,
some European differences may belong to an existing retail revision. The
counts below establish differences from the available reference; they do not
attribute every change specifically to Special Edition.

The changed LDAR resources are code (`INS`, 1,206 load occurrences), graphics
and palettes (`GRPX`, 1,158), and WFM font/dialogue data (210). Some WFM edits
change token scripts or message counts as well as glyph artwork. There are
nine language programs and load-table sets: English, French, German, Italian,
Dutch, Spanish, Portuguese, Swedish and Danish. The five languages in the local
reference filename do not describe the complete internal inventory.

## Levels, audio, movies and hidden data

Every Special Edition image has the same LDAR record inventory as its closest
US or European base: no added groups or resource slots. All corresponding
`WMD`, `WHM`, `APD`, `FOUR`, `WPP` and `CLM` resources are byte-identical to that
base. No added or modified level geometry, collision, placement, deformation or
animation banks were found by this comparison. Differences from original
Japanese retail must therefore be distinguished from differences already
present in the US retail game.

All ISO-listed audio and movie files have identical user payloads to the
corresponding US/European references, including the full **2,324-byte Form 2**
sector payloads used by XA/STR data. Comparing only the normal 2,048-byte ISO
reads would have missed the end of each Form 2 sector; this audit checks it.

Every non-file sector was also inspected. Novel non-file payloads occur only
in filesystem metadata: the primary volume descriptor at LBA 16, path tables
at LBAs 18–21 where changed, and ISO directory sectors. No additional novel
non-file user payload was found elsewhere in these images. Raw image hashes
still differ because of metadata, changed resources, sector addresses/error
correction and different trailing image lengths.

This establishes revised localization and presentation data, with no evidence
of additional levels or new audio/movie payloads inside these CAR images. It
does not establish the meaning of every code change or whether every retained
trigger can run. Assets stored outside the supplied CAR files, such as the
Special Edition wrapper's own gallery or soundtrack, are outside this audit.

## Reproduce

From the checkout, with the six local images at the paths above:

```powershell
python tools/compare_special_edition.py
```

The tool writes `work/special-edition-comparison.json` without changing ROMs.
Use `--rom-root` and `--output` to choose other input/output locations. The
report contains whole-image hashes, every ISO file's stored/decoded/stream
hashes, all parsed LDAR asset occurrences, embedded text-bank locations,
cross-retail matches, and ranges of novel non-file sectors. Asset counts are
load occurrences; shared bytes loaded in multiple groups can appear more than
once. The complete collector also includes valid WFM banks inside overlays
that no LDAR record names directly.

Support can be checked separately with:

```powershell
python tools/validate_special_edition.py --scenes
```

The local check resolved 20 / 20 / 180 load tables and read all 1,907 / 1,907 /
17,199 resource occurrences for US / Japanese / European respectively. All
nine European engine profiles were recognized, with sample town and ending
scenes checked. Thirteen exact glyph mappings cover the new lettered input
symbols and European variants; the remaining unread European shape is also
present in the retail reference, in two embedded banks.
