# Local ROM text study — 28 October 2026

**All-ROM audit: partial. Pure Pure 09 / PrePre 9: static selector coverage checked for all 413 entries.** Unchecked entries do not mean used. Counts are native-profile candidates, not proof of impossibility. Event-table gaps remain unchecked until other display paths are resolved.

30 image paths, 15 distinct playable build/asset sets, 18 ZIP archives. Data tracks in 17 archives were CRC-verified against loose copies; the distinct Tomba-AR image was also inventoried.

| Build | Banks | Entries | Possibly unused | Unchecked | Undecoded entries | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Standalone demo - Japanese | 5 | 685 | not established | 658 | 0 | Partial |
| Yoi demo - Japanese | 5 | 685 | not established | 658 | 0 | Partial |
| Demo One 7 - English | 7 | 1506 | not established | 972 | 0 | Partial |
| PrePre 8 - Japanese | 1 | 71 | 32 | 0 | 2 | Partial |
| PrePre 9 - Japanese | 4 | 413 | 138 | 0 | 0 | Static selectors checked |
| PrePre 9 patched - Japanese | 4 | 413 | 138 | 0 | 0 | Static selectors checked |
| Euro Demo / Winter Releases - English | 7 | 1506 | not established | 972 | 0 | Partial |
| Unidentified | 0 | 0 | 0 | 0 | 0 | No structured text banks |
| Standalone demo - English | 11 | 2202 | not established | 1620 | 0 | Partial |
| Toys R Us / Jampack - English | 11 | 2202 | not established | 1620 | 0 | Partial |
| Hyper PlayStation Re-mix 12 - Japanese | 2 | 80 | not established | 54 | 0 | Partial |
| Dengeki D5 - Japanese | 5 | 685 | not established | 658 | 110 | Partial |
| February 1998 preview - English | 46 | 9411 | not established | 6107 | 11 | Partial |
| Retail - English (US) | 48 | 9971 | not established | 6326 | 0 | Partial |
| Retail - English (Europe) | 41 | 8542 | not established | 5337 | 0 | Partial |
| Tomba-AR - modified US build | 48 | 9971 | not established | 6280 | 9434 | Partial |

PrePre 8: 32 candidates, 26 dynamic conversation selections retained as potentially used, 13 display references. 74 kanji readings are reconstructed, not bitmap recognition. The remaining two undecoded entries contain dwarf-language symbol strings.

Other builds include literal native-call/script references and event-title mapping. Computed selections, additional item/event paths and menus still need tracing. Their event-title mapping tables were studied where located, but those leads are not promoted to unused verdicts. The all-ROM usage audit is not finished.

The HTML report has per-bank details, source offsets, images/aliases and event-table research leads. Full machine-readable records are in studied.json.

Pure Pure 09 / PrePre 9, both original and patched images: **160 display references, 115 conservative dynamic selections, 138 possibly-unused candidates, zero unchecked entries**. AREA01 has 29 candidates and AREA02 has 109; both 30-entry title banks have display references, including CLEAR! through its fixed glyph table. The status in the viewer is Usage checked (static selectors).

The completed pass accounts for the native window constructors and every loaded caller, branch-selected IDs, all 19 signpost/savepoint records, item/event notice mappings, all seven WSS programs and their variable-definition bounds, and the event-title/completion paths. Native R3000A execution checked 96 INFO actor action/substate/timer combinations: the computed selector is confined to action 3. No local script requests that action, the actor helpers only reset actions to zero, and no APD places these script actors outside their checked creation path. The other INFO selector belongs to an unreferenced helper. Those facts close the two previously unresolved object-field paths.

For negative findings, the selector bounds deliberately retain the union across all loaded script/overlay contexts, rather than assuming that a particular scene or branch is reachable. The 115 dynamic entries are potentially selected, not proven used. The 138 unmatched entries are **Possibly unused**, not proof about every hypothetical game state. Missing glyphs and translation output never determine usage.

The shipped metadata validates the executable, overlays, WSS scripts, APD placement lists, WFM bytes and load bindings. Editing native code, a script or an APD invalidates the completed Pure 9 study instead of retaining stale candidate counts. Reproduce the checks with:

```powershell
python -m formats.text.prepre9_study "rom/prepatched pure9/Pure Pure 09.cue"
```

An independent candidate review separates bank copies from distinct text content:

| Candidate comparison | Entry copies |
| --- | ---: |
| Same decoded text as an entry with a display reference | 33 |
| Same decoded text as a conservative dynamic selection | 3 |
| Text found only among unmatched copies | 102 |
| Total possibly-unused entry copies | 138 |

Those 102 unmatched copies contain 92 distinct decoded messages. Equality here compares original visible text; control codes and presentation can differ. A duplicate does not prove the candidate copy is selected, and a static display reference does not prove its trigger is reachable. **Zero entries are confirmed never shown in-game.** The 138 count must not be described as 138 messages that never appear.

Independent R3000A execution of the native item/event notice selector checked all 288 valid area/kind/item combinations, recording the allocated window's actual entry ID. None selected a candidate. Stream-pointer checks found no shared entry pointers or truncated entry decoding. A scan including the Tomba `.000` files found no additional valid WFM banks or WSS programs; apparent script headers inside the menu overlays declare sizes beyond the available bytes. These checks strengthen the candidate evidence but do not replace complete gameplay reachability analysis or an emulator trace. No full DuckStation playthrough has been verified for this conclusion.

