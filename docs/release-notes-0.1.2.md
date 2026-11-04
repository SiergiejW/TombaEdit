# TombaEdit 0.1.2

Changes since **0.1.1** (commit `f30df88`, 29 October 2026).

## Premade translations (no model needed)

- Japanese text now comes with English. Each known build has its own file in `formats/text/translations/`: `japanese-retail.json`, `japanese-demo.json`, `sampler-japanese-demo.json`, `sampler-japanese-demo-dengeki-d5.json`, `pure-pure-09-sampler.json`, `sampler-pure-pure-09-sampler.json` and `prepre-vol-8.json`. Together they translate 2,257 different messages: CAT-Translate 7b made the drafts and 1,549 of them were then corrected by Claude, an AI model (see Translation context).
- Each file lists the build's messages in disc order under `entries` and the same messages bank by bank under `banks` (bank, file, offset, entry index, original, translation), so builds can be compared with any other tool.
- A disc of a known build reads its own file first, then the other files, so the demos and samplers also find the text they share with the retail disc. The info line says how many messages of the open disc are covered and whether the build is recognised.
- The dialogue viewer now shows each message twice, side by side: **Original**, drawn in the game's own font, and **English**, drawn with the fallback letters. The English has a frame for each frame of the original (a blank line in the translation is where the box clears), and a frame whose English is longer than the original's grows taller instead of spilling into extra frames.
- A new **Display** menu chooses *Original and English side by side*, *Original only* or *English only*, switches the premade translations on and off, and keeps the model options: **Never load the translation model** (nothing is queued or started, a model that is still loading is stopped, and the choice is remembered), **Translate every message in the background** and **Choose a model...**. Model translation works exactly as before, and the choices are remembered.
- The filter and the Export/Search/Display buttons moved above the two panes.
- New `tools/make_translations.py` makes the files. It translates only what has no translation yet, can be stopped and started again, keeps a local cache (`rom/translator/translation-cache-ja-glossary.json`, not part of the repo), restarts the model after a graphics-card error, redoes answers in which the model ran away line by line (`--repair`), and rewrites the files without translating (`--files-only`). Messages that still contain an unread glyph (2 on PrePre Vol. 8) are left for a later run.

## Translation context

- Every Japanese build was translated again, this time with the context the first run lacked. The names a message contains are written in English into the sentence the model reads, from `formats/text/glossary_ja.json`: 魔王 is the Witch, not a demon king, 魔ブタ the Evil Pig, コマブタ Koma Buta, マゴブタ Mago Buta, 封印ぶくろ the Seal Bag, the 10,000-Year-Old Man, Wood, Stone and Iron People, and the items and places. Japanese-sounding names stay Japanese-sounding. (Telling the model the names in an instruction worked less well: it often wrote its own, and short messages made it talk about the instruction.)
- The glossary was made from the English release: the text of the Japanese and the US retail discs was lined up (entry by entry, by the controls and numbers of each message and the sizes of the lines), and the English names of items and places were read from the pairs. The translation itself is still of the Japanese.
- The lines of a sentence that the game broke to fit its box are joined before the model reads them, so "フンガの大タイコをつくる / 材料じゃないか?" is one question and not two fragments. A blank line (a new box) stays one, so the English has a frame for each frame of the original.
- Words the game itself misspells (不思識, 村人全表, 博土) are put right for the model, and an answer that runs on, talks about the task, or leaves the Japanese in is asked for again with the message as it is, and then with the game's context and the names listed beside it. The answer is cut after as many boxes as the message has.
- Every message of the retail disc was then read against the model's draft and the English release, and the translation was corrected by Claude, an AI model and not a human translator, wherever the draft was wrong: mistranslations, merged or dropped boxes, item and quest names, cries that the model turns into endless repeats ("oh dear oh dear..."). The Dwarf-language lines, which are Japanese with some letters replaced by symbols, are translated from their plain-Japanese twin where one exists and are Dwarf gibberish (as in the US release) where not. The 1,549 corrected texts are in `tools/manual_translations.json`, which the tool applies over the model's answers for every build, so the demos and samplers get them too. The messages that exist only on the demos and samplers went through the same two readings. Only the placeholder lines ("アイテム033", "イベント012") were left as they are.
- The translating tool uses a new local cache, `rom/translator/translation-cache-ja-glossary.json`; the old cache is not read.

## Japanese retail text

