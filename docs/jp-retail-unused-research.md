# Ore! Tomba: unused-content research beyond the cut villages

Research date: **1 November 2026**. Target: the user's unmodified **Japanese retail SLPS_011.44** disc. This file records native findings, corrections to research leads, and the work still needed. It is not a restored quest or a claim that every candidate is unreachable in normal play. No ROM or save is changed.

The three attached articles and the user's pasted item/event/sprite/sound lists are **community research leads**. Their speculation and embedded “To do” notes are not instructions or binary evidence. **No TCRF page or remote media was opened.** This investigation uses those supplied texts, the local decomp checkout, and the supplied disc.

## Findings added by this audit

| Finding | Native evidence | Practical consequence |
| --- | --- | --- |
| The Jungle eel has surviving art, an original palette and a three-frame script | SPR slot 3 frames 33–35; X10 `8012DEB8 → 8012E0E0`; decoded and visually inspected | Corrects the checked upstream report's “no ... eel ... sprite” conclusion |
| Its retained script ends by holding its final frame | Native `AnimAdvance`: frame changes at updates 8 and 16; completion at 24; no backward jump | A looping GIF is not evidence of a looping retail script |
| Eel item 108 does not select that script through the world-item initializer | All 200 item selectors and 97 selected descriptors checked; item108 selects descriptor0/berry frame0 | Adding the inventory item alone cannot reconstruct the eel creature |
| JP cannot inherit the PAL shock branch by address/name analogy | JP X10 has 74 player animations; its 1,492-byte hurt routine selects ordinary animation57 | PAL animation80 and its shock-reason branch are not verified JP behaviour |
| The two “Chick” placeholders retain different JP use messages | item133: `1UPをつかった`; item134: `ゲージMAX +1をつかった` | Their residual text points toward stat items, while both menu-use conditions remain false |
| Funga Drum and Small Drum share their world rendering chain | items125/137 → different descriptors → same `80011E8C → 80012598`, SPR4 frame197 and CLUT `7D12` | Their identity difference is not a different world sprite; their hit boxes do differ |
| The material remnants are uneven | Wood, Funga Tree, Funga Sap and Chief's Spear retain specific world-item descriptors; Leather falls back to descriptor0 | Restoration needs item-by-item work, not one generic “enable unused items” switch |
| Math Bead11 has more world metadata than 12–15 | item77 selects descriptor89; items78–81 select descriptor0 | The surviving series is asymmetric, even though all five menu-use conditions are false |

“Added” means added to this project's research by this audit. It does not claim worldwide priority over every community discovery. The eel's appearance was already a supplied community lead; the retained pointer chain, native termination, missing item binding and regional control are the new checks here.

## Inputs, offsets and reproduction

These are SHA-1 fingerprints of **decoded assets**, except the complete PS-X executable and the already uncompressed overlays. Offsets into a GAM are offsets in its decoded stream, not raw BIN/sector offsets.

| Input | SHA-1 | Relevant location |
| --- | --- | --- |
| `SLPS_011.44` | `07d577698ad31ec1a69b9d7b80a7c3f90b650888` | load `80010000`; file offset = RAM − `80010000` + `800` |
| `SYSTEM/INFO2.BIN` | `15ea8894a028cdabdda577b32ddfd281e023f51b` | companion fingerprint of the existing JP audit profile |
| `AREA10/X10.BIN` | `e9280e20362a1be59df924bc4be2f769438d6ae7` | load `800E9AF8`; 283,868 bytes |
| `SYSTEM/DSPSUB.BIN` | `985875ab8ac54dc43f5ed88cfef75bfdf9608fc0` | same overlay load base; inventory-use policy |
| `AREA10/A003.GAM` SPR +`1EF7C` | `53c337d8a72ac14b0386dd7702e16b0da821f02e` | slot3, runtime SPR kind `33`, 196 frames |
| `AREA10/A003.GAM` WFM +`BA94` | `233a07817e1b1d903219130c8ae168220b93ac84` | item-use messages and Jungle dialogue |
| `AREA10/B003.GAM` GRPX +`0` | `648fac83861c8018bbf3556d619a2d1410c8e865` | upload `(768,0,256,256)` in VRAM words |
| `AREA10/CLUT01.GAM` +`0` | `c3a9f7e76057f4e7cfa41ed511e49f0faf915124` | upload `(128,480,256,32)` in VRAM words |

