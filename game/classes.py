"""Names for object classes.

A placed object's class is its APD layer and type, which pick the routine
that runs it. A routine in the executable, or in the first 2DE6C bytes every
area overlay shares, is the same thing in every area, and its name is listed
once. The rest of an overlay is the area's own, so those names go by area.
"""

# The same in every area.
SHARED = {
    (2, 0x02): 'Pig',
    (2, 0x07): 'Biting plant',
    (2, 0x0E): 'Chest',
    (3, 0x04): 'Nest',
    (4, 0x00): 'Pump tree',
    (4, 0x03): 'Swing',
    (4, 0x04): 'Pumpkin plant',
    (4, 0x07): 'Door',
    (4, 0x1A): 'Signpost',
    (5, 0x04): 'Pickup',
}

# By area, for the classes its own overlay code runs.
AREAS = {
    0: {
        (2, 0x01): 'Mushroom plant',
        (2, 0x04): 'Egg',
        (2, 0x08): 'Kokka bird',
        (2, 0x12): 'Frog',
        (3, 0x01): 'Fog',
        (3, 0x0A): 'Plant',
        (3, 0x11): 'Wind plant',
        (3, 0x14): 'Flame',
        (3, 0x24): 'Prickly plant',
        (4, 0x01): 'Climbing rock',
        (4, 0x02): 'Gas plant',
        (4, 0x06): 'Door plank',
        (4, 0x0D): 'Water',
        (5, 0x0B): 'Blue apple',
        (7, 0x02): 'Background piece',
    },
}

# What is known about a class beyond its name.
NOTES = {
    (2, 0x02): 'Asleep where it is placed.',
    (2, 0x07): 'An enemy; it stretches out to bite.',
    (4, 0x03): 'Tomba can swing right round it.',
    (4, 0x04): 'Can be climbed.',
    (5, 0x04): 'Apples and crystals; the variant picks which.',
    (0, 2, 0x04): 'Can be cracked open.',
    (0, 4, 0x01): 'Animated; can be climbed.',
    (0, 4, 0x02): 'Can be climbed.',
    (0, 4, 0x06): 'Can be stood on.',
    (0, 3, 0x14): 'Animated.',
    (0, 4, 0x0D): 'The surface of a pond.',
}


def class_name(area, layer, kind):
    """The name of a class in an area, or ''."""
    return AREAS.get(area, {}).get((layer, kind)) or SHARED.get((layer, kind), '')


def class_note(area, layer, kind):
    return NOTES.get((area, layer, kind)) or NOTES.get((layer, kind), '')
