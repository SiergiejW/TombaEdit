"""Content-verified identities of the supplied Special Edition disc images.

The CAR files contain ordinary raw PlayStation sectors. Their names are
not a version identifier: engine selection continues to use executable
hashes, while this optional label identifies the complete source image.
"""
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class Edition:
    name: str
    region: str
    note: str


IMAGES = {
    (491953728, 'e0535e043d453f1f911a49dc3debec7f4dad4cb2f89e8512e3d38c4fb79fbe8e'): Edition(
        'Special Edition (Europe)', 'Europe',
        'European SCES-013.30 image with nine language engines.'),
    (280494816, 'e91422de60e7bfcf8ceee3be7bb9bfe8fa1a46dc27d3301885fdd8acac2086e5'): Edition(
        'Special Edition (Japan)', 'Japan',
        'Japanese localization based on the US retail engine (SCUS_942.36); '
        'this is a different build from the original Ore! Tomba Japanese retail disc.'),
    (279843312, '28e9ca2dd93915cba0eb0a39475b94471933b24b7bfb9cee7bf84f8d81b870bb'): Edition(
        'Special Edition (US)', 'US',
        'US image retaining the original US retail executable.'),
}


def identify(disc):
    """Return a known complete-image identity, or None; cache per disc session."""
    if '_special_edition' not in disc.__dict__:
        found = None
        if disc.source.suffix.lower() == '.car' and disc.byte_size in {size for size, _ in IMAGES}:
            digest = hashlib.sha256()
            with disc.path.open('rb') as stream:
                for block in iter(lambda: stream.read(8 << 20), b''):
                    digest.update(block)
            found = IMAGES.get((disc.byte_size, digest.hexdigest()))
        disc._special_edition = found
    return disc._special_edition
