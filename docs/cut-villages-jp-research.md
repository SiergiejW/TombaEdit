# Cut villages in Ore! Tomba: JP retail evidence and reconstruction leads

Research date: **31 October 2026**. Target: the supplied `rom/Ore! Tomba (Japan).cue` and its BIN. This is a research report, not a playable restoration. No game code, editor code, save, or disc image was modified.

## Editor helper palettes — 1 November 2026

The editor now provides premade **reconstructed helper CLUTs**, derived from the user's
`voc/ground truth` references. They are new editor presentation aids, not newly recovered retail
CLUT files and not a change to the upstream snapshot. The Buildings panel and manual prop/NPC
graphics picker default to these helpers for the three matched sheets; existing explicit palette
assignments remain unchanged.

| Sheet | Nonzero used indices matched | Source-pixel coverage | Unused palette slots estimated | Main reference |
|---|---:|---:|---:|---|
|Wood, group61|255|100%|0|`wood-overlay-restored.png`; five colours supplemented from `FullMapWIP.png`|
|Stone, group76|219|100%|36|`stone-overlay-restored.png`|
|Iron, group80|232|100%|23|`iron-overlay-restored.png`; individual prop/lift references checked too|

Colour-independent pixel-equality signatures find candidate patches, then full8×8 index/colour
correspondences must be one-to-one. Each anchored index needs at least8 votes and98% dominant-colour
agreement. Every seventh matching patch is omitted from fitting for a consistency check; because
patches overlap, this is not an independent statistical validation. Held-out quantized-colour agreement
is99.9967% Wood,99.9950% Stone and100% Iron. Unobserved entries are harmonic-filled, but none is used by
the three matched sheet images. Values are quantized to PS1 RGB555 with index0 transparent.

Reunited-town group86 has only56 usable colour anchors and3.1397% source-pixel coverage in these
references. It keeps a labelled grey fallback instead of receiving a mostly invented default palette.

Runtime data: `formats/level/building_helper_cluts.json`, including source-image SHA-256 values and
exact index-pixel fingerprints. A changed sheet fails the helper lookup. Regeneration and rendered
pixel/UI checks are in `tools/make_building_cluts.py` and `tools/validate_building_helpers.py`.
Only palettes and provenance are bundled; reference images and ROM textures are read from the user's
own files. Missing SPR placement/part tables remain missing, and manual graphics assignments remain
user reconstruction choices.

## Synchronization checkpoint — 1 November 2026

Latest upstream checked: **`b8fe30a1ad2660451c0b6c69b625bb18dac48403`**. The two commits after
the detailed `1c91428` refresh concern Android controller labels and launcher options, not cut-town
evidence. Comparing original `4220d8e` to this checkpoint changes no `src/i0nfo2/` retail source file;
the native JP hash-scoped dialogue/animation mappings therefore require no new address substitution.

The editor now bundles nine exact upstream references, including the complete Civilization article,
cut-content inventory, JP/build notes, format/event research, port/reconstruction documentation and
MIT license. Choose them in the Research document selector. `docs/decomp/manifest.json` records
the common revision, checked date, byte counts and SHA-256 of every file; the browser checks these
before calling the snapshot synchronized. `.gitattributes` preserves their exact source line endings.
Relative upstream links resolve against that same pinned revision. Original game assets are not bundled.

This synchronizes **cut-village and related retail/build/format/port research**, not every upstream
port feature or executable. Retained source data, reported visual matches, authored port behavior and
manual editor graphics choices keep separate evidence labels. A live manual crop never changes an
original NPC definition or proves that a prop originally used that drawing.

To repeat the controlled update, fetch the upstream checkout, run
`python tools/sync_decomp_research.py work/cut_village_research/upstream_current --ref origin/master --checked-date YYYY-MM-DD`,
review the document/code delta, and run `tools/validate_cut_villages.py` against the audited ROM.
The editor does not silently fetch or apply future upstream changes at startup.

## Upstream recalibration — 1 November 2026

Compared the original snapshot `4220d8e1dc8635e51cbe33e2ca4588486786e796` with upstream
**`1c91428b19f675c44d5afff14a532c1620cc0666`**. The rest of this report retains its original
snapshot addresses and evidence. References below describe the refreshed source; they do not replace
the hash-scoped JP runtime bindings or turn reconstruction hypotheses into recovered art.

### Independent confirmation of this report