Run from the project root:

```powershell
python tools/audit_jp_unused_content.py "rom/Ore! Tomba (Japan).cue" --images
```

The read-only audit writes **`work/non_village_research/jp_unused_content.json`** and, with `--images`, **`work/non_village_research/eel-native-jp.png`**. The JSON includes 49 targeted item slots, original use messages, descriptor bytes/addresses, use-condition indices, frame parts, pixel hashes, reference-search coverage and native traces. These 49 slots include used comparison items; they are **not 49 newly proven unused items**. No game artwork is bundled with the tool.

Native checks execute original instructions in isolated memory. The item initializer and eel playback need no external service stubs. The hurt control records and stubs two sound services. None of these checks runs the full PSX game, proves a quest reachable, or assigns missing creature collision/AI.

The comparison baseline is the local `Tombi-Decomp` source checkout **`4220d8e1dc8635e51cbe33e2ca4588486786e796`** and cached `origin/master` **`44e814a6268f294f889ee77f5aad319f88e82a50`**. This records the exact inspected revisions, not an assertion about later remote commits. The user's modified `src/Rand.c` was not touched. The bundled editor reference snapshot remains separately identified in its manifest.

## Electric eel: graphics and script survive together

The loaded Jungle bank contains three recognisable eel images, not just the inventory icon. Each is a **32×16** single-part SPR frame, with draw offset **`(-16,-8)`**, U range **0–31** and V ranges **192–207**, **208–223**, **224–239** respectively.

All three parts carry the original **CLUT word `7B0C`**, meaning palette origin **`(192,492)`**. With page base **12**, their page word `0020` becomes `002C`: the texture origin is VRAM word **`(768,0)`**. That resolves directly into `AREA10/B003.GAM`. The supplied CLUT row is populated; the preview uses **neither a grey fallback nor an invented palette**.

In the decoded texture upload, the frames begin at byte offsets **`18000`**, **`1A000`**, **`1C000`**; each uses the first 16 bytes of each of 16 rows, with upload row stride `200` bytes. Their 16-colour palette begins at decoded CLUT-upload byte offset **`1880`**. These are upload-buffer offsets, not compressed-file seek positions.

The original animation survives in X10:

| RAM | X10 offset | Contents |
| --- | --- | --- |
| `8012DEB8` | `443C0` | pointer to `8012E0E0` |
| `8012E0E0` | `445E8` | frame33, box0, argument0, control `0008` |
| `8012E0E8` | `445F0` | frame34, box0, argument0, control `0008` |
| `8012E0F0` | `445F8` | frame35, box0, argument0, control `8008` |

The `8000` terminal bit matters. Original JP **`AnimLoadDuration` (`80020DE4`)** and **`AnimAdvance` (`80020E38`)** produce:

| Update | Current frame | Result |
| --- | --- | --- |
| 0 | 33 | first frame loaded |
| 8 | 34 | advances one eight-byte record |
| 16 | 35 | advances to terminal record |
| 24 | 35 | returns finished, holds last frame |
| 32 | 35 | returns finished again, still holds it |

There is **no loop pointer** after this script. Replaying it as a looping animation is an editor/presentation choice. A missing owner could also have restarted it, but no such eel owner was identified in this pass.

