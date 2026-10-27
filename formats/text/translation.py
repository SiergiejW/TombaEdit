"""Japanese-to-English translation from a local Argos model directory.

Only CTranslate2 and SentencePiece are used. No package manager, remote
service or automatic resource download runs while translating dialogue.
"""
import json
import re
import threading
import atexit
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path


class TranslationError(ValueError):
    pass


def model_metadata(folder):
    root = Path(folder)
    try:
        metadata = json.loads((root / 'metadata.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise TranslationError('Choose an extracted Argos Japanese-to-English model folder containing metadata.json.') from exc
    if (metadata.get('from_code'), metadata.get('to_code')) != ('ja', 'en'):
        raise TranslationError('This model must translate Japanese (ja) to English (en).')
    if not (root / 'model' / 'model.bin').is_file() or not (root / 'sentencepiece.model').is_file():
        raise TranslationError('The model folder needs model/model.bin and sentencepiece.model.')
    return metadata


def translatable(text):
    if re.search(r'\[g[0-9A-Fa-f]+\]', text):
        raise TranslationError('Some glyphs are still unknown. Set their characters in the Glyphs tab before translating this entry.')
    return bool(re.search(r'[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]', text))


class LocalTranslator:
    def __init__(self, folder):
        metadata = model_metadata(folder)
        try:
            import ctranslate2
            import sentencepiece
        except ImportError as exc:
            raise TranslationError('Offline translation components are not installed. See README: Offline Japanese translation.') from exc
        self.tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(Path(folder) / 'sentencepiece.model'))
        self.engine = ctranslate2.Translator(str(Path(folder) / 'model'), device='cpu', compute_type='int8',
                                            inter_threads=1, intra_threads=2)
        self.prefix = metadata.get('target_prefix', '')
        self.cache = OrderedDict()

    def translate(self, text):
        if text in self.cache:
            self.cache.move_to_end(text)
            return self.cache[text]
        paragraphs = []
        # Game layout line breaks often split one sentence. Keep page breaks,
        # join wrapped lines, and split long inputs rather than truncate them.
        for paragraph in re.split(r'\n\s*\n', text):
            paragraph = paragraph.replace('\n', '').strip()
            if not paragraph:
                continue
            pieces = []
            for sentence in re.findall(r'.+?(?:[。！？!?]+|$)', paragraph):
                tokens = self.tokenizer.encode(sentence, out_type=str)
                pieces.extend(tokens[i:i + 256] for i in range(0, len(tokens), 256))
            translated = self.engine.translate_batch(pieces, beam_size=4, max_input_length=0,
                max_decoding_length=512, replace_unknowns=True,
                target_prefix=[[self.prefix]] * len(pieces) if self.prefix else None)
            lines = []
            for result in translated:
                tokens = result.hypotheses[0]
                if self.prefix and tokens and tokens[0] == self.prefix:
                    tokens = tokens[1:]
                lines.append(self.tokenizer.decode(tokens).strip())
            paragraphs.append(' '.join(lines))
        result = '\n\n'.join(paragraphs)
        self.cache[text] = result
        if len(self.cache) > 1024:
            self.cache.popitem(last=False)
        return result


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _translator(folder):
    return LocalTranslator(folder)


def translate(folder, text):
    if not translatable(text):
        return text
    with _lock:
        return _translator(str(Path(folder).resolve())).translate(text)


def _serve(connection):
    """Keep native language libraries out of Qt's Windows DLL environment."""
    try:
        while True:
            folder, text = connection.recv()
            try:
                result = translate(folder, text)
            except Exception as exc:
                result = f'Translation unavailable: {exc}'
            connection.send(result)
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


class TranslationWorker:
    def __init__(self):
        self.process = self.connection = None
        self.lock = threading.Lock()
        atexit.register(self.close)

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            if self.process.pid is not None:
                self.process.join(timeout=1)
            self.process.close()
            self.process = None

    def translate(self, folder, text):
        import multiprocessing
        import time
        with self.lock:
            if self.process is None or not self.process.is_alive():
                self.close()
                context = multiprocessing.get_context('spawn')
                self.connection, child = context.Pipe()
                self.process = context.Process(target=_serve, args=(child,), daemon=True)
                try:
                    self.process.start()
                except Exception:
                    self.close()
                    raise
                finally:
                    child.close()
            try:
                self.connection.send((folder, text))
                deadline = time.monotonic() + 60
                while not self.connection.poll(.1):
                    if not self.process.is_alive():
                        raise TranslationError('The local translation process stopped. Select the entry again to retry.')
                    if time.monotonic() >= deadline:
                        raise TranslationError('The local translation model took too long. Try a shorter entry.')
                return self.connection.recv()
            except (EOFError, BrokenPipeError, TranslationError) as exc:
                self.close()
                raise TranslationError(str(exc) or 'The local translation process stopped.') from exc


worker = TranslationWorker()
