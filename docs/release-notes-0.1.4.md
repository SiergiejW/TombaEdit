# TombaEdit 0.1.4

Changes since **0.1.3**.

## Translations

- All Japanese builds were translated again with Tomba's own context: the names in each message (the Witch, the Evil Pigs, Koma Buta, the Seal Bag, the 10,000-Year-Old Man, the items and places) are given to the model from `formats/text/glossary_ja.json`, so the Witch is no longer a demon.
- Every message of the retail disc, and the messages the demos and samplers have besides, was read against the model's draft and the English release and corrected where it was wrong. The corrections were made by Claude, an AI model, not by a human translator, so they are still machine translation. The 1,549 corrected texts are in `tools/manual_translations.json` and apply to every build.
- The Dwarf language (Japanese with some letters replaced by symbols) is translated from its plain-Japanese twin where there is one, and is Dwarf gibberish, as in the US release, where there is not.
- Names: Megumi Fountain, Megumi Statues and Megumi Plaza (not a lady), Doodle Rock, Dashing, Blasting and Idaten Pants. The short log lines read "Used the Map", "Put on the Normal Pants".
- Lines are cut into the same number of boxes as the original.

## Japanese retail text

- Eleven wrong glyph readings were corrected and 24 more shapes were read (732 to 756), from the Tomba Club community's spreadsheet (Dada, vervalkon, Folkin) and from words that made no sense: 魔女 for 魔王, 小犬 for 小鳥, 迷宮, 閉, 休, 潰, 材, 全, 道 and more. The cross, triangle and square button tiles are told apart.
- Every glyph of every Japanese disc has a reading except four Dwarf-language symbols on PrePre Vol. 8 whose artwork is blank on the disc.

## Dialogue viewer

- Discs and banks that are already English show a single pane, labelled **English (original)**, with no translation machinery.
- New markers in the entry list: **Confirmed unused · cut village** (blue) and **Shared text · reference elsewhere**, each with its own filter, and counts in the summary line. A confirmed cut-village entry, a shared entry or one with a speaker candidate shows the evidence above its script, including the town, NPCs and routine.
- The *Cut-village research* menu is now *JP retail research*. Its reports show the sprites they describe, drawn from the opened disc: the electric eel animated with its retail timing, the Masakari Chief's candidate frames, and the Funga materials and drum. Each has a button that opens the sprite bank, and file names in the reports link to the file in the disc tree. This needs the audited Japanese retail disc.
- The English preview's 7 and Q were wrong glyphs; they are the game's own now. The game's single z serves for z and Z, so "amazing" no longer mixes in a bold z.

## Cut villages and levels

- Props show their draw order (Y-sorted, fixed depth) in the table and the tooltip.
- The cut-village tables wrap long text and let the text column stretch.
- Packed sprite pieces are aligned to four bytes, as the game's loader does, which fixes pieces after the first of a container.

## Research and tools

- New research notes: the unused content of the Japanese retail disc, the event map, and the save format and save editor.
- New audit scripts for cut-village residents, orphans and state, and for unused Japanese content.
