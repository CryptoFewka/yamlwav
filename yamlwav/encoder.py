"""YAML → WAV encoder."""
import math
import struct
import wave

from .goertzel import AMPLITUDE, SAMPLE_RATE, SAMPLES_PER_CHAR, char_to_freq


def _parse_yaml(path: str) -> dict:
    """Hand-rolled parser for flat key: value YAML (no external dependencies)."""
    result = {}
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key:
                result[key] = value
    return result


def _encode_string(s: str) -> list:
    """Convert a string to a flat list of 16-bit PCM integer samples.

    Each character occupies exactly SAMPLES_PER_CHAR samples of a pure sine
    wave at the character's mapped frequency.
    """
    samples = []
    for ch in s:
        freq = char_to_freq(ord(ch))
        for i in range(SAMPLES_PER_CHAR):
            t = i / SAMPLE_RATE
            samples.append(int(AMPLITUDE * math.sin(2.0 * math.pi * freq * t)))
    return samples


def encode(yaml_path: str, wav_path: str) -> None:
    """Encode a flat YAML config file as a multi-channel WAV audio file.

    Channel 0 holds the key manifest (key names separated by null bytes).
    Channels 1..N each hold one config value, in the same order as the manifest.
    """
    config = _parse_yaml(yaml_path)
    keys = list(config.keys())

    manifest = "\x00".join(keys)
    channels = [_encode_string(manifest)]
    for key in keys:
        channels.append(_encode_string(config[key]))

    # WAV requires all channels to have the same frame count — pad with silence.
    max_len = max(len(ch) for ch in channels)
    padded = [ch + [0] * (max_len - len(ch)) for ch in channels]

    n_channels = len(padded)

    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        # Interleave: frame 0 of ch0, frame 0 of ch1, ..., frame 1 of ch0, ...
        interleaved = bytearray()
        for frame_idx in range(max_len):
            for ch in padded:
                sample = max(-32768, min(32767, ch[frame_idx]))
                interleaved += struct.pack("<h", sample)
        wf.writeframes(bytes(interleaved))


def encode_dict(data: dict, wav_path: str) -> None:
    """Encode a plain dict (string keys and string values) as a WAV file.

    Values are converted to strings via str() before encoding.
    """
    keys = list(data.keys())
    manifest = "\x00".join(keys)
    channels = [_encode_string(manifest)]
    for key in keys:
        channels.append(_encode_string(str(data[key])))

    max_len = max(len(ch) for ch in channels)
    padded = [ch + [0] * (max_len - len(ch)) for ch in channels]
    n_channels = len(padded)

    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        interleaved = bytearray()
        for frame_idx in range(max_len):
            for ch in padded:
                sample = max(-32768, min(32767, ch[frame_idx]))
                interleaved += struct.pack("<h", sample)
        wf.writeframes(bytes(interleaved))
