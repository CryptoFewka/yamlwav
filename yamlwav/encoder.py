"""YAML → WAV encoder."""
import io
import math
import struct
import wave
import zipfile

from .goertzel import AMPLITUDE, SAMPLE_RATE, SAMPLES_PER_CHAR, char_to_freq

# Fixed timestamp used in the zip archive so output is byte-for-byte deterministic.
_ZIP_DATE_TIME = (2020, 1, 1, 0, 0, 0)


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


def _build_wav_bytes(channels: list) -> bytes:
    """Interleave channel samples and return raw WAV file bytes."""
    max_len = max(len(ch) for ch in channels)
    padded = [ch + [0] * (max_len - len(ch)) for ch in channels]
    n_channels = len(padded)

    interleaved = bytearray()
    for frame_idx in range(max_len):
        for ch in padded:
            sample = max(-32768, min(32767, ch[frame_idx]))
            interleaved += struct.pack("<h", sample)

    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(interleaved))
    return buf.getvalue()


def _write_output(wav_bytes: bytes, wav_path: str, compress: bool) -> None:
    """Write wav_bytes to wav_path, optionally wrapping in a zip archive."""
    if compress:
        info = zipfile.ZipInfo("data.wav", date_time=_ZIP_DATE_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(wav_path, "w") as zf:
            zf.writestr(info, wav_bytes)
    else:
        with open(wav_path, "wb") as fh:
            fh.write(wav_bytes)


def _serialize_config(keys: list, values: list) -> str:
    """Serialize key-value pairs into a v2 delimited stream.

    Format: \\x02 + key1\\x00value1\\x01key2\\x00value2\\x01...
    \\x02 prefix marks v2 format. \\x00 separates key from value within a pair.
    \\x01 separates pairs from each other.
    """
    pairs = [f"{k}\x00{v}" for k, v in zip(keys, values)]
    return "\x02" + "\x01".join(pairs)


def _stereo_channels(stream: str) -> list:
    """Split a serialized stream into left/right stereo channels."""
    left = stream[0::2]
    right = stream[1::2]
    return [_encode_string(left), _encode_string(right)]


def encode(yaml_path: str, wav_path: str = None, compress: bool = False) -> None:
    """Encode a YAML config file as a stereo WAV audio file.

    Data is serialized into a single stream and split across left and right
    channels, encoding two characters simultaneously for doubled throughput.

    If wav_path is not given, the output path is yaml_path + ".wav" (e.g.
    "config.yaml" → "config.yaml.wav").

    Pass compress=True to wrap the output in a zip archive. Decoders
    auto-detect the format, so the choice is transparent to decode() and
    WavConfig callers.
    """
    if wav_path is None:
        wav_path = yaml_path + ".wav"
    config = _parse_yaml(yaml_path)
    keys = list(config.keys())
    values = [config[k] for k in keys]

    stream = _serialize_config(keys, values)
    channels = _stereo_channels(stream)

    _write_output(_build_wav_bytes(channels), wav_path, compress)


def encode_dict(data: dict, wav_path: str, compress: bool = False) -> None:
    """Encode a dict as a stereo WAV file. Nested dicts are supported and
    flattened to dot-notation keys (e.g. {"db": {"host": "x"}} → key "db.host").

    Values are converted to strings via str() before encoding.

    Pass compress=True to wrap the output in a zip archive.
    """
    data = _flatten_dict(data)
    keys = list(data.keys())
    values = [str(data[k]) for k in keys]

    stream = _serialize_config(keys, values)
    channels = _stereo_channels(stream)

    _write_output(_build_wav_bytes(channels), wav_path, compress)
