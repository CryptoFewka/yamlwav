"""YAML → WAV encoder."""
import math
import struct
import wave

from .goertzel import AMPLITUDE, SAMPLE_RATE, SAMPLES_PER_CHAR, char_to_freq


def _parse_yaml(path: str) -> dict:
    """Hand-rolled parser for key: value YAML supporting arbitrary nesting.

    Nested keys are flattened to dot-notation (e.g. db.host, db.port).
    No external dependencies.
    """
    result = {}
    prefix_stack = []  # list of (indent_level, dotted_prefix)
    with open(path, "r") as fh:
        for line in fh:
            raw = line.rstrip("\n")
            stripped = raw.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in stripped:
                continue
            indent = len(raw) - len(stripped)
            while prefix_stack and prefix_stack[-1][0] >= indent:
                prefix_stack.pop()
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            full_key = f"{prefix_stack[-1][1]}.{key}" if prefix_stack else key
            if value:
                result[full_key] = value
            else:
                prefix_stack.append((indent, full_key))
    return result


def _flatten_dict(d: dict, prefix: str = "") -> dict:
    """Recursively flatten a nested dict to dot-notation keys."""
    result = {}
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_dict(v, full_key))
        else:
            result[full_key] = v
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
    """Encode a dict as a WAV file. Nested dicts are supported and flattened
    to dot-notation keys (e.g. {"db": {"host": "x"}} → key "db.host").

    Values are converted to strings via str() before encoding.
    """
    data = _flatten_dict(data)
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
