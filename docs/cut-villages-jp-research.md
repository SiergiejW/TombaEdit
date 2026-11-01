# Cut villages in Ore! Tomba: JP retail evidence and reconstruction leads

Research date: **31 October 2026**. Target: the supplied `rom/Ore! Tomba (Japan).cue` and its BIN. This is a research report, not a playable restoration. No game code, editor code, save, or disc image was modified.

**Research beyond the cut villages, 1 November 2026:** the separate [JP retail unused-content report](jp-retail-unused-research.md) adds the Jungle eel's surviving graphics/script and missing item binding, JP/PAL shock controls, stat-item wording in two placeholder slots, material descriptor routes and the shared drum sprite. It also tracks the remaining supplied community leads without treating them all as confirmed unused.

**Second orphan-data audit, 1 November 2026:** see [Deeper orphan-data audit](#deeper-orphan-data-audit--1-november-2026) for the newly enumerated Wood scenery scripts, Iron's unplaced fourth scenery definition, surviving scenery CLUT destinations, and controls against mistaking inline duplicates or progress-selected animations for lost content. The original investigation's no-edit statement above applies to that investigation; subsequent editor presentation changes are described separately.

**Third JP-only audit, 1 November 2026:** see [Resident actions and an unbound animation template](#third-jp-orphan-data-audit--resident-actions-and-an-unbound-animation-template). This adds a 37-frame Wood animation template without its own resident definition, three unselected Wood action scripts, two unselected Iron action loops, and the native selector/terminal-mode checks that distinguish them from the already documented animation inventory.

**Fourth JP-only audit, 1 November 2026:** see [Dormant state, rendering consumers and reused hints](#fourth-jp-audit--dormant-state-rendering-consumers-and-reused-hints). This finds Stone P6's unchanged sprite pointer during its requested state change, an unseeded phase candidate, the craftsman scene's wrong message anchor, and the meaning of prop kind 0/1/2. It also corrects this report's earlier raft attribution of Wood's orphan hint helper.

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
| Wood actor 1 is relocated conditionally; a dialogue handshake has no scene consumer | JP native code | Story-dependent layout and an unconsumed hint handshake; its text also has a retail X11 counterpart |
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

## Lumberjack Town has a conditional resident position and an unconsumed hint handshake

PAL `spawnNpcSet0D` `0x800FB054` (`src/i0nfo2/spawnNpcSet0D.c:78–79`) contains:

```
if (D_8009CDF1 == 0) SCRIPT_OBJECTS[1]->x = -200;
```

JP equivalent starts `0x800FC198`. The test/override survives at `0x800FC32C–0x800FC34C`: event/state byte **`0x8009E999`** is read and, when zero, actor 1's x word is replaced by `-200`. This byte is event `0x4D` (Civilization Machine), because JP event-byte base is `0x8009E94C`. Raw actor 1 is at `(12,256)` in room 1. A reconstruction that merely draws placements misses this initial relocation. The code only changes x; it does not delete the actor or change its room.

The same spawner computes shared dialogue phase 0/1/2 from event `0x66` (`0x8009E9B2`, PAL `D_8009CE0A`) and completion of event `0x4D`; the destination is JP **`0x8009EB4D`** (PAL `D_8009CFA5`). These phases link the Wood and Iron towns to the machine/power storyline. They are sampled at spawn; the NPC dialogue does not recompute them continuously.

True Wood dialogue case 1 (`topdownA11ActorOpenDialogue.c:23–29`, JP `0x800F3080…`) writes transient flag JP **`0x8009EB51`** (PAL `D_8009CFA9`) to 1 or 2 depending on event `0x4F` (`D_8009CDF3` / JP `0x8009E99B`). It returns no message.

The scene controller **`updateNpcSet0D` PAL `0x800FB32C`, JP `0x800FC470` is empty in its live state 1** (`src/i0nfo2/updateNpcSet0D.c:14–15`). It spawns residents, idles, and can be freed. It does not consume this flag. This flag and the helper below are not evidence of a raft-making transaction: their actual messages concern the generator and the Watchtower elevator, as verified in the fourth audit below.

An orphan helper survives: `topdownA11ActorDialogueBank2`, PAL `0x800F1BAC`, JP **`0x800F2F24`**, length `0xDC`. It can show `(2,4)`, then `(2,5)`, and set `o->state=2, o->wac=0x4F`, which would ask the general talk cleanup to start event 0x4F. However there are **zero direct JAL callers and zero 32-bit pointer references to this entry** in JP INFO2 and MAIN0. Source search likewise finds its definition but no named call. This is bounded static evidence, not a proof against every imaginable computed call; the normal Wood actor chain never calls it.

The helper preserves a top-down implementation of a hint/event interaction that also survives in retail X11; its unused body does not make the message itself globally unused. It does not establish that Wood's surviving controller can run the corresponding interaction. The Green Fortune Teller's actor case 11 is also outside the actual 0–10 switch on JP, just as on PAL. His recovered text needs an authored caller.

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
6. **Keep incomplete scene work visible.** Wood's empty state1 and Iron's reset-only steps5–7 cannot be repaired by loading an SPR. Any added town interaction or bomb-making sequence must be documented as a reconstruction. In particular, do not turn Wood's generator/Watchtower hint handshake into an asserted original raft scene.
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
| Wood raft-making transaction | Raft dialogue and the wood material description survive; no transaction established. The previously associated flag/helper actually concerns a generator/Watchtower hint | A genuine raft caller/scene body in another revision, or explicitly authored reconstruction |
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


### Reunited-town proposed building palette

At the user's request, Group 86 now defaults to a warm stone/timber artistic palette proposal. All 255 nontransparent slots are estimated, with no claim of recovered FMV colours. The proposal retains the index-order brightness structure with RGB `(min(255, 1.10*i+6), min(255, .92*i+3), .72*i)`, quantized to RGB555; slot 0 stays transparent. The reference-matching attempt against the other coloured town sheets produced no additional exact matches, so their palettes were not transferred. Grayscale remains selectable and existing saved assignments remain intact. The proposal is bundled in `building_helper_cluts.json`, scoped to the exact Group 86 pixel hash, and clearly labelled PROPOSED CLUT in the editor. Earlier statements that Group 86 has no default colour helper describe the state before this artistic proposal.

## Deeper orphan-data audit — 1 November 2026

This pass follows **placement → definition → animation-pointer slot → script**, and separately checks code references. It extends the existing positions/text/route findings; it does not claim to have recovered missing sprite rectangles, original palettes or a playable section. The supplied JP executable and INFO2 were rechecked against the SHA-1 values in the target-identity table. All offsets below are hexadecimal offsets in the physical, uncompressed `SYSTEM/INFO2.BIN`, unless another file is named. Addresses are JP RAM addresses; one-based **P#** means the editor prop number, not an Iron passage scene number.

Upstream was checked live at **`44e814a6268f294f889ee77f5aad319f88e82a50`**. The thirteen commits after the previous `b8fe30a` checkpoint concern port controls, panels, rendering and launcher behavior. Comparing those revisions changes neither `src/i0nfo2/`, `notes/data_names_i0nfo2.csv` nor `docs/CIVILIZATION.md`. The bundled nine-file reference snapshot remains pinned to its recorded revision; this section's newer source check is not a claim that the bundle was silently updated. The working upstream tree was not reset or switched.

### A. Wood retains ten unselected scenery slots, including eight multi-frame/pose scripts

The Wood scenery definitions are at **`80100198` / INFO2+`166A0`** and **`801001A4` / +`166AC`**. Both select **SPR slot 13**, with relative page offsets **2** and **8**, and point to **`801061C4` / +`1C6CC`**. This is the scenery namespace, not the residents' SPR slot 11.

The pointer window has **24 entries**, ending at `80106224`, the next actor definition's animation-table start. It is not justified by reading an arbitrary 24 pointers beyond an unknown boundary: the definition references and the adjacent table establish this boundary. The 14 Wood prop records select scripts **0–11, 14, 15**. The surviving Wood scenery handler initializes from the selected record and handles room visibility; it does not select the other entries. The Wood set controller's unfinished idle scene was already established above.

Consequently, **slots 12, 13 and 16–23 have no selection in those preserved Wood lists and handlers**. Slots 12/13 are single held frames 12/13. The eight higher slots retain **26 distinct frame IDs, 141–166**, and **256 contiguous bytes of script records** at `801069B0..80106AAF`. Their eight pointer cells occupy `80106204..80106220`. Every one of these ten script starts has exactly one aligned literal pointer reference in the audited MAIN+INFO2 regions: its scenery-table cell. No direct `J`/`JAL` into these script starts was found there.

| Slot | Pointer cell | Script address | INFO2 script offset | Frame sequence | Tick fields in the same order |
|---:|---|---|---|---|---|
|12|`801061F4`|`801063F0`|`1C8F8`|12|60, hold|
|13|`801061F8`|`801063F8`|`1C900`|13|60, hold|
|16|`80106204`|`801069B0`|`1CEB8`|141|60, hold|
|17|`80106208`|`801069B8`|`1CEC0`|142, 143, 144, 145, 146, 147|8, 8, 8, 8, 8, 8|
|18|`8010620C`|`801069E8`|`1CEF0`|148, 149, 150, 149, 148|8, 12, 12, 12, 12|
|19|`80106210`|`80106A10`|`1CF18`|151, 152, 153, 152|8, 1, 10, 4|
|20|`80106214`|`80106A30`|`1CF38`|154|60, hold|
|21|`80106218`|`80106A38`|`1CF40`|155, 156, 157, 158, 159, 160|8, 8, 8, 8, 8, 8|
|22|`8010621C`|`80106A68`|`1CF70`|161, 162, 163, 162, 163|8, 12, 12, 12, 12|
|23|`80106220`|`80106A90`|`1CF98`|164, 165, 166, 165|6, 2, 5, 3|

All steps have box/argument fields zero. Each sequence ends with control bit `8000` (hold final frame); the tick fields are the low 14 bits, not a claim that a held frame disappears after that duration. None of these ten sequences uses a jump payload. Slot 22's final frame really is **163**, not 161; do not symmetrize the retained sequence during reconstruction.

**Cross-build control:** the PAL scenery table is `8010751C`. The corresponding ten PAL script starts are `80107748`, `80107750`, `80107D08`, `80107D10`, `80107D40`, `80107D68`, `80107D88`, `80107D90`, `80107DC0`, `80107DE8`. Every complete bounded sequence compares byte-for-byte with JP, including box, argument and control words. Thus these are original retained scripts in both builds, not an editor-generated animation or JP-only leftover.

**What this permits:** an SPR candidate for Wood scenery can be checked against these additional frame IDs and original timings. A future editor may expose them as unplaced scenery-animation candidates. **What it does not permit:** assigning them to the raft craftsman, windmill, a particular house or an item without the missing SPR parts or independent visual evidence. Identical frame numbers in resident SPR slot 11 and scenery SPR slot 13 do not identify the same drawing. A generic/computed assignment outside the audited paths is not ruled out; “unselected” here is deliberately narrower than proven unreachable.

Source anchors: [Wood scenery handler](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA11SceneryHandler.c), [Wood spawner](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/spawnNpcSet0D.c), [definition names](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/notes/data_names_i0nfo2.csv).

### B. Iron's fourth scenery definition is retained but unplaced

The decomp diagnostic's `DEFS` inventory lists **three** Iron scenery definitions. The native table preserves a fourth 12-byte record before the next area's table:

| Subtype | JP definition | INFO2 offset | Relative page offset | SPR slot | Animation table | Placed Iron props |
|---:|---|---|---:|---:|---|---|
|0|`800FFF48`|`16450`|2|13|`80106F50`|P1–P5|
|1|`800FFF54`|`1645C`|4|13|`80106F50`|P6–P13|
|2|`800FFF60`|`16468`|6|13|`80106F50`|P14–P35|
|**3**|**`800FFF6C`**|**`16474`**|**8**|**13**|**`80106F50`**|**none**|

The fourth record decodes as `{w1e=8, pad=0, spad=13, pad=0, anims=80106F50}`. It ends exactly at `800FFF78`, the next area's definition table. The live Iron scenery init/handler computes `base + subtype*12`; it does not use a hard-coded three-entry limit. All 35 preserved Iron records have subtypes 0, 1 or 2, and the audited scenery updater does not change subtype. This makes subtype 3 a **retained, unplaced definition candidate**, not a newly found resident or a new set of 24 script payloads.

PAL retains the same fourth record at **`800FEE28` / I0NFO2+`16E00`**, pointing to its Iron scenery table `801082A8`, with the same page offset/slot. This is also an inventory-count omission in `tools/topdown.py` / `tools/civ_i0nfo2_diff.py`, not proof that the upstream runtime rejects subtype 3.

**Restoration implication:** retain a fourth selectable scenery definition and its page offset in research tools; do not assume that only three original Iron scenery page bindings existed. The missing SPR slot-13 table still determines UVs, sprite dimensions, part tpages and frame CLUTs/overrides. Page offset 8 alone cannot establish an original building-part crop or show which, if any, missing prop used it.

Source anchors: [Iron scenery init](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA17SceneryInit.c), [Iron scenery handler](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA17SceneryHandler.c), [diagnostic inventory](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/tools/topdown.py).

### C. The intended scenery CLUT destinations survive even where the colours do not

The scenery handlers set **object+0D = 1**, enabling the object's palette override, and put a CLUT identifier in **object+08**. The draw routine uses that override instead of the SPR part's CLUT when enabled. Therefore the absent original sprite table does not erase every palette-related connection:

| Native JP handler | Palette constant instruction(s) | Selected CLUT | VRAM palette origin |
|---|---|---|---|
|Wood `800F80D4` / +`E5DC`, indoor room|`800F81D0` / +`E6D8`|`7F48`|x128, y509|
|Wood, outdoor room 0|`800F81E4` / +`E6EC`|`7FC8`|x128, y511|
|Stone `800F1F84` / +`848C`, both room branches|`800F2080`, `800F2094` / +`8588`, +`859C`|`7FC8`|x128, y511|
|Iron `800F25E4` / +`8AEC`, both room branches|`800F26E0`, `800F26F4` / +`8BE8`, +`8BFC`|`7FC8`|x128, y511|

The CLUT origin follows `(id & 63)*16, (id >> 6) & 511`, also used by TombaEdit's `psx/graphics.py`. An 8-bpp part requires 256 words beginning at that origin. This says **where the renderer expects colours**, not which source file supplied them or what the colours were. In particular, the indoor Wood branch is a distinct palette destination; treating every Wood prop as an outdoor-colour binding would discard real native behavior.

This audit does **not** identify arbitrary nonzero words at y511 after a synthetic area/reload preview as the original palette: boot resources, prior section VRAM and incomplete empty-s0 loads must be accounted for. The current helper palettes remain reconstructed presentation data, and Group 86's warm ramp remains an artistic proposal. A restoration can intentionally upload its replacement palette to the surviving destinations, but that upload and its colours must be labelled authored. No Group 86 scenery handler/CLUT binding is established by this table; AREA18's surviving set has actors, not a prop list.

Source anchors: [Wood handler](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA11SceneryHandler.c), [Stone handler](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA16SceneryHandler.c), [Iron handler](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA17SceneryHandler.c), [SPR part/CLUT override draw path](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownDrawObjectSprite.c).

### D. Orphan function bodies do not necessarily mean orphan gameplay

This pass scans all aligned words in the supplied **MAIN executable and INFO2**, testing full 32-bit pointer equality and decoded direct `J`/`JAL` destinations. It includes unconditional tail jumps, not only calls. The main executable's addresses use its `+800` file header; the offsets below are all INFO2 offsets. This does not cover every possible split-address/computed reference or prove runtime reachability.

| Function entry | JP address | INFO2 offset | Direct/pointer references in MAIN+INFO2 | Interpretation from the matched source |
|---|---|---|---:|---|
|`topdownA11ActorDialogueBank2`|`800F2F24`|`942C`|0|Uncalled generator/Watchtower-hint helper; the normal Wood dialogue does not inline it, while X11 has the same messages/event interaction|
|`topdownA16ActorDialogueBank2`|`800F413C`|`A644`|0|Standalone duplicate of logic retained inline in Stone dialogue case 8|
|`topdownA17ActorDialogueBank2`|`800F5218`|`B720`|0|Standalone smith helper; equivalent logic is inline in Iron dialogue case 2|
|`topdownA17ActorDialogueBank3`|`800F52F8`|`B800`|**1**|Positive control: real `JAL` at `800F55D0` from normal Iron dialogue|
|`topdownA11SceneryInit`|`800F7F6C`|`E474`|0|Initialization is embedded in the live Wood scenery handler|
|`topdownA11SceneryUpdate`|`800F8070`|`E578`|0|Room-visibility behavior is embedded in that handler|
|`topdownA16SceneryInit`|`800F1CFC`|`8204`|0|Initialization is embedded in the live Stone handler|
|`topdownA16SceneryApplyState`|`800F1E00`|`8308`|0|Its state-2/3 substitution is embedded in the live Stone updater|
|`topdownA17SceneryInit`|`800F20F8`|`8600`|0|Initialization is embedded in the live Iron handler|

These bodies are useful retained code, but “0 references to this entry” must not become “the smith dialogue/Stone state change was removed.” The source makes the inline duplication explicit, and native JP matches the same masked instruction structures at these scoped addresses. This comparison is a structural cross-build control, not a newly compiled/matched-C claim. Source: [Stone dialogue](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA16ActorOpenDialogue.c), [Iron dialogue with inline helper](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA17ActorOpenDialogue.c), [Stone scenery updater](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA16SceneryUpdate.c).

### E. Two selection traps resolved by following the native consumers

**Iron animation 15 is not orphaned.** Placement selects script 13 for P16 at `(263,457)`. Its updater chooses `13 + D_8009CFA1` (JP flag **`8009EB49`**). On the first traversal of passage scene 8, starting with phase zero, the native scene changes that flag to 1 when its countdown reaches 42 (`800FE364`), then to 2 on completion (`800FE390`). Thus P16 has a real path **script/frame 13 → 14 → 15**. These three Iron scenery scripts are single held frames, respectively at `80107018`, `80107020`, `80107028`. All 24 entries of its table have a surviving selector once this progress path is included. This narrows the orphan finding to the **fourth definition**, not an invented missing Iron animation.

**Stone script index 12 does not mean frame 12.** The normal seven-prop list selects slots `0,1,2,3,8,9,10`; the alternate list selects 12 for P6, while the updater requests 11/12 in its index field. JP table `80101C48` has slot 11 → `80101E20` → **frame 11**, slot 12 → `80101E30` → **frame 15**. Slot 13 points to `80101E28` → frame 12. All three are held-frame records. The fourth audit adds an important consumer correction: the live updater does not refresh P6's animation pointer, so changing that index alone does not display these requested frames. Reinitializing from the alternate list does. The Stone scenery table also shares script data with the working Baccus definitions; its entries absent from Stone placements cannot be declared globally orphaned just from that absence.

Source: [passage scene 8](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/npcSet0FSceneStep8.c), [Iron scenery updater](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA17SceneryUpdate.c), [Stone spawner](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/spawnNpcSet0E.c).

### F. What a P# prop actually dispatches to: not an APD item ID

The native spawners allocate all these `SpawnB` records as **layer-3 engine object type `1D`**, then copy the record's first word into **object byte `0E`**. These are different fields. Therefore the `Prop.kind` / source `SpawnB.type` values 0/1/2 in the editor are **not** object handler IDs 0/1/2 and are not inventory item numbers.

| Town | Native store of fixed engine type `1D` to object+02 | Native store of record first word to object+0E |
|---|---|---|
|Wood|`800FC388` / INFO2+`12890`|`800FC3B8` / +`128C0`|
|Stone|`800FC7D8` / +`12CE0`|`800FC808` / +`12D10`|
|Iron|`800FD4D0` / +`139D8`|`800FD500` / +`13A08`|

The area dispatcher routes engine type `1D` to the scenery handlers discussed above. Some of those scenery objects have real gameplay effects—the lifts move the player and passage progress changes a prop—but the record does not directly say “give inventory item X.” The distinct top-down pickup handler is **layer 2/type `2D`**, `topdownItemSpotHandler` / `topdownItemSpotCheckStep`, whose definition table and item-grant call explicitly contain the item ID. The known cut-town spawners create residents (`30`) and these scenery objects (`1D`), not an extra hidden `2D` pickup list.

This corrects the overly broad suggestion that any editor P# could itself be an APD item placement. P# is an editor label for a native INFO2 scenery record. Its visual identity can remain unknown while its dispatch class is known. The meaning of every value stored at byte `0E` is not established here; it should remain a raw field rather than being renamed to a guessed item or behavior. Source: [Wood spawn](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/spawnNpcSet0D.c), [Stone spawn](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/spawnNpcSet0E.c), [Iron spawn](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/spawnNpcSet0F.c), [item-spot grant logic](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownItemSpotCheckStep.c).

### Reproducing this pass and its limits

The durable read-only audit is **`tools/audit_cut_village_orphans.py`**. Run:

```powershell
python tools/audit_cut_village_orphans.py "rom/Ore! Tomba (Japan).cue" --pal-cue "rom/Tombi! (Europe) (En,Es,Pt,Sv,Da).cue"
```

It rejects a changed MAIN/INFO2 fingerprint, decodes all three scenery windows, preserves the fourth Iron definition, records prop selectors, follows bounded animation records, checks all ten Wood script starts' literal references, and scans the nine helper entries for pointers and direct jumps. It also verifies the native spawner stores that distinguish engine type from the raw prop field, and records the scenery handlers' CLUT constants. Optional PAL comparison verifies its INFO2 hash, exact Wood script records and fourth Iron definition. Decoded findings, per-function hashes and physical offsets are written to ignored `work/cut_village_research/orphans_deeper.json`; the essential facts are reproduced above and do not depend on that scratch file.

The audit is a binary-data/reference check, not a console/emulator execution, a C recompilation or a proof that every candidate is unreachable. Native scene/handler semantics are established with the pinned matched C and inspected JP instructions; selector exclusions include the audited scene-driven alternatives. No new original CLUT payload, sprite-part table, cut-town map, alternate complete controller or unique X19 payload was recovered in this pass. The strongest new reconstruction leads are the **Wood scenery script window** and **Iron subtype-3/page-8 definition**; the CLUT destinations and false-positive controls make them more usable without turning guesses into recovered assets.

### Town-attribution check: passage scenes 8/9 are Iron, not Stone

The observation that Stonetown also mentions a lift is not enough to assign these particular scenes to it. The decisive evidence is the native controller dispatch, not a visual resemblance or the word “lift.” Iron's NPC set **0F**, `updateNpcSet0F` at JP **`800FEC78`**, uses the 12-entry scene jump table at **`800EA534`**. Entries 8/9 select code at `800FED80` / `800FED90`, containing direct calls to **`800FE22C` / `800FE3D8`**, respectively. Entries 10/11 likewise call `800FE504` / `800FE668`. The `npcSet0FCheckTriggerSpots` code selects those steps from the exact Iron passage rectangles already listed in this report.

Stone's distinct set **0E**, `updateNpcSet0E` at JP **`800FD194`**, dispatches idle step 0 and scenes 1–3; it has no scene-8/9 branches. Its three scene calls are at `800FD2AC`, `800FD2BC`, `800FD2CC`, targeting `800FC89C`, `800FCD78`, `800FCEB0`. Stone's lift references can be investigated separately, but do not reassign the Iron controller's routes. Source: [Iron scene dispatcher](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/updateNpcSet0F.c), [Iron trigger selector](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/npcSet0FCheckTriggerSpots.c), [Stone scene dispatcher](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/updateNpcSet0E.c). The durable audit now asserts the Iron table entries and native call instructions too.

### Character-attribution check: Yan dialogue in Lumberjack Town is unconfirmed

Checked the supplied JP area's actual WFM D0FF bank in **`AREA11/A002.GAM`, decompressed offset `86E0`**, not just a translated transcription. It has 250 dialogue entries, with group starts `0,190,191,210,232` (remaining group offsets zero). Its only literal **ヤン** mention is entry **154**, `ヤンの弁当をつかった` (“Used Yan's lunch box”), in the common item-use text. That is not a conversation spoken by Yan or a town-specific resident binding.

The normal Wood dialogue function **`800F3000`** has cases 0–10, selecting bank entries **210,232,233,234,235,236,237,238,239,242,243,248**; none contains Yan's name or establishes him as the speaker. The orphan generator/Watchtower hint helper is independently accounted for above. Resident **#12**, subtype 4, inside H3 at `(432,448)`, requests **case 11**, which that switch does not implement. Its lost sprite page/parts and unimplemented dialogue cannot be filled in as “Yan” from the placement alone.

**Conclusion:** there is no confirmed Yan conversation attached to the surviving cut Lumberjack Town actor chain. This is not a proof that Yan was never planned to appear there: unidentified residents and missing data leave that historical question open. A name-less line's speaker cannot be ruled in or out merely by searching for ヤン; the native caller/actor linkage is the necessary second check. The shared lunch-box message must not be presented as evidence of a Yan conversation. Source: [Wood dialogue selector](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA11ActorOpenDialogue.c), [Wood spawner](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/spawnNpcSet0D.c); native text/case extraction is retained in `work/cut_village_research/yan_lumberjack_check.json`.

### Eel warning and intended glove giver: Gantetsu's Iron Town block

The supplied JP `AREA17/A003.GAM` WFM D0FF at decompressed offset `6CA8` has SHA-1 **`c7ee48bfef0f60e33321f64f3e650d1081b6bdf0`**. Its group 3 starts at entry 240. Entry **240 / (3,0)** explicitly says `わしの名はガンテツ` (“My name is Gantetsu”). Normal Iron dialogue case 3 calls `topdownA17ActorDialogueBank3`, JP **`800F52F8`**, which selects that self-introduction. The placed actor with this case is **resident #4**, subtype 4, outdoors at **`(223,123)`**. This identifies the outdoor bomb-maker branch as Gantetsu; it does not recover his sprite parts.

The same block contains **245 / (3,5)**, asking for an electric eel to power the hut's apparatus and black water for the bomb material, followed by **246 / (3,6)**: `ちょっとまった! 電気ウナギを素手でつかまえる気か? …ほら、これを持っていきな…` (“Wait! Are you going to catch an electric eel bare-handed? …Here, take this with you…”). Entry **247 / (3,7)** acknowledges both materials. This is strong contextual evidence that **Gantetsu in Iron Town was the intended giver of protection for catching the eel**, consistent with the retained Rubber Gloves item-use message/description.

The important missing edge is that **entry 246 has no resolved surviving display selector**. Gantetsu's live helper selects (3,0/2/3/5/8/11), while controller requests for scenes 5–7 reach reset-only stubs. No intact glove-grant call or item ID is established by the warning. Therefore record Gantetsu/Iron Town as the strongly supported intended speaker/context, not a proven working handover or an exact indoor staging position. The indoor subtype-4 actor at `(223,0)` still lacks an implemented normal dialogue case and cannot independently settle where such a scene would have moved him. The WFM viewer now exposes this speaker-candidate evidence on entry 246 without promoting its unresolved caller to a confirmed display reference.

### Text-usage presentation: blue confirmed cut paths, purple candidates, shared-message references

The JP usage index was rebuilt after the Wood/Stone binding fixes. **64 entries** have a verified binding to an actually placed cut-village NPC: **12 Wood, 21 Stone, 31 Iron**. The WFM viewer marks these **blue**, labels them **Confirmed unused — cut-village dialogue**, and provides a dedicated filter and per-entry town, resident, routine and group/line evidence. Native selector status remains `referenced`; orthogonal `availability=confirmed_unused_cut_village` records that this NPC path belongs to a section not entered by normal unmodified retail play. This does not relabel an entire area's shared text bank or claim that identical wording elsewhere is unused. AREA18 has no established normal dialogue caller and is not guessed into this classification.

The older selector index also had false purple results from outdated village bindings. Rebuilding corrects **50 previously `not_found` entries** across Baccus, Wood, Stone and Iron; these are concrete native reference corrections, not observed gameplay claims. The profile now resolves Stone's four-phase dialogue rows through the actual resident records.

A second pass found **146 remaining `not_found` entries with exact native glyph/control-stream equivalents referenced elsewhere**. Equality uses glyph bitmap hashes, dimensions, glyph flags, control words and their arguments; it does not use OCR, translated strings or guessed character names. These now have `status=referenced_elsewhere`, a plain **Shared text — referenced elsewhere** label, and linked bank/index evidence. They are not purple. Their `local_status=not_found` is preserved: this copy still lacks a resolved selector, while the shared message has another display reference. Reference-bank hashes are revalidated when attaching this evidence; changed referenced banks invalidate the annotation rather than silently preserving it.

The regenerated JP profile (`jp-retail-selector-audit-v3-cut-and-shared-dialogue`) contains 4,647 referenced, 1,151 dynamic, 146 referenced-elsewhere and **339 possibly-unused** records. The 64 blue cut-path annotations are a subset of referenced records. The remaining purple classification is still a candidate, not confirmation of global unreachability. Counts cover this profile's audited slot-0 records; separate event-hint research retains its own classification. JSON/CSV exports carry the availability, native selector evidence, equivalent references and Gantetsu speaker-candidate metadata.

WFM display also now starts at **Fit** while retaining a subsequently selected zoom across entries. Known English banks show the original preview without the Japanese-to-English translation pane/controls; Japanese banks retain those views. Checks: `python tools/validate_text_usage_ui.py "rom/Ore! Tomba (Japan).cue" --english-cue "rom/Tombi! (Europe) (En,Es,Pt,Sv,Da).cue"`.

## Third JP orphan-data audit — resident actions and an unbound animation template

This pass examines **JP retail only**, using the MAIN/INFO2 fingerprints in the target-identity table. It adds **17 high-slot resident animation-script candidates**, occupying **840 bytes of script payload**, beyond the earlier scenery-script and Iron subtype-4 inventory. They cover **46 distinct Wood frame IDs and 16 distinct Iron frame IDs**; frame numbers belong to each area's missing resident SPR bank, so these are not 62 recovered pictures or one global frame namespace.

The documentation comparison was made against this report before this addition, the bundled research references, and upstream `docs/` and `notes/` at **`44e814a6268f294f889ee77f5aad319f88e82a50`**. The raw animation words already exist in upstream's data transcription; the new findings are the **unbound template, absence of a surviving selector for the action tails, native index mismatch, and terminal-mode differences**. The checked documents describe the Green Fortune Teller and Stone lifting frames, but do not make these particular connections. This is a bounded documentation comparison, not a claim about every unpublished/community document.

All addresses in this section are **JP RAM addresses**. Unless stated otherwise, the file is **`SYSTEM/INFO2.BIN`**, and the physical file offset is `address - 800E9AF8`. Resident numbers are one-based editor numbers. These are **unselected candidates in the preserved native village chains**. The reference/selector limits below are part of the finding; absence of a literal pointer alone is not treated as proof of global unreachability.

### G. Wood has an unbound 12-script template covering frames 167–203

The five Wood resident definitions occupy **`800FFFFC..80100037`**. Their animation pointers are `80106224`, `80106268`, `801062B0`, `801062F0`, and `80106360`. The fourth definition, subtype 3 at **`80100020`** (+`16528`), points to `801062F0`. Its ordinary slots 0–15 cover frames 108–140. After those 16 pointers, a different, compact **12-pointer block** survives at **`80106330..8010635F`** (+`1C838..1C867`), immediately before subtype 4's table.

**No resident definition points to `80106330`.** The only placed subtype-3 resident is **#11, `(496,344)`**, the old-signboard speaker. His normal native handler selects the prefix's ordinary idle/talk slots; it does not select this tail. Therefore the tail is reachable by artificially indexing subtype 3 with 16–27, but there is no surviving normal selector that does so. It must not be labelled as twelve proven actions of resident #11, or used to invent a sixth resident placement.

The tail points to a contiguous **592-byte payload, `80106AB0..80106CFF`** (+`1CFB8..1D207`). All twelve scripts finish with **hold bit `8000`**, with no animation jump pointer. The complete frame/timing inventory is:

| Tail index / subtype-3 index | Pointer cell | Script start | File offset | Frames in order | Ticks in order |
|---|---|---|---|---|---|
|0 / 16|`80106330`|`80106AB0`|`1CFB8`|167|60|
|1 / 17|`80106334`|`80106AB8`|`1CFC0`|168|60|
|2 / 18|`80106338`|`80106AC0`|`1CFC8`|169|60|
|3 / 19|`8010633C`|`80106AC8`|`1CFD0`|188,189,190,189,190,189,190,189,188|5,3,17,7,17,7,17,3,5|
|4 / 20|`80106340`|`80106B10`|`1D018`|191,192,193,192,193,192,193,192,191|5,3,17,7,17,7,17,3,5|
|5 / 21|`80106344`|`80106B58`|`1D060`|194,195,196,195,196,195,196,195,194|5,3,17,7,17,7,17,3,5|
|6 / 22|`80106348`|`80106BA0`|`1D0A8`|170,171,172,173,174,175|8,8,8,8,8,8|
|7 / 23|`8010634C`|`80106BD0`|`1D0D8`|176,177,178,179,180,181|8,8,8,8,8,8|
|8 / 24|`80106350`|`80106C00`|`1D108`|182,183,184,185,186,187|8,8,8,8,8,8|
|9 / 25|`80106354`|`80106C30`|`1D138`|197|60|
|10 / 26|`80106358`|`80106C38`|`1D140`|198,199,200,199,200,199,200,199,200,199,200,199,198|9,8,17,7,17,7,17,7,17,7,17,8,9|
|11 / 27|`8010635C`|`80106CA0`|`1D1A8`|202,201,202,203,202,201,202,203,202,201,202,203|4,19,4,6,4,6,4,19,4,6,4,6|

**Connection to the teller family:** compare these twelve scripts with Wood subtype 4's twelve scripts at `80106360`. Every frame is exactly **37 lower**, and every box word, argument word, duration, terminal flag, and record count is identical. The frame sets are 167–203 versus 204–240. Each orphan script start has exactly one aligned full-word reference in MAIN+INFO2: its own pointer cell above. There are no additional aligned pointers into the middle of this payload, and no aligned full-word pointer to its table start.

This is stronger than a vaguely similar frame range: it is a second complete instance of the same compact animation template. **Identity remains unresolved.** It could be an earlier/alternative teller-style actor template or a discarded action bundle. It does not identify a second Fortune Teller, its colour, a character's position, a raft maker, or missing pixels. Its location after subtype 3's ordinary pointers is a retained table relationship, not a recovered drawing assignment.

Source anchors: the definitions and pointer arrays in [`src/data/i0nfo2/D_800FEBD0.c`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/data/i0nfo2/D_800FEBD0.c) use PAL names `data_80107648[28]` and `data_801076B8[12]`; the candidate is the former's last twelve entries. Those source addresses are PAL, not substitutes for the JP addresses above.

### H. Three short Wood resident actions have no surviving native selection

The physical boundaries of the first two Wood pointer tables are **17 and 18 entries**, respectively. Reading an arbitrary 24 entries would incorrectly attribute some of the next subtype's scripts to the previous one. Beyond their ordinary slots 0–15, these scripts remain:

| Subtype / slot | Definition; native page / SPR slot | Pointer cell | Script; file offset | Frames | Ticks |
|---|---|---|---|---|---|
|0 / 16|`800FFFFC`; page `01`, SPR `11` decimal|`80106264`|`80106560`; +`1CA68`|33,34,35,34|8,1,10,4|
|1 / 16|`80100008`; page `0A`, SPR `11` decimal|`801062A8`|`801066D0`; +`1CBD8`|69,70,71,70|6,2,5,3|
|1 / 17|same definition|`801062AC`|`801066F0`; +`1CBF8`|72,73,74,73|6,2,5,3|

They are **three 32-byte scripts, 96 bytes total**, each ending in hold rather than loop. The subtype-0 definition is used by residents **#1–5**; subtype 1 by **#6/#8/#9/#10**. This identifies the resident families their table prefixes belong to. It does not establish which resident was meant to perform the extra actions. MAIN+INFO2 contains exactly one aligned full-word reference to each script, from the listed pointer cell, and no additional pointer into its body.

Native initialization uses the preserved record's animation selector 0. Idle/movement/talk selection stays below 12; Wood's controller has no active scene body to select 16 or 17. The orphan hint helper also does not select them. These scripts are useful **extra-pose/action constraints** for a future matching SPR search. They are not an implemented crafting animation or a newly recovered reward sequence.

### I. Iron retains two unselected repeating resident actions, including the smith's family

The first two Iron resident pointer tables each have **17 entries**. Their final entries select distinct repeating actions:

| Subtype / slot | Definition; page / SPR slot | Pointer cell | Script; file offset | Frames in order | Ticks |
|---|---|---|---|---|---|
|0 / 16|`801000A8`; page `01`, SPR `11` decimal|`801070B0`|`801072E0`; +`1D7E8`|33,34,35,36,37,38,39,40,36|16,4,4,16,7,5,5,7,60|
|1 / 16|`801000B4`; page `0A`, SPR `11` decimal|`801070F4`|`80107494`; +`1D99C`|74,75,76,77,78,79,80,81,77|16,4,4,16,7,5,5,7,60|

Both end with **control `403C`**, followed by a pointer back to their own start. Their jump words are at **`80107328`** and **`801074DC`**. Thus each occupies **76 bytes** and repeats after **124 ticks**. The second literal reference to each script is this self-loop, not another actor/scene consumer. There are no other full-word pointers into either body in the audited regions.

Subtype 0 is used by residents **#1/#6/#8/#11/#12/#15**; subtype 1 by **#2/#3/#7/#10/#13**. In particular, **#3 at `(-75,371)` in H5**, the smith involved in the Iron Wheel transaction, uses subtype 1. This gives script `80107494` a concrete **smith-family connection**. Calling it the intended forging action is still an inference: the lost SPR parts prevent identifying the movement visually, and the surviving wheel scene selects ordinary `8 + facing` scripts, including slot 9, rather than slot 16. Its previously documented unset actor pointer is a separate defect.

These two loops are separate from the already documented **24 MAIN scripts of subtype 4/Gantetsu**. Their payload belongs to INFO2 and their frame sets lie below that bank's 148–202 range. Restoring the loops cannot by itself restore the missing bomb scenes or an item handover.

### J. The compact teller tables do not match Wood's ordinary selector layout

The preceding template comparison also exposes an implementation mismatch for the **already documented Green Fortune Teller**, Wood resident **#12**, subtype 4, H3 `(432,448)`. His compact table is **`80106360`**, twelve entries. The native Wood handler still uses the ordinary four-direction conventions: idle `facing`, movement `facing + 4`, talk `contact_direction + 7`.

The native selector probe records these exact choices:

| Operation | Input from the preserved record / collision direction | Chosen compact slot | Script start; first frame |
|---|---|---|---|
|Initializer `800F3EC8`|record animation selector 0|0|`80106D00`; 204|
|Normal idle in `800F3D0C`|preserved facing 3|3|`80106D18`; 225|
|Talk entry `800F321C`|direction 1|8|`80106E50`; 219|
|Talk entry|direction 2|9|`80106E80`; 234|
|Talk entry|direction 3|10|`80106E88`; 235|
|Talk entry|direction 4|11|`80106EF0`; 239|

The initializer and idle path therefore do **not** keep selecting the same stationary-pose script. The talk path uses a different portion of the compact table from the teller's ordinary talking family. The stores occur at JP **`800F3FE0`**, **`800F3DDC`**, and **`800F3300`**, respectively. This is a native index/layout finding; no screenshot of a working original cut-town interaction is claimed.

For an independent JP control, the working tunnel teller's definition is at **`SYSTEM/INFO3.BIN` `800F033C`** (+`6844`), its 15-entry table at **`800F068C`** (+`6B94`). INFO3 SHA-1 is **`c5284a56eaa9846752d8ade2a37b2dacbd3842a5`**. Compact slots 0–11 correspond to tunnel slots **`1,0,3,5,4,7,9,8,11,12,13,14`**, with frame offsets **+157** for the orphan and **+194** for Green. Tunnel aliases 0/2, 4/6, and 8/10 implement four-direction reuse; the compact tables omit those alias entries.

**Important terminal-mode distinction:** relative frame order, box/argument words and tick counts match, but this is **not a byte-identical copy of the working tunnel animation logic**. In compact slots **3/4/5/6/7/8/10/11**, both Wood copies **hold** (`8000`), while the tunnel copy **loops** (`4000` plus a jump back). The other four compact slots are held poses in both. Upstream's teller correspondence remains useful, but “same timings” must not erase the different termination behavior.

Rebuilding this character therefore needs an explicit decision about selector remapping and hold/loop behavior as well as SPR parts and the missing dialogue case. Copying the tunnel SPR's pictures alone leaves these original table/handler inconsistencies. The unbound 167–203 block is another constraint on that decision, not permission to silently choose a second named character.

Source anchors: [`topdownA11ActorStep`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA11ActorStep.c), [`topdownA11ActorTalkStep`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA11ActorTalkStep.c), [`tunnelActorTalkStep`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo3/tunnelActorTalkStep.c). The latter selects `contact_direction + 3`; Wood selects `+7`. JP raw records and MIPS execution, rather than the port's reconstructed assets, supply the comparisons above.

### Native selection audit, controls and reproduction

`tools/audit_cut_resident_orphans.py` rejects changed MAIN or INFO2 and checks the separate INFO3 fingerprint for the teller control. It decodes each physical pointer window, follows script control words, retains literal users including self-loops, and writes the decoded facts/hashes to ignored `work/cut_village_research/resident_orphans_jp.json`.

The independent selector check runs original JP MIPS in isolated Unicorn memory, stopping on the **first store to the actor's animation pointer**, before drawing, file/device access or animation services. It exercises **41 preserved resident initializers**, and every defined Wood/Stone/Iron subtype over four facing directions, five ordinary movement behaviours and four talk-contact directions: **377 probes total**, all selecting **slots 0–11**. This intentionally includes more ordinary behaviour combinations than the placements use. It does not emulate an entire game, the incomplete scenes, or every possible game state.

| Village | Initializer | Normal actor step | Talk step | Direction setter |
|---|---|---|---|---|
|Wood|`800F3EC8`|`800F3D0C`|`800F321C`|`800F31C0`|
|Stone|`800F4FA0`|`800F4DE4`|`800F43D0`|`800F40C8`|
|Iron|`800F64AC`|`800F62E8`|`800F60B4`|`800F51A4`|

A separate control-flow argument scan resolves **25 direct INFO2 calls** to the direction setters: **15 Stone and 10 Iron**, with offset arguments only **0,4,8**; none calls Wood's setter. The scene source's facing assignments remain ordinary directions. Inlined movement/talk selectors are checked by the native probes rather than omitted from this accounting. Deliberately forcing selector 16 through each village's setter correctly reaches the high-slot data; this is kept as a **synthetic positive control**, not asserted to be an original game path.

All 17 candidate scripts also execute through the original JP **`AnimLoadDuration` `80020DE4`** and **`AnimAdvance` `80020E38`** for a complete first pass. Held scripts stay on their final record and return the terminal signal; both Iron loops return to their original script start at tick 124. No new sprite rectangles, original colours, item-grant calls or quest-state transitions are inferred from that successful playback.

Reference checks cover aligned full-word pointers throughout resident MAIN and INFO2, **including pointers to script interiors**. An additional deliberately overinclusive check pairs any `LUI` with an ADDI(U)/ORI/load/store low half within the following eight instructions, without requiring register agreement. It finds **zero candidates** for the new payloads or unbound table start. This improves on literal-only checking, but does not rule out arbitrary multi-stage/computed address construction or modified execution.

The audit retains controls that prevent inflating this pass's discoveries:

- **Stone lifting scripts 16–23, frames 120–129, were already documented.** Their absence from ordinary native selections is a useful consumer result, not eight newly discovered script payloads. Empty phase-table rows 0/9–15 add no lost dialogue.
- **Gantetsu's 24 MAIN scripts were already documented.** They remain a positive cross-region decoder control, not 24 new findings here.
- The Wood/Stone/Iron/reunited resident terminators are complete 28-byte records: type `00FF`, then 26 zero bytes. No hidden resident was found inside those terminators.
- All **94 unique loaded APD payloads** end at their terminator record, with **no post-terminator payload**. This particular check supplies no extra cut-town placement list; it does not claim to inspect arbitrary encoded placements in every disc file.

Run on the supplied JP disc:

```text
python tools/audit_cut_resident_orphans.py "rom/Ore! Tomba (Japan).cue"
```

The report is the durable interpretation; the JSON contains full per-step control/argument data, file offsets, literal users, all 377 selector traces, the 25 call sites, the 17 playback checks and the tunnel comparison. No ROM data is patched and no original game images are bundled by this audit.

## Fourth JP audit — dormant state, rendering consumers and reused hints

This pass follows **state writer → state consumer → actual drawing/message data**, rather than adding more animation-table entries. The following consumer defects and relationships were omitted from this report and were not described in the checked upstream research documents at `44e814a6268f294f889ee77f5aad319f88e82a50`. Their underlying functions are present in the decomp; these are additional interpretations and JP-native checks, not claims that the function definitions themselves were newly discovered.

The target remains the same fingerprinted JP MAIN and INFO2. Two additional checked code payloads are **`SYSTEM/X11.BIN`**, 193,716 bytes, SHA-1 **`9ec2628e76ff4689408ed19400ec0851637e665f`**, and **`SYSTEM/X16.BIN`**, 191,476 bytes, SHA-1 **`b43230d3a7a49203207f6068eb6dc437d305f12b`**. These overlays are loaded into separate experiment instances; they are not assumed to coexist with INFO2.

### K. Stone P6 requests different scripts but keeps drawing the old frame

Stone's **P6**, zero-based prop index 5, is subtype 2, room 0, draw-order kind 2. Its normal record requests animation **10** at **`(-4,403)`**; its alternate record requests **12** at **`(-3,403)`**. The alternate list is selected only when runtime byte **`8009EB50`** (PAL `D_8009CFA8`) equals 4. These records and the raw 11/12 requests were already known. The omitted detail is that **the live state-change updater never updates the sprite's animation pointer**.

JP functions in `SYSTEM/INFO2.BIN`:

| Function / operation | JP RAM address | File offset |
|---|---|---|
|Stone scenery handler, `topdownA16SceneryHandler`|`800F1F84`|`848C`|
|Live updater, `topdownA16SceneryUpdate`|`800F1E88`|`8390`|
|Initializer's actual `object+24` animation-pointer store|`800F206C`|`8574`|
|Stone controller, `updateNpcSet0E`|`800FD194`|`1369C`|
|State-change scene, `npcSet0ESceneStep2`|`800FCD78`|`13280`|
|Phase increments to 2 / 3 / 4|`800FCE18` / `800FCE5C` / `800FCE9C`|`13320` / `13364` / `133A4`|

The updater stores 11 or 12 into **`object+B4`**, and adjusts X/Y. It neither stores a replacement pointer at **`object+24`** nor calls the animation-duration loader. The native drawing consumer uses that pointer: MAIN `drawObject` at **`80043728`** dispatches render kind 13 at **`80043A04`** to **`drawObjectSprtTinted` `80047C80`**. At **`80047D60`**, MAIN file +`38560`, it loads `object+24`; at **`80047D68`** it reads the frame word from that script. It does not use the requested index in `object+B4` to choose the frame anew.

An isolated native run initializes P6 through the real handler and then executes the real Stone controller and handler each update. Starting phase 1 is an **explicit synthetic seed**, because the missing initiating write is the separate issue below. Counts include the controller's initial step-selection update:

| Point in the experiment | Phase | Requested index (`+B4`) | Actual script pointer (`+24`) | Frame read by the drawing consumer | Position |
|---|---:|---:|---|---:|---|
|Normal initialization|0|10|`80101E18`|10|`(-4,403)`|
|32nd update after synthetic phase-1 seed|2|11|`80101E18`|10|`(-4,403)`|
|62nd update|3|12|`80101E18`|10|`(-3,403)`|
|63rd update, scene finished|4|12|`80101E18`|10|`(-3,403)`|
|Reinitialize from the phase-4 alternate record|4|12|`80101E30`|15|`(-3,403)`|

Only the initializer writes the animation pointer in the continuous run. Thus the state-change scripts are not displayed merely because their numbers appear in the updater. **Frame 15 can be selected after reinitialization from the alternate list, while the continuous sequence retains frame 10.** This is a stronger reconstruction constraint than “animations 11/12 exist.” It also corrects the earlier wording that implied the live updater actually selected those drawing scripts. The object's precise visual identity remains unresolved; calling this prop the repaired clock is still an interpretation without its original SPR/map.

**The phase-1 seed is missing from the checked direct references.** Scanning MAIN plus **23 unique loaded INS payloads** found twelve statically resolved accesses to `8009EB50`: nine reads and three writes, all in INFO2. The writes are the three increments in the scene above. There is no resolved direct constant-1 store and no aligned full-word pointer to this state byte. The scanner follows straight-line register constants and clears them after branches/calls and their delay slot; indexed/indirect aliases, save restoration and arbitrary computed writes are not ruled out. This is an **unseeded-state candidate**, not a universal proof that the byte can never become 1. Ninety ordinary native idle-controller/prop updates starting at zero leave it zero.

The retail Clock Tower repair is a useful independent control. JP **`SYSTEM/X16.BIN` `brokenStoneGearsRepair` at `80116A2C`** (+`2CF34`) calls MAIN **`setEventComplete` `8001C988`**. Executing its repair state with the event-completion body included writes **`FF` to event 61 at `8009E9AD`**, at MAIN instruction **`8001C9CC`**. The experiment leaves a tag value in `8009EB50` unchanged. The subsequent inventory-service request is for item **`3E`**. Presentation/AP/inventory services are stubbed, so this is a native state-write/control check, not an inventory or full-game test. **Completing the retail clock event does not, by itself, supply the missing direct scenery-phase write in this retained code.**

Source anchors: [`topdownA16SceneryUpdate`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownA16SceneryUpdate.c), [`npcSet0ESceneStep2`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/npcSet0ESceneStep2.c), [`drawObjectSprtTinted`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/drawObjectSprtTinted.c), [`brokenStoneGearsRepair`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/x016/brokenStoneGearsRepair.c).

### L. Stone's H4 craftsman scene copies the controller's position into its first message

Stone resident **#9**, subtype 3, dialogue case 8, is the H4 craftsman at **`(26,174)`**. His actual JP text is in **`AREA16/A003.GAM`**, decoded WFM +`6CA8`, SHA-1 **`b70c77d7534df6745263a2df1b7baacb22a78f6d`**. Entries **185/186/187** are `(2,0/1/2)`: wanting something worthwhile to make; reacting to Tomba's capture by the Masakari; and discussing the **Funga drum, hard-to-find materials, and the Tree of Knowledge**. This is a concrete Stone-craftsman connection to the cut drum/material storyline, not an Iron Wheel or raft dialogue assignment.

The normal case-8 branch checks the Masakari/Tree event bytes **3D/3E** and can increment **`8009EB52`** (PAL `D_8009CFAA`). The controller consumes value 1 and selects scene 3. The scene uses **`SCRIPT_OBJECTS[8]` at `800A0E88`**, matching one-based resident #9, and requests event **`3E`** after its two messages. This ties the scene to that particular craftsman rather than an unidentified generic resident. No drum item is granted by this scene.

The overlooked defect is in **`npcSet0ESceneStep3` at JP `800FCEB0`**, INFO2 +`133B8`. Its first coordinate copy at **`800FCEC4..800FCED8`** (+`133CC..133E0`) reads twelve bytes through the **incoming `s0`**. Only afterward does **`800FCF00`** (+`13408`) load the intended resident pointer from `800A0E88`. The first message call is at **`800FCF74`** (+`1347C`), selecting `(2,1)` with the already copied coordinates.

Two direct native trials changed the incoming `s0` object's coordinate bytes while leaving the real craftsman unchanged; the first message position changed with the incoming register. More decisively, running through **`updateNpcSet0E`'s actual scene-3 dispatch** makes incoming `s0` point to the **controller**. The message receives the controller's coordinate bytes instead of the craftsman's. The scene then correctly changes the real resident's step/state: this is **a wrong first-message anchor**, not evidence that every actor access uses an invalid pointer or that a crash was observed. Later in the scene the coordinates are copied again after the resident has been resolved.

The decomp's [`npcSet0ESceneStep3.c`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/npcSet0ESceneStep3.c) already notes the uninitialized C variable needed to match. The additional finding here is its **specific JP caller-chain consequence and resident/story association**. A rebuild should obtain the resident before copying its position; supplying an SPR alone does not repair that interaction.

### M. Prop kind 0/1/2 is a draw-order policy

The previous prop audit established that the first record word is copied into **object byte `+0E`**, while engine layer/type are fixed separately. Following the actual consumer now gives that word a meaning: JP **`topdownSortDrawOrder` `800EE910`**, INFO2 +`4E18`, reads it and assigns signed draw-depth byte **`object+0F`**.

| Record kind / object `+0E` | Retained behavior |
|---|---|
|0|Participates in sorting by world Y with the other ordinary town objects/player; receives a relative depth such as `index - 10`|
|1|Excluded from that Y-sort list; assigned fixed depth **-12**|
|2|Excluded from that Y-sort list; assigned fixed depth **+12**|

Native trials use two kind-0 props and one each of kinds 1/2. Swapping only the two kind-0 Y positions swaps their assigned depths **-9/-10**; the other depths remain **-12/+12**. Thus the field controls ordering of the existing drawing. It is not an item ID, inventory category, sprite group or subtype. Fixed depth alone also does not identify a particular drawing as a roof or interior.

Source: [`topdownSortDrawOrder.c`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/i0nfo2/topdownSortDrawOrder.c). The editor now says **“draw-order kind …”** with the decoded meaning in the selected prop's description and the P# tooltip, replacing the ambiguous “type” wording. This explains the raw value without changing any graphics assignment or ROM record.

### N. Correction: Wood's orphan helper is a reused generator/Watchtower hint, not raft crafting

Earlier versions of this report called **`topdownA11ActorDialogueBank2` `800F2F24`** a raft-related helper and associated it with a raft transaction. **That attribution was wrong.** Its native selector arguments are `(2,4)` and `(2,5)`, with event **`4F`**. The supplied JP bank resolves them to:

| Native pair | Live JP entry | Meaning |
|---|---:|---|
|`(2,4)`|195|Thanks Tomba for using the bomb and getting the generator repaired|
|`(2,5)`|196|An old story about a Watchtower in the Dwarf Forest having an elevator down underground|

Bank: **`AREA11/A002.GAM`**, decoded WFM +`86E0`, SHA-1 **`3eaa362d4c39bc8048deebdde12a031bdb9d05ee`**. Event `4F` is the underground-forest hint event, not the raft event. No stale transcription index or translated paraphrase is used to resolve these pairs.

There is also a retained **retail side-view counterpart**, not merely similar wording: JP X11 **`powerPlantThanksTalk` `80117AFC`** (+`2E004`) selects those same pairs at **`80117C24`** (+`2E12C`) and calls `setEventStarted(4F,0,0)` at **`80117C64`** (+`2E16C`). Its native message call merges lines 4/5 from different states. Separate native executions of states 0 and 1 select line 4 and line 5 respectively. The repeat hint routine is **`80117D08`** (+`2E210`), selecting line 5.

The native side-view dispatcher **`stepFactoryNpcTalk` `80118104`** (+`2E60C`) has its subtype-2 step-7 call at **`801183A4` → `80117AFC`**, and step-8 call at **`801183B4` → `80117D08`**. This establishes a preserved retail controller chain for the hint texts. The top-down helper body is still uncalled in the previously audited scope, and Wood's flag at `8009EB51` is still unconsumed by its empty controller; **the text/event interaction is not lost merely because that particular body is orphaned**.

The actual separate raft discussion survives at **entries 220–224, `(3,10..14)`**, in the same JP bank. It identifies a raft specialist, asks for timber, refers to material beneath the Wise Old Tree, and describes using the completed raft at the river on Old Tree Hill. The audited normal Wood dialogue switch does not select those pairs. Those messages remain a raft-reconstruction lead, but this helper/flag supplies **no evidence of their caller, craftsman's placement or item hand-in sequence**. The earlier raft attribution has been removed from the main findings and unresolved-question tables above.

Source anchors: [`powerPlantThanksTalk`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/x011/powerPlantThanksTalk.c), [`powerPlantElevatorHintTalk`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/x011/powerPlantElevatorHintTalk.c), [`stepFactoryNpcTalk`](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/src/x011/stepFactoryNpcTalk.c). Their published C addresses are PAL; the JP addresses above were resolved and checked in the supplied X11.

### Reproducing the fourth audit

```text
python tools/audit_cut_village_state.py "rom/Ore! Tomba (Japan).cue"
```

The durable tool checks MAIN/INFO2, X11/X16 and both WFM fingerprints. It records all scenery snapshots and transition ticks, the unchanged pointer versus alternate-record initialization, native phase writes, the bounded 24-region reference scan, the two perturbed-register message tests plus the actual controller-dispatch test, draw-order trials, retail event-completion control, and Wood's native dispatcher/message evidence. Output is ignored **`work/cut_village_research/state_consumers_jp.json`**. Read/write traces are obtained from executed instruction/register effective addresses and checked against memory snapshots; the installed Unicorn MIPS backend's global memory hooks were avoided because they disrupted a leaf return. No guest instructions were altered to make the experiment pass.

These checks do not reconstruct a collision map, original sprite parts, palettes or full retail reachability. They identify concrete missing/disconnected behavior and prevent two false shortcuts: treating a requested animation index as the frame actually drawn, and treating an unused function body as proof that its dialogue/content is unused everywhere.
