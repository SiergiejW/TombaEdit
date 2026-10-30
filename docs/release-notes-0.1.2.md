# TombaEdit 0.1.2

Changes since **0.1.1** (commit `f30df88`, 29 October 2026).

## Premade translations (no model needed)

- Japanese text now comes with English. Each known build has its own file in `formats/text/translations/`: `japanese-retail.json`, `japanese-demo.json`, `sampler-japanese-demo.json`, `sampler-japanese-demo-dengeki-d5.json`, `pure-pure-09-sampler.json`, `sampler-pure-pure-09-sampler.json` and `prepre-vol-8.json`. Together they translate 2,096 different messages with CAT-Translate 7b.
- Each file lists the build's messages in disc order under `entries` and the same messages bank by bank under `banks` (bank, file, offset, entry index, original, translation), so builds can be compared with any other tool.
- A disc of a known build reads its own file first, then the other files, so the demos and samplers also find the text they share with the retail disc. The info line says how many messages of the open disc are covered and whether the build is recognised.
- The dialogue viewer now shows each message twice, side by side: **Original**, drawn in the game's own font, and **English**, drawn with the fallback letters.
- A new **Display** menu chooses *Original and English side by side*, *Original only* or *English only*, switches the premade translations on and off, and keeps the model options: **Translate every message in the background** and **Choose a model...**. Model translation works exactly as before, and the choices are remembered.
- The filter and the Export/Search/Display buttons moved above the two panes.
- New `tools/make_translations.py` makes the files. It translates only what has no translation yet, can be stopped and started again, keeps a local cache (`rom/translator/translation-cache-ja.json`, not part of the repo), restarts the model after a graphics-card error, redoes answers in which the model ran away line by line (`--repair`), and rewrites the files without translating (`--files-only`). About 400 messages that still contain unknown glyphs are left for a later run.

## Japanese retail text

- 626 more glyphs of the Japanese release were read (`formats/text/glyphs_jp.json`), most of them kanji, in the 12 x 12, 10 x 10 and 20 x 20 title fonts. Entries that decode completely went from 56.8% to 96.5% (6,459 of 6,690), and glyph slots without a character from 27.2% to 1.8%.
- Remaining `[gNNN]` glyphs are icons drawn in the text and about 30 shapes whose reading is not certain.

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

- Every 2D view (pictures, sprite sheets, the VRAM view, collision planes, placement maps and the 2D level view) has **+**, **-** and **Fit** buttons at its top right.
- **Fit** no longer leaves a scroll bar that changes the fitted size.

## Fixes

- A translation model that finished loading after its pane was closed no longer closes the program; the result goes to the console.
- A backdrop picture too large for the graphics card is scaled down instead of failing inside the paint routine.
- `main.spec` now packages `glyphs_jp.json` and the translation files.