The checked upstream [CUT_CONTENT.md](https://github.com/afsenovilla/Tombi-Decomp/blob/44e814a6268f294f889ee77f5aad319f88e82a50/docs/CUT_CONTENT.md), under the Jungle survey, says no chief, eel or drum sprite was found. **The eel part of that negative conclusion is too broad for this JP dump.** This finding does not establish the chief's graphics or a distinct large drum graphic.

## Electric eel: the item binding is missing, not just its placement

JP **`initItemObject` is `8003D740..8003D9A3`** in the resident executable. The relevant search names and structure come from upstream [initItemObject.c](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/initItemObject.c); the addresses and results here are checked against JP bytes.

The native chain is:

1. Item subtype at object `+3` indexes the **200-byte table `80077BE4`**. JP lookup instruction: **`8003D794`**.
2. The selected byte indexes the **descriptor pointer table `80077CAC`**. JP load: **`8003D7A8`**.
3. A 20-byte descriptor supplies page, SPR slot, palette mode, box and animation-table pointer. The initializer assigns object `+24`, then loads its duration.

For **Electric Eel108 / `6C`**, the selected descriptor is **0**, at **`80077450`**. The same is true for Rubber Gloves59, Black Water109 and Funga Leather119. Native initialization with variant0 produces:

| Field | Native result |
| --- | --- |
| SPR slot | 4, the common item/effect bank |
| Page base | 21 |
| Palette | `7D56`, origin `(352,501)` |
| Animation table | `80011D2C` |
| Selected script | `80011F64` |
| Frame | 0, the generic berry graphic |
| Box words | `7,16,7,16` |

This is a **world-object initialization result**, not a claim that the inventory icon is a berry. Inventory icons and these world sprites are separate tables.

None of the **97 descriptors selected by the 200 item IDs** points to eel animation cell `8012DEB8`. In aligned full-word searches of resident MAIN and X10, the only pointer into the eel's 24-byte script is the cell `8012DEB8` itself. Those two files contain no aligned full-word pointer to that cell. A deliberately broad scan pairing every LUI with eligible low-half instructions in the following eight instructions also finds no candidate for the cell or script interior.

**Bound:** this is an unbound animation candidate in those searches, not a proof against every possible computed address. Other Jungle tables have indexed consumers. The existing item initializer definitely does not link inventory108 to these eel frames; an independent creature owner, its spawn rule, swimming motion, collision and capture transaction remain to be found or authored.

The menu policy is a separate surviving link. **Eel108 and Black Water109 both use condition22 at `80104E24` in DSPSUB**: area18, section2, player H coordinate **128..192**. This is a use-at-destination predicate, **not an eel spawn coordinate**. Rubber Gloves59 uses false condition0 at `801047F4`. Their intended supply chain therefore cannot be reconstructed by copying a single location predicate.

For the intended glove-giver context, see the [Gantetsu section of the cut-village report](cut-villages-jp-research.md#eel-warning-and-intended-glove-giver-gantetsus-iron-town-block): Iron entries245–247 discuss the eel, protection for bare hands, and both bomb materials. Entry246 has no recovered display selector or working glove grant. Do not turn its wording into a confirmed functional handover.

## Shock reaction: the PAL branch must not be assigned to JP

Upstream's shared [playerStepHurtKnockback.c](https://github.com/afsenovilla/Tombi-Decomp/blob/4220d8e1dc8635e51cbe33e2ca4588486786e796/src/x010/playerStepHurtKnockback.c) describes PAL X010 **`800FD358`, 2,084 bytes**. It checks object byte `+D1`; reason3 selects **animation `50` hex / 80 decimal**, waits60 updates, then continues ordinary damage recovery. This is a useful later-build lead for the community's shocked Tomba animation. It does not itself name an eel caller.

The corresponding **JP X10 routine is `800FCE48`, 1,492 bytes**, file offset **`13350`**. Its ordinary hurt entry loads **animation57** at **`800FD01C`**, stores it to the player's animation selector at **`800FD050`**, and invokes **`800EFD70`** when needed. It lacks that PAL reason3 branch and extra wait state.

JP selector `800EFD70`, X10 +`6278`, copies **74 pointers** from **`800E9E40`**, X10 +`348`. The loaded JP player's SPR bank has **366 frames**. All 74 script pointers decode against that bank. There is no index80 in that table. These are native regional counts; “animation80” must not be copied from PAL labels onto JP frames.

As a controlled check, the JP routine was run with a synthetic extension pointer, equal health values, state1, and object `+D1` set to 0, 1 and 3. All three select **animation57 → script `80011470`**, then reach state2. The two sound-service calls are the same: **`8001E388(23h,24h)`** and **`8001E2D4(1Fh)`**. They were recorded and stubbed; no audio identity was inferred from the numbers.

**Conclusion:** a generic shock branch survives in the inspected PAL source, while this JP hurt routine supplies no eel-specific reaction. This is not a whole-disc proof that no JP shock artwork or alternate handler exists. The pasted “eel zap” sound and shocked Tomba imagery still need a JP bank/sample/caller identification. No remote animation or sound was downloaded.

## Two placeholder items preserve stat-item wording

The community list calls two entries **Chick**, with placeholder pictures and uncertain roles. The PAL-oriented enum uses `ITEM_CHICK2` and `ITEM_CHICK3`. JP text gives a more useful lead, without proving those were their final inventory names.

| JP item slot | AREA10 WFM entry/use message | Literal meaning | Native menu and world metadata |
| --- | --- | --- | --- |
| 131 / `83` | `地下迷路の地図をつかった` | Used the Underground Labyrinth Map | false condition0; descriptor0 |
| 133 / `85` | `1UPをつかった` | Used 1UP | false condition0; descriptor0 |
| 134 / `86` | `ゲージMAX +1をつかった` | Used Gauge MAX +1 | false condition0; descriptor0 |
| 147 / `93` | `石炭をつかった` | Used Coal | false condition0; descriptor0 |

These messages are in **`AREA10/A003.GAM`, WFM +`BA94`**, entries equal to the item IDs. They form part of the common item-use message block. A use-message string does **not** prove a working effect. Native DSPSUB maps all four slots to **condition0 at `801047F4`**; native world selection maps all four to descriptor0 at `80077450`.

This also prevents cross-version naming errors: the inspected enum calls slot131 `ITEM_OVENBAKEDMUSHROOM` and slot147 `ITEM_TRASHCAN`, while these JP use messages explicitly describe a map and coal. For slots133/134, “1UP” and “Gauge MAX +1” are confirmed **residual message wording**, not confirmed implemented rewards. Which gauge, its limits and its intended acquisition remain unresolved.

## Funga materials and the drum's actual sprite alias

The following are **native world-item routes**, tested with X10 loaded where the overlay scripts can be read. A route does not prove that its expected pixels, placement, reward or crafting scene is present.

| Item | Descriptor | Native selected script/frame | Menu condition |
| --- | --- | --- | --- |
| Wood91 | 75, `80077A2C`; anim cell `8012DEC0` | `8012E108`, SPR3 frame38, page12 | false0 |
| Funga Leather119 | 0, `80077450` | `80011F64`, common SPR4 frame0 | false0 |
| Funga Tree122 | 73, `80077A04`; anim cell `8012DF14` | `8012E308`, SPR3 frame111, page13 | false0 |
| Funga Sap123 | 72, `800779F0`; anim cell `8012DEC8` | `8012E100`, SPR3 frame37, page12 | false0 |
| Chief's Spear140 | 74, `80077A18`; anim cell `8012DECC` | `8012E178`, SPR3 frame93, page12 | false0 |
| Funga Drum125 | 94, `80077BA8`; anim cell `80011E8C` | `80012598`, SPR4 frame197, page20 | condition41, `8010542C` |
| Small Drum137 | 61, `80077914`; same anim cell | same `80012598`, SPR4 frame197, page20 | false0 |

For the two drums, native initialization agrees on **script, frame, page and original CLUT `7D12`**, origin `(288,500)`. Their descriptors differ in exactly the four box bytes: Funga Drum **`08 10 08 10`**, Small Drum **`0C 0C 0C 0C`**. These become four halfwords at object `+6C..+72`. This is concrete aliasing; it does not prove an accidental name/sprite swap or identify the art of a separate large crafting drum.

Beside the Wood cell is **`8012DEC4 → 8012E110`**, which also holds **frame38**, rather than a different material frame. No selected item descriptor points to cell `8012DEC4`. That neighbouring pointer alone therefore cannot be assigned to Leather119 as a recovered binding.

The chief's already-known judgement dialogue is retained verbatim in the audit JSON: **entries188–195 = group2, lines11–18** in the same Jungle WFM. It distinguishes harming none of the Masakari from harming them, mentions a drum and dancing, and contains gibberish counterparts191/195. The inspected upstream report already traced these as unselected text; this pass does not claim a newly recovered chief actor, fortune algorithm, spear quest or drum recipe.

For reconstruction, preserve the distinction between **materials with routed world metadata**, **materials with only an inventory/text identity**, and **implemented recipe transactions**. The last of these has not been recovered here.

## Math Beads and numbered placeholders are not equally preserved

| Slots | Native world selector | Retained use-message behaviour |
| --- | --- | --- |
| 77 / `4D`, community Math Bead11 | descriptor89 at `80077B44`, animation table `80011EB8` | message77 says `エラーです` (“Error”) |
| 78–81 / `4E..51`, community Math Beads12–15 | descriptor0, `80077450` | each corresponding message says Error |
| 82–86 / `52..56`, community “Number Balls16–20” | descriptor0, `80077450` | each corresponding message says Error |

All ten use-condition indices are0, the false condition. This establishes an extra world descriptor for slot77, not a working eleventh bead quest. The JP use-message block does not validate the 16–20 names or their icons' intended roles; those labels stay attributed to the community lead. Icon palette correction and inventory-name mapping are separate investigations.

## Claim ledger for the other supplied leads

This ledger keeps the remaining material visible without promoting a pasted guess to a native finding. **Baseline** means already discussed in the inspected upstream report or the existing cut-village report; it is not a new exhaustive reachability check in this pass.

| Supplied lead | Current standing and next useful check |
| --- | --- |
| Lost Dwarf, Mighty Fish, Golden Bowl, Flower Tears, Grandpa's Bracelet as inventory items | Targeted IDs2/101/135/136/120 are exported. These can be used actors, pickups, rewards or end-state objects while an inventory representation remains unseen. Audit each inventory-add/display path before calling the underlying content cut. |
| Map and torn halves; Letter; Iron; Shovel; Coal | IDs25/57/58/90/61/97/147 exported with their native metadata. Where the halves, letter, shovel or iron were originally obtained is not established. Digger/cheese replacement stories remain guesses. Coal's JP identity is supported above. |
| Rain Essence | Baseline: menu condition16 at `80104CCC` permits AREA03 sections5/6. Descriptor32 is `800776D0`. This confirms retained location-specific policy, not rainfall, flame removal, an old cutscene or a Haunted Mansion origin. Trace the JP pending-item consumer and sound sample next. |
| Black Water and Coconuts as bomb ingredients | Black Water109 shares the eel's destination policy; Coconuts118 is exported. Gantetsu text supports the eel/black-water chain. A Dried Wishing Well pickup, coconut source and working recipe still need their own callers/placements. |
| Five coloured candies and thin/fat body types | Candy110–114 has five specific descriptors `80077928..80077978`, all using animation cell `80119608`, page8 and palette origins `(240,480..484)`; all five use conditions are false. No candy→body-type state transition is established. Status icons/strings alone cannot supply it. |
| Forbidden Mushroom, Chuckling/Weeping Mushroom | IDs116/128/129 exported. Forbidden Mushroom116 differs from many dormant items by using true condition1; that alone does not prove an effect. The relationship to eating world mushrooms needs the actual consumer. |
| Unusual Key and Iron Castle | Item127 has descriptor44 at `800777C0`, animation cell `80130DC8`. The keyhole theme is a lead. A specific lock, acquisition point or working door transaction is not recovered here. |
| Used items with unseen world sprites | Banana Juice, Big Key, Charles' Pants, Cold Medicine, Gold Candy, medals, fruit, keys, repaired mirror, pig bag, powders, wires, Weed Killer, Wine, Yan's lunch, hat and Molasses need per-reward display checks. “Never visibly materialises” is narrower than “unused item.” |
| Old Valve/Pipe | Baseline: used item64, an older out-of-bounds placement and palette quirks are already reported upstream. Keep it separate from genuinely unbound eel data. No new valve quest is claimed. |
| Eel event74; chief/language/secrets59–61; Doodle Rocks67; Green Fortune Teller89 | Retained titles, hints/icons and selected text are baseline leads. This pass adds the eel art/script chain, not new quest start/complete callers. The large pasted unused-event table is not evidence that all related graphics or dialogue are unreachable. |
| Event icon mismatches | Check event ID→frame mapping and regional SPR tables; the checked upstream report already distinguishes intended reuse from some community “wrong icon” interpretations. Do not remap icons just from the pasted names. |
| Pufferfish and Hermit Crab/Whelk animations | Still open. JP Trick Village SPR banks were inspected with multiple page bases, but no defensible frame/CLUT/handler identification was completed. This is not evidence that the art is absent. Need a local reference image or texture/part correlation, then animation and spawn references. |
| Masakari chief graphics; extra NPC animations; early Yan | Still open for native frame/page/CLUT/selector ownership. The new eel rendering does not establish these identities. A character using some frames does not make all its other frames unused. |
| Silver/gold berries, question bubbles, full16HP meter, final pig gate | Baseline or unverified graphics leads. Upstream reports the berry reward as2HP for nonzero variants, unlike the pasted1HP claim; that discrepancy needs a dedicated JP reward trace before assigning a JP number. Bubble shape alone does not establish retail use. |
| Growing flowers in the Elder's Hut | JP AREA02/D109.GAM +`1B88` and AREA19/D109.GAM +`BF0` share a34-frame SPR, SHA-1 `6d07e313d86089d7db0583e87f99a26c82ca39a3`; records27–32 survive. Parts alone do not recover the art. The exact intended page/palette and progression caller remain open here; the upstream PAL “empty pixels” result is not automatically a JP art result. |
| GoGoCart cacti/signs and extra track; Mansion metal sign; Doodle Rock sprites; Small Room masks; Factory boulder/house mask; Castle blown door | Preserve as separate geometry/texture/placement leads. The cacti/signs and Factory mask are already baseline subjects. This pass has not assigned new native object IDs or unreachable masks to the others. |
| Drowning, Rain Essence and eel sounds | No audio attached in the supplied text, and no remote media opened. Sample-bank IDs and live callers still need identification. Generic hurt sound calls above are not a recovered eel sound. |
| Demo item pictures, early AP door/rock, Pure8 events | Outside this **JP retail** evidence scope unless the same bytes or a concrete retail reference is found. Demo event names must not be treated as JP runtime quests. |

## Next investigations with the clearest payoff

1. **Find an eel owner, not another icon export.** Trace Jungle handler tables, bounded subtype indices, code-generated actors and WSS object creation against `8012DEB8`/frames33–35. Record any actual collision and inventory-add calls. Keep a swimming loop or glove test marked as authored unless a native caller supplies it.
2. **Trace JP stat-slot consumers.** Start from items133/134 in DSPSUB and pending-item handling, looking for health/lives/gauge writes. Their recovered messages justify this search but do not answer it.
3. **Separate the two drum identities at the inventory layer.** Check icons, names and item125's real consumer independently from the proven shared world sprite. Reconstruct material transactions only after locating native give/remove/complete operations.
4. **Identify the unverified creatures from actual texels.** For pufferfish, crab and chief, pin a local visual reference to one uploaded page and CLUT before naming a bank's frames or declaring them unused.
5. **Study Rain Essence's surviving destination code.** Use JP X03 plus DSPSUB condition16 to trace what happens after menu acceptance. Test any sound/cutscene claim against a real call and a named sample or event state.

The editor exposes this file in **JP retail research → Research and sources → TombaEdit: JP unused content beyond cut villages**. Findings are research context; this change does not silently mark every item, event, animation or text entry as confirmed unused.
