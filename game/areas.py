"""User-supplied area/section names. Unknown entries deliberately keep their IDs."""
AREAS = dict(enumerate([
    "Village of All Beginnings", "Dwarf Forest", "Dwarf Village", "Phoenix Mountain",
    "Haunted Mansion", "Baccus Village", "Motocross Segment", "Dwarf Forest (purified)",
    "Baccus Lake", "Mushroom Village", "Deep Jungle", "Village of Civilization",
    "Haunted Mansion (purified)", "Pig Island", "Evil Pigs", "Unused",
    "Village of Civilization (Clock Tower)", "Village of Civilization (Iron Tower)",
    "Village of Civilization (Y Crossing)", "Hidden Village",
]))
SECTIONS = {
    0: ["Village of All Beginnings", "Forest of All Beginnings", "Forest of All Beginnings (hut entrance)", "100 Year Old Man's Hut", "Behind the Hut", "Ol' Pond"],
    1: ["Forest of 100 Flowers", "Forest of 100 Flowers (right entrance)", "Wobbly Wharf", "Watch Tower", "Charity Square"],
    2: ["Dwarf Village", "Dwarf Elder's Hut", "Underground Prison", "Underground Maze", "Million Year Old Man's Room", "The Strange Small Room"],
    3: ["Stormy Mountain", "Stormy Mountain (second part)", "Lava Caves", "Phoenix's Nest", "Stormy Mountain (purified)", "Stormy Mountain (purified, second part)"],
    4: ["North Side of Mansion", "West Side of Mansion", "South Side of Mansion", "East Side of Mansion", "Sunny Room", "Thief's Room One", "Swimming Room", "Keyhole Room", "Hiding Room", "Room of Tribulation", "Laughing Room", "Civilization Room", "Trap Room", "Trick Room", "Sun Torch Stand", "1,000 Year Old Man's Room", "Shadow Room", "Thief's Room Two", "Thief's Room Three", "Crying Room"],
    5: ["Baccus Village", "Central Park", "Baccus Village", "Central Park"],
    6: ["Dirt Motocross", "The Mermaid's Singing Rock (beach)", "The Mermaid's Singing Rock (mermaid)"],
    8: ["Baccus Pier", "Baccus Lake", "Baccus Pier", "Baccus Lake"],
    9: ["Mushroom Forest", "Lake", "Mansion (Grandfather clock room)", "Mansion (Chandelier room)", "Mansion (descending stairs)", "Mansion (ascending stairs)", "Leaf Slider"],
    10: ["Masakari Jungle", "Masakari River", "Old Tree Hill", "Trick Village", "Masakari Jungle (purified)", "Masakari River (purified)", "Old Tree Hill (purified)", "Trick Village (purified)", "10,000 Year Old Man's Room"],
    11: ["Lumberjack Town (crash / soft lock)", "Lumberjack Factory", "Dried Wishing Well"],
    13: ["Outer Walls of Pig Island (Flower Tower)", "Year Old Men Ending"],
    14: [f"Evil Pig area {i}" for i in range(1, 9)],
    16: ["Stonestown (soft lock)", "Clock Tower (soft lock)", "Clock Tower (crash)", "Clock Tower (Engine room)", "Clock Tower (Entrance)", "Clock Tower (Halfway up)", "Clock Tower (Engine room, no exit)"],
    17: ["Iron Town (crash)", "Iron Castle (entrance)", "Iron Castle (main room)", "Iron Castle (left room)", "Iron Castle (right room)", "Iron Castle (engine room)", "Iron Castle (soft lock)", "Iron Castle (soft lock)", "Iron Castle (crash)", "Iron Castle (soft lock, Y Crossing music)", "Iron Castle (soft lock, Witch's Hut music)"],
    18: ["Village of Civilization (crash / soft lock)", "Y Crossing", "Witch's Hut"],
    19: ["Dwarf Elder's Hut", "Dwarf Elder's Hut", "Hidden Village"],
}
SECTIONS[7] = SECTIONS[1]
SECTIONS[12] = SECTIONS[4]


def section_name(area, index):
    names = SECTIONS.get(area, [])
    return names[index] if 0 <= index < len(names) else "Additional load entry"
