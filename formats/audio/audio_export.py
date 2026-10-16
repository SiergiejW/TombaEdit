"""Encode rendered audio without changing playback's WAV buffer."""
from io import BytesIO


def encode_audio(wav, suffix):
    if suffix == '.wav':
        return wav
    if suffix != '.ogg':
        raise ValueError('Choose WAV or OGG audio.')
    import soundfile
    samples, rate = soundfile.read(BytesIO(wav), dtype='float32', always_2d=True)
    output = BytesIO()
    soundfile.write(output, samples, rate, format='OGG', subtype='VORBIS',
                    compression_level=0.5)
    return output.getvalue()
