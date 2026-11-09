# Cut Content Research

Discover surviving pieces of Tomba’s removed or unfinished ideas. Pictures are decoded from the disc you opened; no game artwork is bundled with the editor. The evidence below is for **Japanese retail, Ore! Tomba (SLPS-01144)** unless a different build is named. An asset surviving on the disc does not by itself prove that it can be encountered during ordinary play.

Choose a topic on the left, scroll through the discoveries, or use the tabs for town plans, residents, animations and events. The full research reports and source documents are available in the list above.

## The lost Civilization towns

**Lumberjack Town, Stonetown and Iron Town** retain resident positions, dialogue routines and movement data. The joined town also has surviving layout data. Their missing graphics and original behavior have not all been recovered, but their plans can be explored in the editor.

[Open Lumberjack Town](tomba://village/11) · [Open Stonetown](tomba://village/16) · [Open Iron Town](tomba://village/17) · [Open the reunited town](tomba://village/18)

Iron Town retains a lift with six boarding stops, and passage movement scenes. Their existence does not identify every passage with a specific town. Residents also have preserved dialogue, including a discussion of an electric eel and protective gloves. The cut-town-specific NPC lines are marked **confirmed unused** in the text viewer; shared lines can also be used elsewhere.

## Electric eel and rubber gloves

A three-frame eel survives in the Jungle sprite bank, along with its native animation script and a populated palette. The display below repeats the sequence for viewing; the surviving script holds its last frame and does not contain a loop. The eel's creature owner, capture behavior and glove handover have not been recovered.

![Electric eel animation](fig:eel)

[Open the eel sprite bank](tomba://asset/eel) · [Open Jungle dialogue](tomba://file/AREA10/A003.GAM) · [Open Iron Town](tomba://village/17)

The inventory eel does not select the recovered eel animation through the tested world-item initializer. The preserved warning about gloves is a story lead, not proof of a working quest.

## The Masakari Chief

The Japanese disc retains chief frames in two distinct Jungle sprite banks: SPR 32FF (slot 2, D005.GAM +02A24C) and SPR 37FF (slot 7, D005.GAM +02B814). The picture shows slot 2 frames; it is a frame gallery, not a recovered animation sequence. Dialogue candidates discuss judging the player's treatment of the Masakari and mention a drum. Their complete reachability has not been established.

![Masakari chief poses](fig:chief)

**Colour note:** the chief is shown with a stored palette as a useful preview. His intended runtime palette is unknown, so these colours are provisional.

[Open chief SPR 32FF](tomba://asset/chief) · [Open related SPR 37FF](tomba://asset/chief-alt) · [Open Jungle dialogue](tomba://file/AREA10/A003.GAM)

## Palette examples

These are the actual 16-colour palette rows used in the eel and chief previews. A dark square represents a transparent zero colour. The eel palette is supported by the native sprite data; the chief row is a provisional display choice.

![Eel and chief palette colours](fig:palettes)

## Funga materials, drum and spear

Several proposed drum materials and the Chief's Spear retain item data and world-sprite selections. Funga Drum and Small Drum select the same world image in the tested initializer. Leather selects a generic graphic. The spear renders blank in this preview; the tree image has not been confirmed as its intended appearance. These selections do not establish a crafting recipe or spear quest.

![Item graphics selected by the game](fig:funga)

[Open item sprite bank SPR 3](tomba://asset/funga) · [Open common sprite bank SPR 4](tomba://asset/beads) · [Open Jungle files](tomba://file/AREA10/A003.GAM)

## Extra number beads

A further numbered item has its own world-sprite descriptor. Other nearby numbered slots select a generic graphic; their names, intended purpose and acquisition are not all established. The compared slots return an error message when used.

![Number bead and generic graphic](fig:beads)

[Open the common sprite bank](tomba://asset/beads)

## Doodle Rocks and the tunnel symbols

Numbered rock graphics and related dialogue survive in several places. Some rock models occur in retail levels; texture evidence alone does not prove where every design was placed. A tunnel texture also contains a grid of number and picture symbols.

![Tunnel symbol sheet](fig:tunnel)

The symbol sheet is displayed with a **grey ramp** because its intended palette has not been established. Open the Doodle Rocks tab for the dialogue and location leads.

[Open the tunnel texture](tomba://asset/tunnel)

## Other surviving clues

The game also retains old movement routines, item and event records, and an 8 × 8 system font. The system texture preview includes nearby graphics as well as font characters. A surviving routine may be unreferenced without proving that every possible indirect caller is absent. The event-location reference is based on **PAL retail**; its locations should not automatically be treated as Japanese equivalents.

![System font](fig:debugfont)

[Open the system font texture](tomba://asset/debugfont) · [Open the Japanese executable](tomba://file/SLPS_011.44)

## Sources and deeper research

The detailed reports retain source files, addresses, functions, translations, and the limits of each investigation. They draw on the opened disc, TombaEdit's own analysis, community research and [Alberto's Tombi-Decomp project](https://github.com/afsenovilla/Tombi-Decomp). Select a detailed report above for the complete evidence.
