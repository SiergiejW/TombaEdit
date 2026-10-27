"""Japanese-to-English translation with user-selected CAT or Argos models.

Inference uses local files in a separate process, without remote services
or automatic resource downloads.
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
    if (root / 'config.json').is_file():
        try:
            config = json.loads((root / 'config.json').read_text(encoding='utf8'))
            index = root / 'model.safetensors.index.json'
            shards = set(json.loads(index.read_text(encoding='utf8'))['weight_map'].values()) if index.is_file() else {'model.safetensors'}
            if not shards or any(Path(name).name != name or not (root / name).is_file() for name in shards):
                raise ValueError('missing safetensors weights')
            if not (root / 'tokenizer.json').is_file() or config.get('model_type') != 'mistral':
                raise ValueError('expected a CAT-Translate-7b tokenizer and Mistral model')
            return dict(backend='cat', config=config)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise TranslationError(f'The local CAT-Translate folder is incomplete: {exc}.') from exc
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


class CatTranslator:
    """User-selected, local safetensors CAT-Translate-7b; never fetch code."""
    def __init__(self, folder):
        model_metadata(folder)
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
        except ImportError as exc:
            raise TranslationError('Install requirements-translation-cat.txt to use a CAT-Translate safetensors model.') from exc
        torch.set_num_threads(2)
        self.torch = torch
        weights = sum(path.stat().st_size for path in Path(folder).glob('*.safetensors'))
        self.tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
        options = dict(local_files_only=True, trust_remote_code=False, use_safetensors=True,
                       low_cpu_mem_usage=True, dtype=torch.float16 if torch.cuda.is_available() else torch.float32)
        if torch.cuda.is_available():
            # Leave space for generation and other applications. Accelerate
            # can keep the remaining layers in system RAM when necessary.
            free, _ = torch.cuda.mem_get_info()
            import psutil
            options.update(device_map='auto', max_memory={0: max(0, free - 1024 ** 3),
                           'cpu': int(psutil.virtual_memory().available * .6)})
            if free < weights + 1024 ** 3:
                try:
                    import bitsandbytes
                    from transformers import BitsAndBytesConfig
                except ImportError as exc:
                    raise TranslationError('Free more GPU memory, or install bitsandbytes for low-memory GPU translation.') from exc
                if free < 5 * 1024 ** 3:
                    raise TranslationError(f'CAT-Translate-7b needs about 5 GB of free GPU memory; '
                        f'{free / 1024 ** 3:.1f} GB is currently free. Close a GPU-heavy application '
                        'or project, then select this entry again to retry.')
                options['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True,
                    bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float16)
                options['device_map'] = {'': 0}
        else:
            import psutil
            if weights * 2 > psutil.virtual_memory().available * .85:
                raise TranslationError('Not enough free RAM for CPU translation. Install CUDA-enabled PyTorch '
                                       'for your GPU, or free memory before loading this model.')
        self.model = AutoModelForCausalLM.from_pretrained(folder, **options).eval()
        self.cache = OrderedDict()

    def translate(self, text):
        if text in self.cache:
            self.cache.move_to_end(text)
            return self.cache[text]
        prompt = 'Translate the following Japanese text into English.\n\n' + text
        inputs = self.tokenizer.apply_chat_template([dict(role='user', content=prompt)],
                    add_generation_prompt=True, return_tensors='pt', return_dict=True)
        if inputs['input_ids'].shape[1] > 4096:
            raise TranslationError('Select a shorter dialogue entry (up to 4096 input tokens).')
        inputs = {key: value.to(self.model.device) for key, value in inputs.items()}
        with self.torch.inference_mode():
            result = self.model.generate(**inputs, max_new_tokens=1024, do_sample=False, use_cache=True,
                         pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id)
        value = self.tokenizer.decode(result[0, inputs['input_ids'].shape[1]:], skip_special_tokens=True).strip()
        self.cache[text] = value
        if len(self.cache) > 1024:
            self.cache.popitem(last=False)
        return value


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _translator(folder):
    return CatTranslator(folder) if model_metadata(folder).get('backend') == 'cat' else LocalTranslator(folder)


def translate(folder, text):
    if not translatable(text):
        return text
    with _lock:
        return _translator(str(Path(folder).resolve())).translate(text)


def _serve(connection):
    """Keep native language libraries out of Qt's Windows DLL environment."""
    import os
    import sys
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    os.environ.setdefault('MKL_NUM_THREADS', '2')
    if sys.platform == 'win32':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS
    try:
        while True:
            folder, text = connection.recv()
            try:
                if model_metadata(folder).get('backend') == 'cat':
                    import sys
                    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
                    # Keep the optional runtime portable with the selected
                    # model, rather than tying it to one ROM folder spelling.
                    candidates = (Path(folder).resolve().parent / 'runtime',
                                  root / 'rom' / 'translator' / 'runtime',
                                  root / 'roms' / 'trnslator' / 'runtime')
                    runtime = next((path for path in candidates
                                    if (path / 'torch' / '__init__.py').is_file()), None)
                    if runtime is not None and str(runtime) not in sys.path:
                        sys.path.insert(0, str(runtime))
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
        self.folder = None
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
            if not self.process.is_alive():
                self.process.close()
            self.process = None
        self.folder = None

    def translate(self, folder, text):
        import multiprocessing
        import time
        with self.lock:
            folder = str(Path(folder).resolve())
            if self.process is None or not self.process.is_alive() or self.folder != folder:
                self.close()
                context = multiprocessing.get_context('spawn')
                self.connection, child = context.Pipe()
                self.process = context.Process(target=_serve, args=(child,), daemon=True)
                try:
                    self.process.start()
                    self.folder = folder
                except Exception:
                    self.close()
                    raise
                finally:
                    child.close()
            try:
                self.connection.send((folder, text))
                deadline = time.monotonic() + 300
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