Upstream added [SiergiejW's JP research — verification](https://github.com/afsenovilla/Tombi-Decomp/blob/1c91428b19f675c44d5afff14a532c1620cc0666/docs/CIVILIZATION.md#siergiejws-jp-research--verification),
explicitly attributing these findings to TombaEdit. It confirms the external MAIN animation scripts,
JP dialogue addresses, Wood relocation and unfinished controller, blocked iron-lump transaction and
unset actor pointer, bomb-scene stubs, lift stops, internal passages, empty JP section lists, shared
entrance pointers, and X19's repeated script payload. Its `tools/topdown.py` now follows MAIN pointers,
fixing the diagnostic limitation identified here. The old missing-animation claim is therefore
historical, not the current upstream position.

The verification is deliberately incomplete: upstream labels our JP music comparison **unverified**
(not rechecked), and the disc-residue result **partly checked** (CLUT/INFO2 copies and zero tail checked,
full allocation/file-slack audit not repeated). Neither is a refutation. Preserve our original scoped
checks; do not present them as independently confirmed in full. Its AREA18 viewer address is explicitly
PAL `800F548C` / JP `800F6804`, distinct from the JP Iron dialogue routine `800F5488`.

### New AREA18 evidence: FMV registration and animation windows

Upstream reports five AREA18 test actors registering to residents in `MOVIE/BUNMEI.STR` frames135–225,
with an almost unit-scale fit (reported x scale0.998, residuals at most1pixel). In its frames135–205
median mosaic, the proposed relation is **mosaic pixel = world position − (215,104)**.
This is a registration result reported upstream, **not independently re-fitted in this refresh**:

| Zero-based actor | Subtype | Reported FMV correspondence | Confidence boundary |
|---|---:|---|---|
|3|1|wide-hat figure, visible around frame220|position/figure correspondence; original SPR binding still missing|
|5|0|figure at castle gate, partly clipped at top|partial visual reference|
|9|6|bald crouching man|visual correspondence; not identified on A08600|
|7|3|boy on balcony|visual candidate; upstream points to Stone boy art on A07600|
|2|2|blonde head at bottom edge|too little visible to identify the complete sprite|

Actors0,1,4,6,8 are outside that visible movie region. Their identities cannot be filled in from this fit.
This makes AREA18 useful evidence for planned population/layout; it still does not provide a completed
town controller or dialogue caller.

The following animation windows were **independently decoded from the supplied JP INFO2 in this refresh**.
The definition table is `801000E4`, with12-byte entries and SPR slot11/page offset1 for all seven subtypes.
Follow each definition's animation pointer, read the indicated initial scripts, then follow8-byte
animation records and any control-word jump pointer. These are frame IDs, not recovered UV rectangles:

| Subtype | JP animation-pointer table | Initial scripts inspected | Frame set | Upstream visual interpretation |
|---|---|---|---|---|
|0|`80107D90`|0–11|0–26|first A08600 figure group, boy in vest; candidate|
|1|`80107DC0`|0–7|27–35|wide-hat figure,9 frames; candidate supported by FMV position|
|2|`80107DE0`|0–11|36–62|only blonde head at corresponding FMV position; unresolved|
|3|`80107E10`|0–11|63–89|balcony boy; candidate Stone boy, not A08600 figure identification|
|4|`80107E40`|0–11|90–116|possible Iron Man; not visible in fitted FMV region|
|5|`80107E70`|0–11|117–143|walking actor with idle/walk/talk scripts; not a save sign|
|6|`80107EE4`|0–7|144–149|bald crouching figure; candidate from FMV, art unresolved|

Do not interpret every24-pointer span as24 independent animations owned by one subtype. Upstream
documents overlapping script-table windows: later entries may be another subtype's initial scripts.
This is especially relevant to AREA18, where subtype1 has no independent talk frames. The original
SPR table is lost, so none of these frame ranges alone proves which surviving picture to draw.

### Save-point correction and presentation changes

Upstream newly documents top-down saving through **talk spots (layer2 type2E)**, not side-view save-sign
objects. PAL `topdownTalkSpotHandler` is `800EEAC8`, its step routine `800EE8B0`; it draws resident SPR
slot4/frame50 with page offset15hex, then opens the area's save prompt `(1,0)`.
Placed examples: AREA05 at `(240,456)` and AREA19 s2 at `(6,390)`. AREA08 has no such record.
The cut sets0D/0E/0F/10 have none, and AREA18's spawner makes actors, so **do not relabel an unidentified
AREA18 resident as a save sign**. These save-handler semantics/placements are source-backed upstream
PAL findings; this refresh does not assign them unverified JP function addresses.

`tools/civ_sheets.py` now includes `personajes` sheets, including AREA18, with explicit known/probable/
unknown labels and neutral silhouettes when an original drawing cannot be identified. It flags the old
Lumberjack Factory Worker names applied to lost-page subtypes as unsupported. This supports retaining
translucent stand-ins and explicit uncertainty in the editor, not promoting those names into identities.

Source: [refreshed Civilization research](https://github.com/afsenovilla/Tombi-Decomp/blob/1c91428b19f675c44d5afff14a532c1620cc0666/docs/CIVILIZATION.md),
[sheet generator](https://github.com/afsenovilla/Tombi-Decomp/blob/1c91428b19f675c44d5afff14a532c1620cc0666/tools/civ_sheets.py),
[fixed pointer reader](https://github.com/afsenovilla/Tombi-Decomp/blob/1c91428b19f675c44d5afff14a532c1620cc0666/tools/topdown.py).
No original cut-town map, collision grid, missing SPR table, or Iron subtype4 texture page was newly
recovered in this upstream delta. Original JP dialogue bindings and recovered animation data remain valid.

## What this investigation adds

The most useful new connection is **Iron Town subtype 4 → an INFO2 pointer table → 24 valid animation scripts in the resident main executable**. Their exact frame IDs and timing survive. The decomp documentation at the original pinned revision incorrectly labelled this subtype's animation table missing because its diagnostic reader rejected pointers outside INFO2; upstream has now corrected it. The sprite rectangles and matching texture page have not been recovered.

The investigation also found native JP details that go beyond positions, preserved text and patrols:

| Finding | Evidence level | Use for a future rebuild |
|---|---|---|
| 24 subtype-4 animation scripts, covering frames 148–202 | JP binary verified; PAL bytes compared | Original frame order and timing for the bomb-maker subtype; 24-script table below |
| Wood and Stone dialogue functions misidentified by the current editor | Native JP dispatch followed through actor and talk handlers | Correct actor-to-dialogue bindings; prevents treating a Baccus routine as Wood evidence |
| Iron lump `0x3D` handed in inside Iron Town house 5 → Iron Wheel `0x3E` → Clock Tower quest | JP controller/scene verified; retail consumer source identified | A real dependency across the cut town and the retail Clock Tower |
| The menu rejects the iron lump, the wheel scene has an unset actor pointer, and bomb-maker steps 5–7 are stubs | JP binary plus matched C | Exposes implementation work that merely restoring map/SPR files would not fix |
| Six exact lift boarding locations and two hidden passages inside Iron Town | JP native tables and movement code | Strong layout constraints independent of FMV or reconstructed scenery |
| Wood actor 1 is relocated conditionally; a dialogue handshake has no scene consumer | JP native code | Story-dependent layout and evidence of an unfinished scene |
| JP has its own embedded load/music scheme; all four town s0 lists terminate immediately | Native JP pointers and load records | Exact loading anchors; music must be supplied explicitly in a JP restoration |
| Orphan X19 has no unique animation-script payload in its area-specific tail | Entire tail accounted for and compared against X02 | Closes a plausible asset lead without discarding the historical scroll-controller remnant |
| Free sectors, file slack, dummy data, duplicate INFO2 and unlisted CLUTs audited | Supplied JP image read directly | Rules out these particular hiding places; preserves a precise boundary on negative results |

“New” here means absent from, correcting, or materially extending the pinned upstream research and this checkout's existing cut-village preview. It does not claim priority over unpublished community research.

## Scope, sources and reproducibility

The source of function names and PAL semantics is [afsenovilla/Tombi-Decomp](https://github.com/afsenovilla/Tombi-Decomp), pinned at commit **`4220d8e1dc8635e51cbe33e2ca4588486786e796`**. The checked-out source is `work/cut_village_research/upstream_current`. Its [CIVILIZATION.md](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/docs/CIVILIZATION.md), [CUT_CONTENT.md](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/docs/CUT_CONTENT.md), matched `src/i0nfo2/` code, JP symbols and raw JP bytes were used together. The older local `work/decomp` at `d8a8a5f0fe78eeddc589b69fba86f5b755dc566b` served only for orientation.

The upstream port already contains authored reconstruction patches. Port choices, FMV-derived palettes, reconstructed collision and stand-in sprites are **not retail evidence**. This report uses the retail code and data for its new assertions. The public decomp source and documentation are [MIT licensed](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/LICENSE); the game assets remain separate.

### Exact target identity

| Input | Size | SHA-1 |
|---|---:|---|
| `Ore! Tomba (Japan).bin` | 289,430,064 bytes | `c86baf702303e7e0963b99aff307b1c40e40478a` |
| ISO `SLPS_011.44` | 583,680 bytes | `07d577698ad31ec1a69b9d7b80a7c3f90b650888` |
| ISO `SYSTEM/INFO2.BIN` | 125,620 bytes (`0x1EAB4`) | `15ea8894a028cdabdda577b32ddfd281e023f51b` |
| ISO `SYSTEM/DSPSUB.BIN` | 162,088 bytes | `985875ab8ac54dc43f5ed88cfef75bfdf9608fc0` |
| ISO `SYSTEM/X19.BIN` | 179,944 bytes | `63bc65d813749580612d1f9907bde52f7eef0c39` |

BIN SHA-256: `fb5b8ea9e3bd328e88a6b8b8ecb0b493d0dda5a9b5f732a7a6e4c9b146d9cd2b`.

The CUE selects one `MODE2/2352` track at index `00:00:00`. ISO payloads occupy 2,048 bytes per logical sector, starting at byte 24 in the raw sector. The image and ISO volume both contain 123,057 sectors.

### Address conventions

- **JP RAM address** means the supplied Japanese retail build. `SLPS_011.44` loads at `0x80010000`; its file offset is `address - 0x80010000 + 0x800`.
- JP raw overlays, including INFO2 and DSPSUB, are interpreted at `0x800E9AF8`; overlay file offset is `address - 0x800E9AF8`.
- **PAL address** is a function/data address in the pinned decomp's European target. It is a source anchor, not a JP patch address. JP/PAL differences are not one universal delta.
- `.GAM +offset` means offset in the **decompressed** file unless explicitly marked otherwise.
- JP `SYS/LDSYS.BIN` / `SYS/LDARnn.BIN` names in TombaEdit are logical views of lists embedded in `SLPS_011.44`. No physical files with those paths exist on this image. In particular, a synthesized empty `LoadGroup.offset == 0` is not an address of an original empty list.
- Resident numbers in the findings are **zero based** when called an index or record number; house numbers are the engine's room values, starting at 1. Tables explicitly using `#1` style are one based.

**Verified** means the stated bytes, native control-flow edge, or table value was read. **Source-backed** means the matched PAL implementation supports the claim but a JP counterpart is not established here. **Inference** means interpretation of those facts. **Unresolved** means a specific missing link remains. No static absence result here proves all game-state reachability or all possible computed references.

## Baseline: what survives, and what is still missing

These points were already established upstream; they orient the new findings without presenting known routes or text as discoveries.

| Intended town | Area/section | NPC set | Residents | Props | House rectangles | State |
|---|---|---:|---:|---:|---:|---|
| Wood People's village / Lumberjack Town | 11:0 | `0x0D` | 12 | 14 | 3 | placement, actor/scenery logic and text remain; section list empty |
| Stone People's town / Stonestown | 16:0 | `0x0E` | 13 | 7, plus alternate list | 4 | placement and substantial scene logic remain; section list empty |
| Iron Men's town / Iron Town | 17:0 | `0x0F` | 16 | 35 | 5 | placement, lift and passage logic remain; several quest scenes incomplete |
| Reunited town, epilogue/test data | 18:0 | `0x10` | 10 | 0 | no village house list established | viewer-like actor code, no completed dialogue/controller path |

The preserved definition records say more than “some sprites once existed”: they retain contact boxes, relative page offsets, SPR slot and animation-pointer tables. The missing layer is principally the town-specific **SPR frame/part tables**, together with map picture/collision and some needed pixel pages. The recovered external scripts below are an additional surviving layer.

| Layer | Preserved evidence | Boundary |
|---|---|---|
| Resident/prop placement | INFO2 fixed lists | Placement alone omits spawn gates, conditional moves and scripted passages |
| Actor/scenery definitions | INFO2 `{box,w1e,spad,anims}` | Page offset alone does not identify UV rectangles or palette |
| Animation selection | INFO2 routines and script tables, plus newly traced MAIN scripts | Valid script does not supply missing SPR parts |
| Texture pixels | Menu-close reload pages in system groups 61/76/80/86 | Reloads are clipped VRAM restoration, not complete original section loads |
| Resident colours | Existing area CLUT rows documented upstream | Some colour identifications are visual/community comparisons, not original subtype-to-part bindings |
| Map picture and cell map | Working engine format survives | No original cut-town picture/cell payload recovered in this audit |
| Event/text links | INFO2, JP text and menu item/event data | Orphan helpers, stubs and uncaught menu restrictions matter |

The engine's established world-to-map relation is picture pixel `(x+128,y-40)`. The cell-map cells are 8×8 pixels, low 7 bits collision shape and high bit a room trigger. Trigger rectangles set room `n`; room-0 roofs/props are hidden while the corresponding interior actors are shown. Source anchors: [topdownLoadMapTiles](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/topdownLoadMapTiles.c), [topdownCollideMapTile](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/topdownCollideMapTile.c), [topdownPlayerMainStep](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/topdownPlayerMainStep.c). These are reconstruction formats and constraints, not recovered maps.

The retail hub bypasses the cut towns: AREA18 s1 goes to 11:1, 17:1 and 16:4. The cut-town outgoing topology in the matched PAL source is:

| Town | Preserved outgoing connection | Trigger shape |
|---|---|---|
| Wood 11:0 | hub 18:1 spawn 1 | x>555, y361..460 |
| Wood 11:0 | factory 11:1 spawn 0 | x199..263, y<79 |
| Stone 16:0 | hub 18:1 spawn 3 | x<-116, y520..529 |
| Stone 16:0 | dried wishing well 11:2 spawn 0 | x107..114, y319..320 |
| Stone 16:0 | cut Clock Tower 16:1 spawn 0 | x>147, y<74 |
| Iron 17:0 | hub 18:1 spawn 2 | x167..279, y>570 |
| Iron 17:0 | Iron Castle 17:1 spawn 0 | x176..271, y<80 |

See [topdownSectionStepC](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/topdownSectionStepC.c), [StepD](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/topdownSectionStepD.c), [StepE](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/topdownSectionStepE.c) and the upstream [entry-route audit](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/docs/CIVILIZATION.md). Those PAL exit routines were not remapped instruction by instruction to JP in this investigation. Native JP load, bounds, controller and entrance data are mapped later in this file.

## Recovered animation connection

### Iron Town subtype 4 has 24 surviving animation scripts in MAIN

Upstream `docs/CIVILIZATION.md:224` says subtype 4 has no animation table and line 496 reports its frames as none. This is a parser coverage failure: `tools/topdown.py:405-409` accepts only script pointers inside I0NFO2, while this subtype deliberately points to resident executable data. No production code was changed.

Confirmed chain (JP):

```
INFO2 topdownA17ActorInit 0x800F64AC
 -> TOPDOWN_A17_ACTOR_DEFS at 0x801000A8, subtype 4 entry 0x801000D8
 -> {box=(8,16,8,16), w1e=8, spad=11, anims=0x8010854C}
 -> 24 pointers at 0x8010854C..0x801085A8
 -> resident SLPS_011.44 scripts 0x80014B6C..0x80014EE4
 -> 55 unique frame IDs: every integer 148..202
```

The entire 920-byte script region JP `[0x80014B6C,0x80014F04)` is byte-identical to PAL `[0x80014C90,0x80015028)`: SHA-256 `89d502a0ba3333b14aadcf234a58e5b48efea6ed39851a6ed0f3d171ff2b4d1f`. This includes frame order, hit-box words, signed arguments and controls; the hit-box and signed-argument words are zero throughout. The scripts are valid 8-byte animation records, not code words that happen to look like pointers.

JP file offsets: INFO2 subtype-4 def `0x165E0`, pointer table `0x1EA54`; SLPS_011.44 script region `0x536C..0x5703` including its 0x800-byte PS-X EXE header. Address-to-file conversion: overlay offset = address - `0x800E9AF8`; EXE offset = address - `0x80010000` + `0x800`.

Two resident placements use subtype 4: record 3 (fourth actor) at (223,123), dialogue case 3, is the bomb-maker branch; record 4 (fifth actor) at (223,0), dialogue case 4, returns no normal dialogue. Both initially select script 0 because their `wb4`/animation-set field is zero; their facing field is 3. Do not label the second actor as an identified character.

This recovers animation selection/timing and a concrete MAIN-to-cut-village connection. It does **not** recover the village's missing SPR_DATA[11] frame rectangles or the texture page at base 8, and it does not establish that all 24 scripts are exercised by the preserved village state machine. Idle, walking and talk code explicitly selects scripts from the table; scene indices above those normal ranges remain reconstruction leads.

### All 24 scripts

`ticks` lists the low 14 control bits per step, in update ticks (not assumed video FPS). Every final control has bit 0x8000 set, so each sequence holds its final frame and reports completion; there are no pointer jumps in these 24 sequences. Full control words are represented without loss by the tick sequence plus “set 0x8000 on the final step”. All hit-box/argument words are zero.

| Index | JP script | PAL script | Exact frame order | Exact ticks per step |
|---|---|---|---|---|
| 0 | `0x80014B6C` | `0x80014C90` | 169,170 | 14,14 |
| 1 | `0x80014B7C` | `0x80014CA0` | 148 | 60 |
| 2 | `0x80014B84` | `0x80014CA8` | 149 | 60 |
| 3 | `0x80014B8C` | `0x80014CB0` | 150 | 60 |
| 4 | `0x80014B94` | `0x80014CB8` | 151,152,153,154,155,156 | 8,8,8,8,8,8 |
| 5 | `0x80014BC4` | `0x80014CE8` | 157,158,159,160,161,162 | 8,8,8,8,8,8 |
| 6 | `0x80014BF4` | `0x80014D18` | 163,164,165,166,167,168 | 8,8,8,8,8,8 |
| 7 | `0x80014C24` | `0x80014D48` | 171,172 | 14,14 |
| 8 | `0x80014C34` | `0x80014D58` | 173,174 | 14,14 |
| 9 | `0x80014C44` | `0x80014D68` | 175,176,175,176,175,176,175,176 | 18,18,8,8,8,8,18,18 |
| 10 | `0x80014C84` | `0x80014DA8` | 177,178,179,178,179,178,179,178 | 18,18,8,8,8,8,18,18 |
| 11 | `0x80014CC4` | `0x80014DE8` | 180,181,182,181,182,181,182,181 | 18,18,8,8,8,8,18,18 |
| 12 | `0x80014D04` | `0x80014E28` | 183,184,183,184,183,184,183,184,183,184,183,184 | 18,6,6,6,6,6,6,6,6,8,8,10 |
| 13 | `0x80014D64` | `0x80014E88` | 185,186,185,186,185,186,185,186,185,186,185,186 | 18,6,6,6,6,6,6,6,6,8,8,10 |
| 14 | `0x80014DC4` | `0x80014EE8` | 187,188,187,188,187,188,187,188,187,188,187,188 | 18,6,6,6,6,6,6,6,6,8,8,10 |
| 15 | `0x80014E24` | `0x80014F48` | 189 | 60 |
| 16 | `0x80014E2C` | `0x80014F50` | 190 | 60 |
| 17 | `0x80014E34` | `0x80014F58` | 191 | 60 |
| 18 | `0x80014E3C` | `0x80014F60` | 192,193,192,148 | 7,16,5,40 |
| 19 | `0x80014E5C` | `0x80014F80` | 194,195,194,196 | 7,16,5,40 |
| 20 | `0x80014E7C` | `0x80014FA0` | 197,198,197,199 | 7,16,5,40 |
| 21 | `0x80014E9C` | `0x80014FC0` | 149,194,192,202,201 | 9,9,9,11,6 |
| 22 | `0x80014EC4` | `0x80014FE8` | 200,201,202,201 | 11,6,11,6 |
| 23 | `0x80014EE4` | `0x80015008` | 170,192,195,149 | 7,9,9,9 |

### Source anchors and runtime acceptance boundaries

- `src/i0nfo2/topdownA17ActorInit.c:16-26`, PAL function `0x800F5134`: subtype indexes 12-byte records; definition supplies page offset, SPR slot and animation-pointer table; `b0d=0` preserves each sprite part's CLUT. JP function `0x800F64AC` verified instruction-by-instruction: `lw` table pointer at `0x800F65B0`, `lw` chosen script at `0x800F65BC`, store to object+0x24 at `0x800F65C4`.
- `src/i0nfo2/topdownA17ActorStep.c:15-20,31` uses `TOPDOWN_A17_ACTOR_ANIMS[subtype][0][animFrame]`; patrol handlers add four to facing. `src/i0nfo2/topdownA17ActorTalkStep.c:29-34` selects script `b69+7`.
- `src/AnimAdvance.c:9-35`, PAL `0x8001FEC0`: each 8-byte step has duration/control at +6; low14 bits set timer, 0x8000 holds and reports end; 0x4000/0xC000 follow a pointer after the step. The audit implements those rules over both executable and overlay memory, with bounds and cycle checks.
- `src/drawObjectSprite.c:87-90,115-121`, PAL `0x8005296C`: frame word indexes `d3c`, which is SPR_DATA[11] for this subtype; relative part tpage is incremented by `w1e`. No check limits animation scripts to the overlay. Thus scripts in resident MAIN are legitimate runtime inputs. However, a valid script cannot replace missing SPR frame metadata.
- `tools/topdown.py:392-411`: diagnostic-only restriction that caused the missing-script claim. A future audit reader should model all resident regions, not infer absence when a pointer crosses an overlay boundary.

### JP resource preservation: exact reload chains independently checked

All following groups are in the load table embedded in `SLPS_011.44` (exposed by TombaEdit as the logical name `SYS/LDSYS.BIN`; there is no physical JP file at that path). Each ends with `SYSTEM/INFO2.BIN` (0xF0FF, size 0x1EAB4). The group assets preserve texture pixels and overlay code, but include no SPR slot-11 table, collision kind0x8E or map-picture kind0x8F. Group identity for the towns is already established upstream; below is the exact JP filename/record map suitable for extraction.

| Town | SYS group | Texture files (JP) | Decompressed bytes | VRAM upload rectangles | First GRPX record file offset in SLPS_011.44 |
|---|---|---|---|---|---|
| Wood / AREA11 s0 | 61 | `SYSTEM/A00147.000` | 0x38000 | (64,0,448,256) | 0x6ACE4 |
| Stone / AREA16 s0 | 76 | `SYSTEM/A00153.000`, `A00154.000` | 0x28000 + 0x10000 | (64,0,320,256), (384,0,128,256) | 0x6B11C |
| Iron / AREA17 s0 | 80 | `SYSTEM/A00163.000` | 0x38000 | (64,0,448,256) | 0x6B270 |
| Reunited / AREA18 s0 | 86 | `SYSTEM/A00175.000`, `A00176.000` | 0x28000 + 0x10000 | (64,0,320,256), (384,0,128,256) | 0x6B464 |

For these VRAM rectangles, x/width are 16-bit word units and y/height are rows, not 4bpp texel dimensions. x64..511 at y0..255 covers texture page bases1..7. Subtype4's w1e8 would add page8 (x512,y0) when its missing parts have relative page0. The reload group does not supply that region, and AREA17's base group0 supplies x0, x704 and x192/y256 instead. This establishes absence from the preserved reload/base group, **not non-existence of every possible compatible pixel elsewhere on disc**. The relative page encoded in the missing sprite parts remains a constraint to recover. Existing working actors often use relative page0; that is analogy, not direct proof for the lost parts.

JP actor-def tables independently identified by exact `w1e`/slot sequences (these offsets cannot be obtained by shifting the overlay load base alone):

| Table | JP address | PAL address | Definition count | Each subtype's w1e |
|---|---|---|---|---|
| A11 actors | 0x800FFFFC | 0x800FEEB8 | 5 | 1,10,11,16,17 |
| A16 actors | 0x80100038 | 0x800FEEF4 | 4 | 1,1,1,17 |
| A17 actors | 0x801000A8 | 0x800FEF64 | 5 | 1,10,11,16,8 |
| A18 actors | 0x801000E4 | 0x800FEFA0 | 7 | 1,1,1,1,1,1,1 |

All eight JP INFO2 copies (SYSTEM and AREA05/08/11/16/17/18/19) are byte-identical, 125620 bytes, SHA-256 `254b171cb86a19f98edfc2721db1694949d9b3cb0625591ec92dd2667e650fa6`. There is no alternate per-town INFO2 under these paths.


## Confirmed correction: current editor assigns two villages the wrong dialogue functions

This was verified from the native dispatch path, not inferred from the count of cases.

JP layer-2 dispatch table `0x80071784`, entry `0x30`, points to MAIN0 `0x8003CA98`. That function loads the selected area (`0x8009E508`), subtracts 5, then dispatches through MAIN0 jump table `0x80013460`. The relevant entries lead to these JALs:

| Area | MAIN0 call site | Actor handler | Actor step | Talk step | Actual dialogue function | Cases |
|---|---|---|---|---|---|---|
| 11 | `0x8003CAF0` | `0x800F4020` | `0x800F3D0C` | `0x800F321C` | **`0x800F3000`** | 11, IDs 0–10 |
| 16 | `0x8003CB00` | `0x800F50FC` | `0x800F4DE4` | `0x800F43D0` | **`0x800F41FC`** | 16, IDs 0–15 |
| 17 | `0x8003CB10` | `0x800F6604` | `0x800F62E8` | `0x800F60B4` | **`0x800F5488`** | 16, IDs 0–15 |

Corresponding PAL semantic functions are `src/i0nfo2/topdownA11ActorOpenDialogue.c` (`0x800F1C88`), `topdownA16ActorOpenDialogue.c` (`0x800F2E84`) and `topdownA17ActorOpenDialogue.c` (`0x800F4110`). JP limits are directly visible at `0x800F304C` (11), `0x800F4248` (16), `0x800F54D4` (16); each reads actor `+0xBA`.

Calling current `formats.level.cut_towns.dialogue_routines` on the actual JP overlay returns:

```
set 0D -> 0x800F0A04, 23 cases   WRONG: Baccus Village actor dialogue
set 0E -> 0x800F3000, 11 cases   WRONG: Lumberjack Town actor dialogue
set 0F -> 0x800F5488, 16 cases   correct Iron Town
```

Cause: `HANDLER_CASES = {0x0D: 23, 0x0E: 11, 0x0F: 16}` identifies functions by case count alone, while Stonetown and Iron Town share the count 16. The dictionary overwrites Stonetown's candidate when it encounters Iron Town. The 23-case function belongs to the intact AREA05 actor path, not Lumberjack Town. Existing editor dialogue displays are therefore not evidence of original NPC bindings for AREA11/16. The raw placement tables remain separately verified.

Reproduction: `python work/cut_village_research/logic_dispatch.py` and `logic_confirm.py`; textual proof saved in matching `.txt` files. `logic_map.py` uses normalized instruction matching only to discover candidates; the dispatch/JAL chain and native jump tables supply the actual verification.

## Lumberjack Town has a conditional resident position, plus an unfinished scene handshake

PAL `spawnNpcSet0D` `0x800FB054` (`src/i0nfo2/spawnNpcSet0D.c:78–79`) contains:

```
if (D_8009CDF1 == 0) SCRIPT_OBJECTS[1]->x = -200;
```

JP equivalent starts `0x800FC198`. The test/override survives at `0x800FC32C–0x800FC34C`: event/state byte **`0x8009E999`** is read and, when zero, actor 1's x word is replaced by `-200`. This byte is event `0x4D` (Civilization Machine), because JP event-byte base is `0x8009E94C`. Raw actor 1 is at `(12,256)` in room 1. A reconstruction that merely draws placements misses this initial relocation. The code only changes x; it does not delete the actor or change its room.

The same spawner computes shared dialogue phase 0/1/2 from event `0x66` (`0x8009E9B2`, PAL `D_8009CE0A`) and completion of event `0x4D`; the destination is JP **`0x8009EB4D`** (PAL `D_8009CFA5`). These phases link the Wood and Iron towns to the machine/power storyline. They are sampled at spawn; the NPC dialogue does not recompute them continuously.

True Wood dialogue case 1 (`topdownA11ActorOpenDialogue.c:23–29`, JP `0x800F3080…`) writes transient flag JP **`0x8009EB51`** (PAL `D_8009CFA9`) to 1 or 2 depending on event `0x4F` (`D_8009CDF3` / JP `0x8009E99B`). It returns no message.

The scene controller **`updateNpcSet0D` PAL `0x800FB32C`, JP `0x800FC470` is empty in its live state 1** (`src/i0nfo2/updateNpcSet0D.c:14–15`). It spawns residents, idles, and can be freed. It does not consume this flag or execute a raft-making/woodworking scene.

An orphan helper survives: `topdownA11ActorDialogueBank2`, PAL `0x800F1BAC`, JP **`0x800F2F24`**, length `0xDC`. It can show `(2,4)`, then `(2,5)`, and set `o->state=2, o->wac=0x4F`, which would ask the general talk cleanup to start event 0x4F. However there are **zero direct JAL callers and zero 32-bit pointer references to this entry** in JP INFO2 and MAIN0. Source search likewise finds its definition but no named call. This is bounded static evidence, not a proof against every imaginable computed call; the normal Wood actor chain never calls it.

This changes the interpretation of the baseline docs: the helper preserves intended dialogue/event behavior, but does not establish that Wood's surviving controller can run the corresponding scene. The Green Fortune Teller's actor case 11 is also outside the actual 0–10 switch on JP, just as on PAL. His recovered text needs an authored caller.

## Iron Town's iron-lump → Iron Wheel transaction is more specific, and less complete, than the overview suggests

PAL `npcSet0FPickStep` `0x800FD8B0` (`src/i0nfo2/npcSet0FPickStep.c:17–18`); JP **`0x800FE9F4`**. The surviving trigger is:

```
use_item_pending == 1 && room == 5 && use_item_id == 0x3D -> controller step 4
```

JP native fields: use pending **`0x8009E4E8`**, use ID **`0x8009E4E9`**, room **`0x800A7BE3`**. The decisive checks are `0x800FEA68–0x800FEAA8`. This is an **indoor room-5 material hand-in**, not simply talking to any smith.

Item `0x3D` is called `ITEM_IRONHAMMER` in the upstream enum, but that symbol must not be treated as its retail name. The item-description audit decoded the native JP item description as a lump of iron suitable for sturdy tools. Use **iron lump / Iron** in the report, retaining `ITEM_IRONHAMMER` only to locate source.

Step 4 is `npcSet0FSceneStep4`, PAL `0x800FD688`, JP **`0x800FE7CC`**. It shows `(2,7)`, turns the resident, waits 60 controller updates, shows `(2,8)`, grants **item `0x3E` (Iron Wheel)** and completes **event `0x62`** (`src/i0nfo2/npcSet0FSceneStep4.c:56–59`). The native JP calls/constant operands survive (see `logic_confirm.txt`).

Important reconstruction gaps:

- The independent menu audit found the native inventory use condition for item 0x3D is the false script; the ordinary menu cannot currently send this item-use request. See the DSPSUB addresses below for independent proof.
- Source explicitly records an uninitialized NPC pointer in this scene (`npcSet0FSceneStep4.c:20`); Native JP also saves register `s1` at `0x800FE7DC` without assigning it an NPC value before use: `0x800FE84C` passes `s1` as the actor and `0x800FE85C` stores the message pointer at actor+0x90; `0x800FE8A0` later reads actor+0x90 through `s1`. The normalized candidate comparison agrees with the PAL routine, but these native operations supply the direct JP proof. It does not initialize the actor pointer from `SCRIPT_OBJECTS[2]` as the neighboring smith intro scene does. A restoration needs to validate/repair this scene, not merely expose the section.
- There is no removal of item 0x3D in this scene and no event-completion check around the hand-in trigger. Do not invent a consumption policy or one-time guard and describe it as recovered original behavior.

Cross-overlay connection to intact retail code (PAL addresses; exact JP X016 counterpart requires separate mapping):

- `src/x016/brokenStoneGearsTalk.c` PAL **`0x801174B8`** starts event **0x62** (line 39), asking for a replacement gear.
- `src/x016/checkStoneGearsTrigger.c` PAL **`0x801177B0`**, JP version header **`0x80116B60`**, accepts used item **0x3E** at the gear location (current source lines 19/42).
- `src/x016/brokenStoneGearsRepair.c` PAL **`0x8011767C`** completes **event0x61** and removes **item0x3E** (lines24–25).

Thus the surviving cut-town origin of the Iron Wheel and the intact Clock Tower consumer form a real item/event dependency. Event0x62 is not an isolated unused title. Whether the item could be obtained elsewhere in normal JP play is a separate placement/reward audit; this report does not assume it could not.

## Bomb-maker dialogue requests three scenes that are explicit stubs on JP too

`topdownA17ActorDialogueBank3`, PAL **`0x800F3F80`**, JP **`0x800F52F8`**, is called by Iron dialogue case3 (the outdoor subtype4 resident at `(223,123)`). It reads event0x61, event0x66, event0x69, machine event0x4D, and the Bomb inventory byte to select dialogue or request a controller scene.

`npcSet0FPickStep` JP `0x800FE9F4` consumes these handshakes:

| Trigger | JP byte | Action |
|---|---|---|
| event0x69 equals2 | `0x8009E9B5` | increment to3, select step5 |
| PAL `D_8009CFA6` equals1 | `0x8009EB4E` | increment to2, select step7 |
| PAL `D_8009CFAB` equals1 | `0x8009EB53` | clear, select step6 |

But **all three steps 5,6,7 select one reset-only block** in JP `updateNpcSet0F` **`0x800FEC78`**: the jump table at **`0x800EA534`** points all three entries at **`0x800FED64`**. That block tests scene state, resets step/state to zero and returns; it does not make or grant a bomb. PAL source shows the same omission in `src/i0nfo2/updateNpcSet0F.c:40–47`, also in `stepNpcSet0F.c:32–39`.

This is stronger than text merely being unused: the dialogue-to-scene request, transient flags, and state transition remain, while the requested scene bodies are reset-only stubs. Restoration should preserve this distinction. It cannot claim all Iron Town quest behavior is complete simply because the overlay has 100% matched functions.

Retail bomb-related connections that survive outside the town:

- MAIN0 `src/rewardItem.c` PAL **`0x8003CC8C`**, lines54–55: picking up `ITEM_BOMB` completes event0x69.
- MAIN0 `src/updateItemObject.c` PAL **`0x8003DD28`**, line71: world item subtype0x3C is removed when event0x69 is zero or0xFF. It only exists while the bomb event is active.
- `src/x011/factoryBossIronCastleDoorTalk.c` PAL **`0x80118328`** starts event0x69 (line40).
- `src/x017/ironCastleMachineRoomTalk.c` PAL **`0x80117224`** starts event0x66; `stepWaterfallHintNpcTalk.c` PAL **`0x80117C84`** watches used item0x3C plus event0x66 state1, and completes event0x66 after the door sequence.

These are retail repurposing/parallel connections. They do not prove every associated retail NPC or texture originally belonged inside the cut town.

Iron subtype4 indoor actor4 (`dlg4`, room1, `(223,0)`) has no normal dialogue: JP switch entry4 resolves to **`0x800F5794`**, the zero-return epilogue. Its exact intended role remains unknown. The animation audit independently recovered subtype4's external animation table; therefore the absence of a dialogue case is **not** evidence of missing subtype4 animation scripts.

## Iron Town preserves exact boarding points and two hidden passage traversals

The baseline describes lifts but does not enumerate this stronger topology evidence.

PAL `npcSet0FCheckTriggerSpots` **`0x800FCFA8`**, JP **`0x800FE0EC`**, reads seven `{s16 x,y}` pairs at JP **`0x801018CC`** (PAL `D_80100788`). Each genuine point accepts the inclusive 3×3 square `[x,x+2]×[y,y+2]` and selects lift scene3. Table:

| Index | Point | Mechanism |
|---|---|---|
|0|(55,375)|lower lift left stop|
|1|(231,367)|lower lift middle stop|
|2|(390,375)|lower lift right stop|
|3|(-999,-999)|deliberate unusable placeholder|
|4|(111,159)|upper lift left stop|
|5|(230,151)|upper lift middle stop|
|6|(334,159)|upper lift right stop|

Mechanism assignment follows scene3's `k=(index>=4)` and `index&3`, not a guess based on the picture. `npcSet0FSceneStep3` PAL `0x800FC9E4`, JP **`0x800FDB28`**, selects animation/facing, moves Tomba onto the lift, sets rider flag0x40 in the mechanism state, requests its next stop and then walks Tomba off it. Mechanism arrays are shared with scenery update. This gives six exact usable attachment locations even without the lost map.

Four additional hard-coded rectangles in the same trigger checker select hidden player traversals:

| Scene | JP entry | PAL entry | Inclusive trigger rectangle | Forced initial player position | Motion |
|---|---|---|---|---|---|
|8|`0x800FE22C`|`0x800FD0E8`|x100–128,y420–428|(116,426)|up84px; toggles progress-dependent prop15 state|
|9|`0x800FE3D8`|`0x800FD294`|x110–128,y348–354|(116,346)|down84px|
|10|`0x800FE504`|`0x800FD3C0`|x295–312,y406–410|(302,407)|up145px, x approaches288 every other controller update|
|11|`0x800FE668`|`0x800FD524`|x280–296,y268–272|(288,272)|down145px, x approaches302 every other controller update|

The routines hide the player for most of the motion, restore visibility near the end, lock/unlock input and keep the same section; there is no area-warp call. They constrain two north/south passages in the original town layout. Whether each passage was a tunnel, gate opening or covered stair cannot be established from code alone. Do not call them exits to another village or use them to infer a missing area file.

Exact source: `src/i0nfo2/npcSet0FCheckTriggerSpots.c:26–40`, `npcSet0FSceneStep8.c`, `...Step9.c`, `...Step10.c`, `...Step11.c`. JP complete native listing and table extraction: `logic_paths.txt`, `logic_spots.txt`; no native data was edited.


## Independent menu evidence: the missing iron-lump hand-in is blocked before INFO2

The room-5 iron-lump check above is not enough to make the wheel transaction usable. The native JP inventory condition table explicitly rejects item `0x3D` everywhere. This connects **DSPSUB inventory policy → pending-use flag → cut-town scene** and explains an otherwise easy-to-miss failure when rebuilding the town.

### Native JP tables and call sites

Source file: `SYSTEM/DSPSUB.BIN`, loaded at `0x800E9AF8`.

| Data/code | JP RAM address | File offset | Meaning |
|---|---:|---:|---|
| Item → condition ID array | `0x8010472C` | `0x1AC34` | 200 bytes compared against PAL |
| Condition pointer table | `0x80105514` | `0x1BA1C` | 45 JP script pointers; PAL has 46 |
| Condition operation table | `0x801055C8` | `0x1BAD0` | 18 native predicate functions |
| Always-false predicate, operation 0 | `0x800F26DC` | `0x8BE4` | `jr ra; addu v0,zero,zero` |
| Always-true predicate, operation 1 | `0x800F26E4` | `0x8BEC` | returns 1 |
| Icon-colour condition lookup | `0x800ECF64`, `0x800ECF78`, `0x800ECF80` | — | index → script → operation table |
| Actual use-selection condition lookup | `0x800EE6F8`, `0x800EE70C`, `0x800EE714` | — | same condition evaluator before use dispatch |

The condition record is 8 bytes: `{s16 next; u8 fn,a; s16 b,c}`. Evaluate `ops[fn](a,b,c)`; if `next == -1`, return that result; otherwise a true result jumps to record `next` relative to the script base and a false result advances one record. This is control flow, not a simple list of requirements.

Source anchors: [subScreenItemListStep, PAL 0x800ED0C4](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/d0spsub/subScreenItemListStep.c#L192), [subScreenDrawItemIcon, PAL 0x800EB7A8](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/d0spsub/subScreenDrawItemIcon.c#L99), [subScreenCondArea](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/d0spsub/subScreenCondArea.c), [subScreenCondSection](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/d0spsub/subScreenCondSection.c), [subScreenCondPlayerH](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/d0spsub/subScreenCondPlayerH.c). Native JP references are read directly in `item_conditions.txt`; no PAL address shift was assumed.

### Specific retained item links

| Item ID | Meaning | JP condition | Actual acceptance | Research implication |
|---|---|---|---|---|
| `0x3D` / 61 | Iron / iron lump | ID0 → `0x801047F4` | always false | House-5 scene has a surviving material trigger, but normal inventory use never reaches it |
| `0x3E` / 62 | Iron Wheel | ID20 → `0x80104DDC` | area16, section3 **or** section6 | Authentic retail Clock Tower consumer context; not arbitrary use inside the cut Stone town |
| `0x6C` / 108 | Electric Eel | ID22 → `0x80104E24` | area18, section2, player's H coordinate 128..192 inclusive | Shares Black Water's specific use location; a retained menu-level lead, not proof of a working generator transaction |
| `0x6D` / 109 | Black Water | same ID22 | same area18:2 coordinate interval | Keep distinct from Iron Town scene1 starting event0x4C; they are not the same trigger |
| `0x5B` / 91 | Wood for a raft | ID0 | always false | The description preserves intended material, but its menu-to-craftsman use path is not enabled |
| `0x93` / 147 | Coal | ID0 | always false | Textual generator/fuel connection remains; normal item hand-in is not enabled |

The iron-lump script bytes at `0x801047F4` are `FF FF 00 FF 00 00 00 00`: `(-1,0,255,0,0)`. Operation0 is independently verified to return zero in the JP code. The use routine's source only enters the use dispatcher when this result is true. A restoration must explicitly resolve that policy before expecting `GVARS_USE_ITEM_PENDING` to activate the smith.

The exact JP description comes from the embedded item-description WFM at **DSPSUB file `+0xA0B8`**, dialogue **65 = item61+4**. It describes a **lump of iron suitable for making sturdy tools**. The decomp enum `ITEM_IRONHAMMER` is a search aid, not authority for calling this item a hammer. The same bank's dialogue95 describes wood suitable for a raft; dialogue151 describes a stone that burns; dialogue112 describes a shocking source of electricity; dialogue113 describes dangerous black water. These semantic links are text evidence, not missing scene bodies.

Additional always-false items checked here: 57/58 torn map halves, 59 gloves, 64 pipe/valve, 90 letter, 97 shovel, 119/122/123 Funga materials, 137 drum and 140 spear. These names follow the existing research; their **condition ID0** was newly checked on this JP image. This does not mean an item can never be selected through another UI or used automatically in an unexamined path.

The 200 item-condition indices differ from PAL at only item98: PAL condition45 versus JP condition1. The JP pointer table consequently has 45 entries rather than PAL's46. This is a useful versioning check: blindly interpreting 46 JP pointers misreads the first predicate address as a script pointer. Item98 is outside the cut-village conclusion.

Reproduce with `python work/cut_village_research/item_conditions.py`. Its assertions verify the pointer-table location and the false predicate's native bytes; the JSON records full selected scripts, descriptions, operation addresses and the JP/PAL index differences. No dynamic gameplay execution of these item transactions is claimed.

## Native JP loading, music and surviving section wiring

The JP routine at **`0x8001BC7C`** is the analogue of PAL `src/loadCurrentArea.c` (`0x8001C218`). It calls the JP queue routine **`0x8001FFFC`** at `0x8001BD04`. The latter:

- at `0x80020034` reads base-list pointer `BASE[area]` from **`0x80085360`** and at `0x80020038` calls the list walker;
- at `0x8002005C` reads section-pointer-row `SECTIONS[area]` from **`0x800855EC`**, then indexes that row by `section * 4`, and at `0x8002006C` calls the same walker;
- the walker starts at **`0x800200C4`**, directly checks the signed file ID for `-1`, and handles kind `0x90`/`0xB0` families as audio records (`0x800200D8..0x8002010C`).

These names are semantic identifications from the code and tables; unlike `setAreaModeFromSection`, upstream does not supply all of them as named JP matching symbols. The raw instructions are retained in `connections_probe.txt`; `jp_load_audit.py` reads the actual table values independently of virtual LDAR section numbering.

| Town | JP base-list pointer | Native s0 pointer cell | Native s0 list | Exact contents |
|---|---:|---:|---:|---|
| AREA11 Lumberjack Town | `0x800818DC` | `0x800854DC` | `0x800819E0` | `FF FF` followed by 18 zero bytes |
| AREA16 Stonestown | `0x80083C7C` | `0x8008558C` | `0x80083D6C` | same 20-byte terminator |
| AREA17 Iron Town | `0x800842BC` | `0x800855A8` | `0x800843C0` | same 20-byte terminator |
| AREA18 reunited-town draft | `0x800849EC` | `0x800855D4` | `0x80084ADC` | same 20-byte terminator |

The native table also distinguishes other empty slots that a heuristic inventory can omit: AREA11 s3/s4, AREA16 s1/s2, and AREA17 s6..s10. These are independent terminator records, not evidence of hidden data behind a zero pointer.

### The JP BGM detail which upstream explicitly left untraced

Upstream CIVILIZATION.md, "Music of the cut sections", ends its JP paragraph with "We did not trace the JP set table." Its preceding PAL table is accurate for PAL, but the corresponding JP loading mechanism is different.

All four JP common/base lists above have only SEQ kinds **`0xB2` and `0xB3`** for the short shared cues; none contains a kind-`0x93` WVD or main kind-`0xB0` SEQ. Each cut s0 list then immediately terminates. The working neighboring sections load their WVD and main music directly:

| Actual JP section | WVD load-record address and source | Main SEQ load-record address and packed source range | Relation to PAL |
|---|---|---|---|
| 11:1 | `0x80081A44`: `AREA11/SND0110.WVD`, 71,500 B | `0x80081B98`: `AREA11/D104.GAM` unpacked `+0x28FD8`, 8,488 B | byte-identical to `SOUND/S_AR110.SEQ`, SHA-1 `26fc113d6413d8e5e85a5f84cba01478d03a1242` |
| 16:3 | `0x80083DE4`: `AREA16/SND0160.WVD`, 186,564 B | `0x80083E98`: `AREA16/D305.GAM` unpacked `+0x2828`, 4,224 B | PAL `SOUND/S_AR160.SEQ` 4,223 B followed by one zero byte |
| 17:1 | `0x800843FC`: `AREA17/SND0170.WVD`, 216,372 B | `0x8008449C`: `AREA17/D103.GAM` unpacked `+0x6EC`, 6,464 B | PAL `SOUND/S_AR170.SEQ` 6,462 B followed by two zero bytes |
| 18:1 | `0x80084B54`: `AREA18/SND0181.WVD`, 208,260 B | `0x80084C30`: `AREA18/D104.GAM` unpacked `+0x9CF8`, 8,880 B | PAL `SOUND/S_AR181.SEQ` 8,879 B followed by one zero byte |
| 18:2 | `0x80084CA8`: `AREA18/SND0182.WVD`, 192,708 B | `0x80084D5C`: `AREA18/D203.GAM` unpacked `+0x59D0`, 2,784 B | byte-identical to `SOUND/S_AR1802.SEQ`, SHA-1 `764c3996f0f68def720542356a54e66ddd21ebc4` |

Offsets into `.GAM` are **decompressed payload offsets**, not compressed on-disc byte offsets. Kind/slot records are `0x93` slot `0x80` and `0xB0` slot `0xFF` in these section lists. Every byte of the PAL-length SEQ prefix was compared, not just the size. This gives authentic existing theme candidates for reconstruction, but **does not establish which theme the missing town itself originally used**. Runtime behavior after forcing entry to an empty s0 was not emulated; no claim is made about whether prior audio remains, stops, or becomes invalid.

### Surviving mode, bounds, controllers and entrance reuse

`setAreaModeFromSection` is an upstream named JP match at **`0x8001BD28`** (PAL `src/setAreaModeFromSection.c`, `0x8001C314`). The actual JP area-mode pointer table is **`0x80071644`** (`lw` at `0x8001BD4C`). Each of these four s0 entries is still **mode 5**, as are the working top-down sections.

`loadSectionBounds` is an upstream JP match at **`0x80022468`** (PAL source `src/loadSectionBounds.c`, `0x80021A94`). Its actual per-area pointer table is **`0x80074A60`** (`lw` at `0x80022484`), and it copies four 16-bit words into object fields `+0x2C..+0x32`. These section-0 bounds survive:

| Area | Bound-record address | Four signed words | Section-object list address | NPC-set controller record |
|---|---:|---|---:|---|
| 11 | `0x80074940` | `(33, 417, 153, 512)` | `0x800789B8` | `(4, 13, 0, 0)` |
| 16 | `0x800749B8` | `(33, 192, 153, 476)` | `0x800789D8` | `(4, 14, 0, 0)` |
| 17 | `0x800749F0` | `(33, 416, 153, 464)` | `0x80078A28` | `(4, 15, 0, 0)` |
| 18 | `0x80074A30` | `(33, 672, 153, 512)` | `0x80078A74` | `(4, 16, 0, 0)` |

Every listed controller sequence begins `(2,0,0,1), (1,0,0,0)` before the shown NPC-set record. This verifies the mode/controller side of the intended connection directly in JP, separately from the empty load lists. Treat the bounds as authentic retained framing constraints; they do not by themselves reveal background dimensions or collision cells.

The JP entrance pointer table is **`0x80075328`**. The cut-town records are:

| Section | Entry-list address | All entries before next distinct entry-list pointer (`x,y,z,flags`) | Reuse |
|---|---:|---|---|
| 11:0 | `0x80075028` | `(20,-52,0,0)`, `(280,-52,90,0)` | same pointer as 11:1 and 11:3 |
| 16:0 | `0x80075090` | `(160,-18,0,0)`, `(160,-48,0,0)` | same pointer as 16:1 and 16:4 |
| 17:0 | `0x800750B8` | `(160,-18,0,0)`, `(160,-58,0,0)` | same pointer as 17:1 and 17:6 |
| 18:0 | `0x80075100` | `(300,300,0,0)` | unique among the compared sections |

Entry-list length here is bounded by the next distinct pointer, not an explicit in-data count. The raw sharing is confirmed; calling these three lists temporary/reused side-scroller entrances is an inference. They do not independently preserve the intended three top-down gate arrival points. `loadSpawnPosition` JP `0x800220F0` and `initPlayerAtSpawn` JP `0x8002222C` explain how these 8-byte entries are consumed (shared sources `src/loadSpawnPosition.c` and `src/initPlayerAtSpawn.c`).

## Orphan X19: useful dead build, but no new village animation scripts

Upstream CUT_CONTENT.md line 53 explicitly leaves comparison of X019 against X002 open. This check addresses the JP retail copies.

- `SYSTEM/X19.BIN` and `AREA19/X19.BIN`: each **179,944 B**, SHA-1 **`63bc65d813749580612d1f9907bde52f7eef0c39`**. Neither occurs in the executable file-link catalog; neither has any parsed load-record reference.
- `SYSTEM/X02.BIN` and `AREA19/X02.BIN`: each **208,756 B**, SHA-1 **`ef7bef439d5dd84f9825b4d894d0cc47bfc7626e`**. SYSTEM catalog ID 56, AREA19 catalog ID 1037. The AREA19 copy has a real section load-record reference.
- The first **`0x2B680` bytes** of X19 are the repeated JP shared overlay prefix, as upstream `docs/JP.md` / `config/slps01144/x19.yaml` describe.

The entire remaining **2,152 bytes** are accounted for as follows:

| X19 file offset | JP virtual address | Size | Content / upstream source |
|---|---:|---:|---|
| `0x2B680` | `0x80115178` | 4 | area ID word |
| `0x2B684` | `0x8011517C` | 348 | sole area-specific function, matched to PAL X019 `updateAreaScroll` at `0x80115EA8`, `src/x019/updateAreaScroll.c` |
| `0x2B7E0` | `0x801152D8` | 324 | two animation pointer tables, 2 + 79 entries; PAL source `src/data/x019/D_80116004.c` starts with `ptrs_80116004[2]` and `ptrs_8011600C[79]` |
| `0x2B924` | `0x8011541C` | 1,476 | animation scripts through EOF (`0x801159E0`) |

The sole function is a reduced side-scrolling scroll/exit controller. Its PAL C initializes `cameraModeHandler6B`, dispatches through `D_80079AD0[o->subtype]`, arms exit 0 at player horizontal coordinate `<30` and Y `>=-59`, and arms exit 1 at Z `90`, X `<17`, Y `>=-77`; its later step invokes `cameraEventScrollHandler`. Compare **`src/x002/updateAreaScroll.c`**, PAL `0x80116358`: that has the expanded selected-section switch and additional section-specific exit checks. It is not a top-down resident handler. The original intention of the X19 fork remains uncertain; do not call it the missing Civilization-town renderer.

**Animation payload comparison:** the 81 pointer-table entries name 73 distinct script starts. Sort those starts, bound each block by the next start/EOF, and compare every 4-byte-aligned candidate block in X02. Decode each block as 8-byte animation records, with an additional 4-byte jump payload only when `durFlags & 0x4000` is set. Only these structurally identified jump addresses are normalized relative to each candidate start; all non-pointer words remain exact. There are exactly **7** jump payloads. The initial broader address-range normalization was separately checked and selected exactly those same 7 fields, with no non-pointer words included. **All 73 bounded blocks, totaling all 1,476 bytes, match X02.** This includes content following the first STOP within a block; the first version of the probe compared only first-terminal sequences, and the final probe adds the exhaustive bounded-block comparison. The pointer-table arrangement as one contiguous 1,800-byte block does not match X02, so do not describe the entire X19 tail as byte-identical to X02. The result is narrower and useful: no unique script payload was recovered there.


## Physical disc residue and uncatalogued copies

This was checked independently of the decomp's file lists, so that “not in a load list” would not hide a recoverable file or sector.

### Unallocated sectors, file slack and dummy data

The ISO has 1,076 files and 28 directory entries. Sector ownership included the system area, volume descriptors, both endian path tables, directory extents and all file extents. All sectors through LBA122906 are allocated. The **only** unallocated run is **LBA122907..123056**, 150 sectors / 307,200 ISO payload bytes, all zero. No GAM, WFM, TIM8, WSS or EXE signature occurs there.

All examined unused bytes after the final byte of a Form-1 file/directory's final ISO sector were zero. Form-2 stream tails were excluded from the file-slack test because they have a different payload contract. The allocated filler `ZZZ/DUMMY.DAT` is **27,648,000 zero bytes**, SHA-1 `8971df6ec5aba765699da263a630d68db2527bb8`.

**Result:** no deleted/unlisted asset can be recovered from these zero-filled regions of this particular dump. This does not search for unknown embedded structure inside every allocated file, nor does it say anything about other disc masters.

### The apparently unused CLUT files are one duplicate payload

The JP executable's file-link catalog begins at **SLPS file `+0x62DF4`** and has 1,045 resolved links. Comparing it with the ISO exposed these uncatalogued village CLUT files:

| Area | Uncatalogued files |
|---|---|
| 11 | `CLUT01.GAM`, `CLUT04.GAM`, `CLUT05.GAM` |
| 16 | `CLUT01.GAM`, `CLUT02.GAM`, `CLUT03.GAM` |
| 17 | `CLUT01.GAM`, `CLUT07.GAM` through `CLUT11.GAM` |
| 18 | `CLUT01.GAM` |

All **13** are 4,078 bytes compressed and expand to **the same 16,384-byte payload**, SHA-1 **`dfa19034c63f7a8f890c27808860b5cc81e3e584`**, with 3,143 nonzero bytes. This establishes one shared palette block, not 13 independent lost-town palette sets. Its entries were not declared visually useless: a particular row could still be compared to a future identified sprite. It supplies no new town-specific variation by filename alone.

The AREA11/16/17/18 INFO2 copies are also uncatalogued. Together with SYSTEM/AREA05/08/19 they form **eight byte-identical copies**, all SHA-1 `15ea8894a028cdabdda577b32ddfd281e023f51b`; the village-directory copies contain no alternative cut-town code or script bytes. Orphan X19 is separately accounted for above.

Reproduce: `python work/cut_village_research/disc_residue_scan.py`. `disc_residue.json` records all uncatalogued files, their extents, sizes, decompressed hashes and nonzero counts, plus the complete gap/slack and target-fingerprint inventory. No ROM data is copied into this report.

## What should be reconstructed next, and what evidence is still missing

### Highest-value next steps

1. **Correct the research bindings before interpreting text.** Use the dispatch-derived JP handlers `0x800F3000`, `0x800F41FC`, `0x800F5488`. Replace size-only identification in a future editor change with the layer2/area/actor/talk chain or a hash-scoped verified mapping. Re-extract dialogue with groups from the actual village bank. This report documents the defect; it does not patch the editor.
2. **Teach the decomp diagnostic to read both resident MAIN and the current overlay.** The external subtype4 table is a positive control: all24 scripts must decode with the exact sequences below. An out-of-overlay pointer should become “external, unresolved” until checked, not “missing”.
3. **Search for sprite parts using the new constraints.** Iron subtype4 uses SPR slot11, page offset8, box8/16/8/16 and frames148..202. A usable replacement bank needs at least203 frame entries. The surviving 431-frame generic bank in JP `AREA02/D006.GAM+0x1E80`, `AREA08/D003.GAM+0xEE8` and `AREA19/D008.GAM+0x137C` is a candidate to compare, **not an identified original table**. Matching numeric frame IDs is insufficient: require UV, silhouette, palette, part-layout and facing/animation agreement.
4. **Model Iron Town topology from code before drawing it.** Preserve six lift stops, the dummy stop slot, two passage pairs, exact room rectangles and exit rectangles. The hidden passages stay within the same section. Keep alternate visual interpretations editable.
5. **Test the gear transaction as an isolated state machine.** First resolve the blocked inventory condition and identify the intended smith actor pointer. Then verify dialogue, player lock, wait, wheel reward and event0x62 completion, followed by the retail X016 consumer. Record any added material consumption or one-shot guard as authored behavior, since the surviving scene does not supply them.
6. **Keep incomplete scene work visible.** Wood's empty state1 and Iron's reset-only steps5–7 cannot be repaired by loading an SPR. Any added raft/bomb-making sequence must be documented as a reconstruction, even when its dialogue and requests are original.
7. **Use the native JP load architecture.** Supply complete map/SPR/CLUT/WPP resources and intentional music for the empty s0 lists. Reused entrance pointers are not proof of the original town arrival point. The mode, bounds and controller records provide authentic constraints without supplying missing graphics.

### Useful JP breakpoint/watchpoint ledger

These are investigation targets for a future emulator run, not evidence that such a run was performed here.

| Target | Address | Observe |
|---|---:|---|
| Layer2 type0x30 area dispatcher | `0x8003CA98` | area → actual actor handler |
| Wood / Stone / Iron normal dialogue | `0x800F3000` / `0x800F41FC` / `0x800F5488` | actor+0xBA, group/line calls and switch case |
| Iron actor init | `0x800F64AC` | subtype4 loads script from MAIN; SPR slot11 must be valid |
| Animation advance | `0x80020E38` | decoded frame, timer/control and script pointer; named in pinned JP symbols |
| Wood set controller | `0x800FC470` | idle state1; no CFA9 consumer recovered |
| Iron set pick-step | `0x800FE9F4` | room5, pending-use/item ID, scene override priority |
| Iron wheel scene | `0x800FE7CC` | unset actor register/pointer, wheel grant and event completion |
| Iron set dispatch / reset stub | `0x800FEC78` / `0x800FED64` | scene5/6/7 requests reach reset-only body |
| Iron trigger spots | `0x800FE0EC` | six stops and four passage trigger rectangles |
| Pending item / item ID | `0x8009E4E8` / `0x8009E4E9` | menu hand-in reaching INFO2 |
| Current top-down room | `0x800A7BE3` | room5 is required for iron lump |
| Machine event0x4D | `0x8009E999` | Wood relocation and shared phase |
| Shared Wood/Iron dialogue phase | `0x8009EB4D` | sampled by spawners; not continuously refreshed |
| Wood dialogue handshake | `0x8009EB51` | case1 writes it; no controller consumer recovered |
| Iron bomb handshakes | `0x8009EB4E`, `0x8009EB53` | requests for incomplete scene steps |
| Native JP load walker | `0x800200C4` | real section records, including WVD/B0 audio |
| Inventory actual-use conditions | `0x800EE6F8` | rejection occurs before pending-use request |

### Unresolved questions, with a specific way to settle each

| Missing link | Current boundary | Next discriminating evidence |
|---|---|---|
| Original Iron subtype4 pixels / SPR parts | Scripts retained; original rectangles/page not identified | A bank/page pair matching the55 recovered frame IDs across direction and motion, with a defensible load/palette chain |
| Indoor subtype4 actor at (223,0), dlg4 | Placement and scripts survive; normal dialogue returns0 | A surviving scene caller/actor reference or independent pre-release evidence; do not infer identity from the outdoor actor sharing subtype |
| Wood raft-making transaction | Text, material description, transient flag and orphan helper survive; controller does not implement it | Caller/scene body in another revision, or explicitly authored reconstruction |
| Iron bomb-making scene | Dialogue and three handshakes survive; steps5–7 reset | Another build's implementation or a labelled replacement sequence |
| Original map/room SPR tables | No recovered payload; preserved reload pages are partial | Structurally validated table with correct frame ranges/parts and a load reference or unambiguous matching visual evidence |
| Cut-town BGM choice | No explicit main BGM in JP empty s0 lists | Original section data from another build or a direct historical source; adjacent retail tracks are candidates only |
| Area18 reunited town | Viewer-like actor handler and placeholder controller/entrances | A genuine completed controller/dialogue caller in another build; current epilogue text does not prove one exists |
| X19 historical role | Reduced dead side-scroller controller, shared animation payload | Version history/prototype comparison explaining why this overlay fork was retained |

## Reproduction index and validation boundary

All supporting scratch evidence is under `work/cut_village_research/`, ignored by Git. The **single durable deliverable is this file**. Essential addresses, hashes, tables, sequences and limitations are embedded here, so the findings do not require the scratch JSON to be understood.

Run from `C:\Users\Patryk\PycharmProjects\TombaEdit`:

```powershell
python work/cut_village_research/external_anims.py
python work/cut_village_research/logic_dispatch.py
python work/cut_village_research/logic_confirm.py
python work/cut_village_research/logic_orphans.py
python work/cut_village_research/logic_paths.py
python work/cut_village_research/logic_spots.py
python work/cut_village_research/item_conditions.py
python work/cut_village_research/jp_load_audit.py
python work/cut_village_research/x19_compare.py
python work/cut_village_research/disc_residue_scan.py
```

| Output | Purpose |
|---|---|
| `external_anims.json` | all24 scripts, every 8-byte step, native pointers, both builds |
| `assets_probe.txt` | definition bytes, reload records, resource sizes/hashes |
| `logic_dispatch.txt`, `logic_confirm.txt` | native actor chain, true switches, stubs and wheel-scene instructions |
| `logic_orphans.txt`, `logic_paths.txt`, `logic_spots.txt` | bounded xrefs, passage code and exact trigger coordinates |
| `item_conditions.json`, `item_conditions.txt` | native menu condition tables, selected scripts and descriptions |
| `jp_load_audit.json` | native JP section pointer cells and full load records, bounds, controllers, entrances |
| `x19_block_matches.json` | all73 bounded X19 script blocks and matching X02 locations |
| `disc_residue.json` | whole-image fingerprints, gaps, file slack, dummy and uncatalogued file inventory |

The analysis checked native bytes and static control flow. It did not run a restored town on a console/emulator, validate every possible state, reconstruct missing art, audit every sound call, or prove the absence of arbitrary encoded data inside all allocated files. PAL-only cross-overlay functions are marked accordingly. A source function that matches the retail binary can still contain original incomplete/unsafe logic; matching percentage is not restored playability.

### Pinned source entry points

- [Cut-town research baseline](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/docs/CIVILIZATION.md), [cut-content inventory](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/docs/CUT_CONTENT.md), [JP build/address notes](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/docs/JP.md).
- [INFO2 sources](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2), [definition/animation diagnostic](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/tools/topdown.py#L392), [animation record interpreter](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/AnimAdvance.c#L9), [sprite renderer](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/drawObjectSprite.c#L87).
- [Wood spawn](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/spawnNpcSet0D.c#L78), [Wood controller](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/updateNpcSet0D.c), [Wood orphan helper](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/topdownA11ActorDialogueBank2.c).
- [Iron scene picker](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/npcSet0FPickStep.c), [wheel scene](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/npcSet0FSceneStep4.c), [Iron controller](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/updateNpcSet0F.c), [trigger spots](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/i0nfo2/npcSet0FCheckTriggerSpots.c).
- [Clock Tower gear talk](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/x016/brokenStoneGearsTalk.c), [gear-use trigger](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/x016/checkStoneGearsTrigger.c), [repair/consumption](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/x016/brokenStoneGearsRepair.c).
- [JP X19 split](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/config/slps01144/x19.yaml), [X19 scroll controller](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/x019/updateAreaScroll.c), [X02 scroll controller](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/x002/updateAreaScroll.c), [X19 data tables](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/data/x019/D_80116004.c).

Every source link above is pinned to the investigated revision. Semantic names assist navigation; the supplied-image hashes and explicit native JP dispatch/table checks establish which build the new addresses describe.


## Community civ_towns spreadsheet cross-check — 1 November 2026

Source: [civ_towns community research sheet](https://docs.google.com/spreadsheets/d/14QfyM5j8V3zQocUOMLXNa9FhJ_M4YUyJIGxFGFb5G_4/edit), read-only XLSX export on 2026-11-01. The transcribed snapshot is `formats/level/civ_towns_reference.json`; its metadata records the exact export SHA256. The editor Research window exposes all four source tabs, including confidence, source notes, palette aliases and raw 16-word palettes. Blank identification fields remain blank. This community snapshot is separate from the pinned decomp documentation and does not assert that upstream independently verified community claims.

The sheet has 108 palette records, 51 resident records and 56 prop records. Against the supplied JP retail disc, 82 palette records match all sixteen words at the stated file/row; 26 differ. By area, matches are 45/55 (11), 6/10 (16), 11/17 (17), 20/26 (18). Do not overwrite JP palettes with these source values or assume the sheet is JP-specific. Example: `Palettes!AA67`, Iron Town CLUT03 row 1, starts `0000 0C63 7FFF 56B5`; JP retail starts `0000 0421 7FFF 5EF7`. The cause of the differences has not been established here. The Research table calculates status and native words against the currently opened disc. Named community claims appear in palette selectors only on an exact 16-word match, preserving the sheet confidence rather than promoting it to verified identity.

Useful leads include purple-dress/red-shirt FMV palette matches (`Palettes` rows 62/64, 73/76, 94/98), the unverified miner identification, and reunited-town wide-hat/boy hypotheses (`Residents` rows 46/49/50/51). These do not recover the original subtype-to-sprite or subtype-to-CLUT tables. The Palettes tab concerns 16-colour residents, not the missing 256-colour building palettes. Prop P# markers and Iron passage scene numbers are distinct namespaces even where their numbers overlap. Patrol boxes transcribed in the sheet may be relative (notably Stone); use native decoded movement for actual placement.

### BUNMEI and BUNMEI2 colour evidence

The supplied JP disc has BUNMEI (227 decoded frames, 320x224, LBA 43084) and BUNMEI2 (157 frames, 320x224, LBA 45356). These are MDEC video streams: decoded colours can guide reconstruction but are not original indexed CLUT words. BUNMEI contains the Wood/Stone/Iron town pans and later reunited exterior; BUNMEI2 shows machine/clock interiors and a later building pan. Contact sheets and decoded samples are retained under `work/cut_village_research/movie_cluts/`. No unverified BUNMEI2 building-pixel registration is applied to the default helper palettes.

BUNMEI ISO payload SHA256: `c4873c05dc101d72675215e608beca2a6adbaef95834552009d6d3714920ae8e` (same payload in the compared PAL disc). JP BUNMEI2 payload: `fc107dcb1480354713a87afe71b91fac3b86986a5dd4b52be2fe4a6b85f0647c`; compared PAL payload: `e4031833d099a74f0579ba0d50aedfed71ae9455e8b0001dc7e666aecb832010`. The demuxed video also differs; PAL BUNMEI2 must not be silently substituted for JP evidence. Existing Wood/Stone/Iron helper defaults remain based on exact index-pattern correspondences with the supplied restored ground-truth images. Reunited town still lacks sufficient matched coverage for a default building helper.
