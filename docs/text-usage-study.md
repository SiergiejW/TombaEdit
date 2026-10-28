# Local ROM text study — 28 October 2026

**Partial usage audit.** Unchecked entries do not mean used. Counts are native-profile candidates, not proof of impossibility. Event-table gaps remain unchecked until other display paths are resolved.

30 image paths, 15 distinct playable build/asset sets, 18 ZIP archives. Data tracks in 17 archives were CRC-verified against loose copies; the distinct Tomba-AR image was also inventoried.

| Build | Banks | Entries | Possibly unused | Unchecked | Undecoded entries | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Standalone demo - Japanese | 5 | 685 | not established | 658 | 0 | Partial |
| Yoi demo - Japanese | 5 | 685 | not established | 658 | 0 | Partial |
| Demo One 7 - English | 7 | 1506 | not established | 972 | 0 | Partial |
| PrePre 8 - Japanese | 1 | 71 | 32 | 0 | 2 | Partial |
| PrePre 9 - Japanese | 4 | 413 | not established | 188 | 0 | Partial |
| PrePre 9 patched - Japanese | 4 | 413 | not established | 188 | 0 | Partial |
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

PrePre 9: one CLEAR! title candidate per area bank, 136 display references, and 275 unresolved dialogue entries. The native selector was checked over 116 area/event/completion combinations.

Other builds include literal native-call/script references and event-title mapping. Computed selections, additional item/event paths and menus still need tracing. Their event-title mapping tables were studied where located, but those leads are not promoted to unused verdicts. The all-ROM usage audit is not finished.

The HTML report has per-bank details, source offsets, images/aliases and event-table research leads. Full machine-readable records are in studied.json.

PrePre 8: 32 candidates, 26 dynamic conversation selections and 13 display references. The remaining two undecoded entries contain dwarf-language symbol strings; 74 kanji readings are reconstructed.

PrePre 9 and patched Pure Pure 09: all 413 entries decode. The study now records 160 display references, 65 bounded dynamic script selections and 188 unchecked dialogue entries. All script talk-action arguments have finite variable-definition upper bounds, including branch/subroutine assignments; these bounds deliberately include branches whose triggers may be unreachable. Native shared notices, elder conversation branches and the savepoint table add further references.

CLEAR! is used through a fixed banner glyph table, even though no event-title mapping selects entry zero. Running native event-object construction with allocation enabled emitted all seven glyphs in AREA01 and AREA02. The earlier selector-only check omitted this path. Event-table gaps in other builds have likewise been withdrawn as unused candidates until their other display paths are checked. Their previous candidate counts must not be treated as valid all-game unused counts.

Pure 9 event-title colour was checked against the native title model: its textured front face uses CLUT 7D16, (352,500), loaded by the section. Its other cube faces are orange, consistent with the orange fill of this palette. Dialogue uses (352,483). The viewer now reads these palettes rather than borrowing the retail height-based constants.

The usage audit remains incomplete. In particular, INFO's object-supplied dialogue fields and remaining native selector state need tracing before the 188 unchecked Pure 9 entries can receive reliable classifications. No Japanese retail executable was identified locally; the folder named SLPS-01144_1998-02-03_Tombi NTSC Preview Version contains an English preview. Tomba-AR's modified font remains outside the Japanese/English decoding work.

The local detailed report is work/text-audit/summary.html, with machine-readable records in studied.json. Packaged evidence is guarded by executable, overlay, WSS-script, bank-content and binding hashes. Changing a script invalidates its precomputed study.
