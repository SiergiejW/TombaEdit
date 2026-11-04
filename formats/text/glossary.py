"""Names and terms of Tomba! for the translation model: what to tell it about a message before it translates.

formats/text/glossary_ja.json holds the terms (how the Japanese writes one, how the English should) and a few
fixes for words the game itself misspells. `user(text, inline=True)` is the request in the form the model was
trained on, with the names written into the message in English; `system(text)` is the context and the list of names
for a model that needs them said in an instruction.
"""
import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).with_name('glossary_ja.json')
LIMIT = 14      # most terms listed for one message: a long list drowns the message

CONTEXT = ('You translate Japanese text from the PlayStation game Tomba! (Japanese title: Ore! Tomba) into English: '
           'dialogue, signs, item names and menu text of a fairy-tale platformer in which a wild boy named Tomba '
           'fights the Evil Pigs and the Witch. Translate what the Japanese says, as natural English in the voice '
           'of the speaker. The Japanese is broken into short lines only where the game wraps its text box: join '
           'the lines of a sentence into one, and keep a blank line wherever the Japanese has one, because it '
           'starts a new box. Answer with the translation only.')


@lru_cache(maxsize=4)
def load(path=None):
    data = json.loads(Path(path or PATH).read_text(encoding='utf8'))
    terms = sorted(((t['ja'], t['en']) for t in data.get('terms', ())), key=lambda pair: -len(pair[0]))
    return data.get('fixes', {}), terms


def normalise(text, path=None):
    """The text with the game's own misspellings put right (what the model should read)."""
    fixes, _ = load(path)
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text


def terms_in(text, path=None):
    """[(ja, en)] for the terms the text contains, longest first, a term inside a longer one left out."""
    _, terms = load(path)
    found, covered = [], normalise(text, path)
    for ja, en in terms:
        if ja in covered:
            found.append((ja, en))
            covered = covered.replace(ja, '\0' * len(ja))
    return found[:LIMIT]


def with_terms(text, path=None):
    """The text with each term of the glossary already written in English, where the Japanese has it: a model
    that is only told a name often writes its own (Demon Pig for 魔ブタ), one that reads it in the sentence keeps it."""
    text = normalise(text, path)
    for ja, en in terms_in(text, path):
        text = text.replace(ja, en)
    return text


def system(text, path=None):
    found = terms_in(text, path)
    if not found:
        return CONTEXT
    return CONTEXT + '\nWrite these names and terms in English exactly like this:\n' + '\n'.join(f'{ja} = {en}' for ja, en in found)


_ENDS = tuple('。.!?!?▼・…〜~」』)）')


def joined(text):
    """The text with the lines of a sentence joined: the game breaks its lines to fit a box, mid-sentence, and a
    model translates one sentence better than a sentence cut in three. A line that ends a sentence (or the
    ellipsis, or the box's arrow), and a blank line, keep their break."""
    pages = []
    for page in text.split('\n\n'):
        lines = page.split('\n')
        out = [lines[0]]
        for line in lines[1:]:
            if out[-1].rstrip().endswith(_ENDS) or not line.strip() or line[:1] in ' 　' or not out[-1].strip():
                out.append(line)
            else:
                out[-1] += line
        pages.append('\n'.join(out))
    return '\n\n'.join(pages)


def user(text, path=None, inline=False):
    """The request: the message (with the glossary's names written in English if `inline`) and nothing else."""
    return 'Translate the following Japanese text into English.\n\n' + joined(with_terms(text, path) if inline else normalise(text, path))


def pages(text):
    """How many boxes (blank-line separated parts) a message has."""
    return max(1, len([part for part in text.split('\n\n') if part.strip()]))


def clean(value, text):
    """The answer for `text` as many boxes as the message has: a model that goes on after its translation, to
    repeat itself or to talk about its instructions, is cut off there. '' when what is left is not a translation."""
    value = '\n\n'.join(value.strip().split('\n\n')[:pages(text)]).strip()
    import re
    quoted = re.search(r'translates? to:?\s*\n?\s*"(.+?)"\s*$', value, re.S)
    if quoted and pages(text) == 1:
        value = quoted.group(1).strip()      # 'The Japanese text "..." translates to: "..."'
    if (any(mark in value for mark in ('Write these names', 'You translate Japanese', 'fairy-tale platformer', 'natural English',
                                       'translates to', 'Japanese text', 'already in English', 'text you provided',
                                       'meaning of', "Here's the English", 'Here is the English'))
            or re.match(r'\s*Japanese\s*:', value)):
        return ''
    return value


def untranslated(text, value):
    """True when the answer still has Japanese words in it though the message has some to translate."""
    import re
    words = r'[ぁ-ゖァ-ヺ一-鿿]'
    return re.search(words, text) is not None and re.search(words, value) is not None


def ran_away(text, value):
    """True for an answer far longer than its message, or the same line over and over: the model lost its way."""
    import re
    return (len(value) > 6 * max(len(text), 6) + 40 or re.search(r'(.{3,40}?)\1{4,}', value) is not None
            or re.search(r'(.)\1{11,}', value.replace('.', '')) is not None)
