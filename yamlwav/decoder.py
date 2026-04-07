"""WAV → dict decoder."""
import struct
import wave

from .goertzel import SAMPLE_RATE, SAMPLES_PER_CHAR, detect_char


def _decode_channel(samples) -> str:
    """Decode a sequence of audio samples into a string.

    Splits into SAMPLES_PER_CHAR-sized windows, detects the dominant frequency
    in each window, and converts the result to a character. Trailing null bytes
    (silence padding) are stripped from the result.
    """
    result = bytearray()
    for start in range(0, len(samples) - SAMPLES_PER_CHAR + 1, SAMPLES_PER_CHAR):
        window = samples[start : start + SAMPLES_PER_CHAR]
        result.append(detect_char(window, SAMPLE_RATE))
    # Decode as latin-1 so all 256 byte values survive the round-trip.
    return result.decode("latin-1").rstrip("\x00")


def decode(wav_path: str) -> dict:
    """Decode a yamlwav WAV file back to a dict of string key-value pairs."""
    with wave.open(wav_path, "r") as wf:
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        sample_width = wf.getsampwidth()
        raw = wf.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"Expected 16-bit PCM, got {sample_width * 8}-bit")

    # De-interleave: layout is [ch0_f0, ch1_f0, ..., chN_f0, ch0_f1, ...]
    total_samples = n_channels * n_frames
    all_samples = struct.unpack(f"<{total_samples}h", raw)
    channels = [all_samples[c::n_channels] for c in range(n_channels)]

    # Channel 0: key manifest — key names separated by null bytes.
    manifest = _decode_channel(channels[0])
    keys = [k for k in manifest.split("\x00") if k]

    result = {}
    for i, key in enumerate(keys):
        ch_idx = i + 1
        if ch_idx >= n_channels:
            break
        result[key] = _decode_channel(channels[ch_idx])

    return result