Direct runtime evidence was added on 28 October from the user-supplied `work/PCPX-96093_1.sav` (SHA-256 `c83718ef4cc0a3ee4dcfb5a4787f2f9fe127370ea42724b5b65a2324e835cfd3`). It matches the patched executable's selector routines and patch code, and is in AREA02 section 01. Dialogue window `800AC2D0` reads stream `8014F2C0`, inside entry **095**, from the byte-identical `TOMBA/AREA02/A003.GAM@4E14` bank loaded at `80148E14` in text slot 0. The running game's visible dwarf dialogue matches the decoded entry. This entry now says **Observed in-game** in the patched-image viewer's usage evidence; its underlying referenced status and all candidate counts are unchanged. This observation is not transferred to the original image as a gameplay observation. Slots 2 and 3 are zero in this scene. All 16 dialogue CLUT words at (352,483) match the editor's AREA02 reconstruction exactly. This validates that palette in this scene, not every palette or scene. Reproduce the saved-state extraction with `python work/pure9_state_text_check.py work/PCPX-96093_1.sav`; its JSON output is `work/pure9-live-text-evidence.json`.

Generate a reviewable UTF-8 JSON report containing every candidate's source, bank offset, zero-based viewer entry number, original text, selector evidence and matching entries:

```powershell
python -m formats.text.prepre9_study "rom/prepatched pure9/Pure Pure 09.cue" --candidate-report work/pure9-candidate-evidence.json
```

Pure 9 event-title colours use the native title model's CLUT 7D16, (352,500), loaded with the section. Its other cube faces are orange, matching this palette's fill. Dialogue uses (352,483).

For emulator verification, use a digital controller for the PrePre 9 sampler menu. Its `MAIN.EXE` reader at `8002C3C8`, called at `8002C544`, reads the pad buffer at `801A71B8` and rejects a controller whose ID's upper nibble is not 4. Native execution with Start, Cross and Circle pressed returned the expected buttons for digital ID `41`, and zero buttons for analog IDs `73` and `53` in all nine cases. This establishes the menu reader's compatibility restriction; it does not establish the controller's current runtime mode. After changing controller type, boot the disc afresh so a loaded save state cannot retain its previous device mode. The local reproduction is `python work/pure_sampler_input_verify.py`.

Other ROM builds still have partial selector coverage; their unchecked entries are not treated as used or possibly unused. The Japanese retail disc (`SLPS_011.44`, `Ore! Tomba (Japan)`) has 51 text banks and 7,858 entries, including the item and event description banks in `DSPSUB`/`DSPSUB3` and a second pair in `AREA19/D208.GAM` that no load table names. The 46 banks of the load tables are audited by `python -m formats.text.jp_retail_study "rom/Ore! Tomba (Japan).cue" --write-index`: every message-window call and the helpers that pass a message on (argument values over all paths of each function), the signposts each area places, the scripts' talk actions, the item and event notice tables and the info actors. The audit is complete for the area dialogue banks of 22 banks and leaves open AREA02 and AREA19 (script talk selectors with unbounded operands) and AREA12 (its event table lies outside the loaded overlay); 547 entries are possibly unused and 517 stay unchecked, mostly the event-title banks and those open areas. The DSPSUB menus open only text slots 2 and 3, so the item and event description banks and `D208.GAM` are not covered. A contributor's list of Japan-only text, compared with the PAL release, is a different question: of its 148 entries in the area banks, the audit finds 81 possibly unused and 57 reached, with 10 in AREA02 unchecked. The reached ones are AREA00's tutorial signs (by signposts), the lines of AREA16 and AREA18 that a generic NPC routine opens, and the residents' lines of the three cut Civilization villages: their dialogue routines in the INFO2 overlay open 34 of those entries, but the villages' sections are never loaded and no exit leads into them, so the evidence says so. The folder named SLPS-01144_1998-02-03_Tombi NTSC Preview Version contains an English preview. Tomba-AR's modified font remains outside Japanese/English decoding coverage.

The detailed local report is work/text-audit/summary.html; machine-readable records are in studied.json. The reproducible Pure 9 audit implementation is formats/text/prepre9_study.py.

## Unused events

The list of event hints in DSPSUB (`DSPSUB @124C8` on the Japanese retail disc: 200 entries, the entry of an event
being its own number) is checked against `formats/text/unused_events.json`, the 24 events that the event research
found nothing starts or completes: 22 never started or started only in cut content (the cut villages), and two that
start in retail and end in cut content or the other way round. Their entries are marked **Unused event** in the same
purple as possibly unused text, listed under the "Possibly unused" filter and counted in the tree, and the tooltip
gives the event's English and Japanese title, what triggers it, what starts and completes it and the research's note.
The research searched every executable and overlay of the PAL and Japanese releases for `setEventStarted`,
`awardEventProgress` and the event flags; it is a search, not proof, and the list is data to correct as it is
corrected. Source: https://claude.ai/artifact/LKgNAn4dYnArqoQtcupY48