- 732 glyphs of the Japanese release were read (`formats/text/glyphs_jp.json`), most of them kanji, in the 12 x 12, 10 x 10 and 20 x 20 title fonts. Every one of the retail disc's 7,598 entries with text now decodes completely, and each of its 10,897 glyph slots has a character. The 渡 of "死神の実を渡すため…" is the one reading that rests on the sense of the sentence more than on the shape.
- The readings were checked against the hand-made spreadsheet of the Tomba Club community (Dada, vervalkon and Folkin). Sixteen more shapes were corrected from it: 魔女 for 魔王 (the villain is the Witch), 小犬 for 小鳥 (Baron is a puppy), 迷宮 (read 迷路), 閉 (read 開: the doors close), 使 (read 合), 休 (read 体), 潰 (read 渡: crush the Reaper Fruit), 消 (read 通), 教 (read 救), 父 (read 両), 共 (read 達), 込 (read 囲), 事 (read 切), the arrow ← (read ◀) and the title font's 女. The cross, triangle and square button tiles, which differ only in their palette indices, are told apart now, so △ and □ no longer read as ×.
- Ten glyphs that had been read as a look-alike were corrected, found where the Japanese made no sense and checked against the US release: 材 (read 村: 材料, 木材, 鉄材, 素材), 全 (read 代: 全部, 全体), 特 (read 持), 上 (read 先: 湖上, 頂上), 合 (read 張: 場合), 道 (read 方: 近道, 道具, 抜け道), 辺 (read 道: 浜辺), 海 (read 近: 海草), 密 (read 窓: 密林) and 着 (read 若: 着替え).
- Every glyph of every Japanese disc has a reading except four Dwarf-language symbols on PrePre Vol. 8, whose artwork is blank on the disc (two entries). PrePre Vol. 8's tile-cut "Thank You" and "Bye-Bye" lettering is read as whole runs.
- Event titles of the Japanese retail disc are drawn with the disc's own palette (black-edged letters on orange tiles, as in the game), not the guessed one that showed them as white letters with orange speckles. The dialogue font reads its palette from the disc too. Pure 9 already did.

## Unused events

- The 24 events that the event research found nothing starts or completes are marked **Unused event** in the list of event hints (`DSPSUB`, 200 entries, the entry being the event's number), in the same purple as possibly unused text. They are listed under the "Possibly unused" filter and counted in the tree. The tooltip gives the English and Japanese title, what triggers the event, what starts and completes it, and the research's note. The data is `formats/text/unused_events.json`.

## Cut villages

- Section 0 of AREA11, AREA16, AREA17 and now AREA18 is shown in a **Cut village** tab, the first tab of the section and the one that opens. The section is blue in the tree and ends in "(unused area)".
- The plan draws the houses, walking boxes, props, residents and, from the research, the exits of each village, which can be selected like a house.
- Click a resident, prop, house or exit on the plan to select it, and a row of the table to see it on the plan; click empty space to deselect. A line under the plan says what is selected.
- Residents are drawn as figures from the sheets on the disc, in the palettes of the `CLUT` files that the research named, solid where the page of the subtype survives and translucent where it is lost. The Sprites panel shows every sprite, page and palette (with counts); its building pages are shown grey, because their palette is on no disc.
- Buttons take you to the text entry, the sprite sheet, the palette file or the overlay code of the selected resident.
- Opening the tab, or selecting a row, translates that village's lines first. The English column fills in as translations arrive.
- A background picture of your own can be drawn under the plan and placed with X, Y, scale and opacity; it is remembered for each village.
- The houses read from the overlay match the research's rectangles for all three villages.

## Models and levels

- Untextured model faces are lit from the normals they store (**Light From Normals**, on by default); objects placed in a level keep their normals and turn them with the object, and faces with zero normals keep their colour. The light direction is an estimate. A selected polygon says whether it is raw-textured, shaded or lit.
- The back view of the Stonetown strongman's head is placed over its body.
- The level editor's object list now shows the class before the scene object.
- APD placement maps draw objects as they are, without 50% opacity.
- Backdrop panoramas no longer show a one-pixel line at the join of repeats (AREA00 sections 01 and 02, AREA10), and are drawn at whole pixels in one wrapped rectangle.

## Interface

- The resource trees show only the name and the label: the size and the SPR and ANIM review columns are hidden (the marks are kept). The Label column opens at 20% of the tree's width and cannot be dragged below 15%; the name column takes the rest.
- The buttons of the Cut village tab (**Open text entry**, **Open sprite sheet**, **Open palette file**, **Open overlay code**) and **Load background picture...** are large and bold, in pink, yellow, blue, green and purple pastels. A button that does not apply to the selection is the same colour, faded.
- **Open sprite sheet** opens the VRAM tab of the sheet's load group, where the sheet is a picture, not the empty level editor.
- The sprite panel of the Cut village tab shows the figures and the buildings side by side, each with its own palette choice.

- Every 2D view (pictures, sprite sheets, the VRAM view, collision planes, placement maps and the 2D level view) has **+**, **-** and **Fit** buttons at its top right.
- **Fit** no longer leaves a scroll bar that changes the fitted size.

## Fixes

- A translation model that finished loading after its pane was closed no longer closes the program; the result goes to the console.
- A backdrop picture too large for the graphics card is scaled down instead of failing inside the paint routine.
- `main.spec` now packages `glyphs_jp.json` and the translation files.
- The English preview's 7 and Q were wrong glyphs in the saved 16 pixel font; they are now the game's own. The game has one z, drawn small, and the preview uses it for z as well as Z, so "amazing" no longer mixes in a bold z from another size.
