# yamlwav standalone decoder — copy-paste boilerplate
#
# Paste the `decode_yamlwav` function below into your own Python file.
# It requires only the Python standard library (wave, struct, math).
# No pip install needed.
#
# Usage:
#   config = decode_yamlwav("config.wav")
#   print(config["port"])   # -> "8080"  (all values are str)


def decode_yamlwav(wav_path: str) -> dict:
    """Decode a yamlwav WAV file back to a dict of string key-value pairs.

    Requires only Python stdlib — safe to paste into any project without
    adding a dependency.

    Args:
        wav_path: Path to a WAV file produced by yamlwav's encoder.

    Returns:
        dict[str, str] mapping each config key to its string value.
    """
    import math
    import struct
    import wave

    SAMPLE_RATE = 44100
    SAMPLES_PER_CHAR = 6615       # int(44100 * 0.15) — samples per character
    SILENCE_THRESHOLD = 1_000_000  # below this magnitude → treat as padding

    def _goertzel(samples, freq):
        """Return the DTFT magnitude of samples at the given frequency (Hz)."""
        w = 2.0 * math.pi * freq / SAMPLE_RATE
        cos_w = math.cos(w)
        coeff = 2.0 * cos_w
        s1 = s2 = 0.0
        for s in samples:
            s0 = s + coeff * s1 - s2
            s2, s1 = s1, s0
        real = s1 - s2 * cos_w
        imag = s2 * math.sin(w)
        return math.sqrt(real * real + imag * imag)

    def _detect_char(window):
        """Return the byte value (0-255) whose tone dominates this audio window."""
        best_mag = -1.0
        best_byte = 0
        for b in range(256):
            freq = 200.0 + b * 25.0   # encoding: freq = 200 + byte * 25
            mag = _goertzel(window, freq)
            if mag > best_mag:
                best_mag = mag
                best_byte = b
        return best_byte if best_mag >= SILENCE_THRESHOLD else 0

    def _decode_channel(samples):
        """Decode a list of audio samples into a string."""
        result = bytearray()
        for start in range(0, len(samples) - SAMPLES_PER_CHAR + 1, SAMPLES_PER_CHAR):
            window = samples[start : start + SAMPLES_PER_CHAR]
            result.append(_detect_char(window))
        # latin-1 so all 256 byte values survive the round-trip
        return result.decode("latin-1").rstrip("\x00")

    with wave.open(wav_path, "r") as wf:
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        sample_width = wf.getsampwidth()
        raw = wf.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"Expected 16-bit PCM, got {sample_width * 8}-bit")

    # De-interleave: WAV layout is [ch0_f0, ch1_f0, ..., chN_f0, ch0_f1, ...]
    total_samples = n_channels * n_frames
    all_samples = struct.unpack(f"<{total_samples}h", raw)
    channels = [all_samples[c::n_channels] for c in range(n_channels)]

    # Channel 0 is the key manifest: key names joined by null bytes
    manifest = _decode_channel(channels[0])
    keys = [k for k in manifest.split("\x00") if k]

    result = {}
    for i, key in enumerate(keys):
        ch_idx = i + 1
        if ch_idx >= n_channels:
            break
        result[key] = _decode_channel(channels[ch_idx])

    return result


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "examples/sample_config.wav"
    config = decode_yamlwav(path)
    for k, v in config.items():
        print(f"{k}: {v}")
