"""Goertzel algorithm for frequency detection and shared audio constants."""
import math

SAMPLE_RATE = 44100
SAMPLES_PER_CHAR = int(SAMPLE_RATE * 0.15)  # 6615
AMPLITUDE = 26214  # ~80% of 32767
SILENCE_THRESHOLD = 1_000_000  # well below a real tone's magnitude


def char_to_freq(byte_val: int) -> float:
    """Map a byte value (0-255) to a frequency in Hz."""
    return 200.0 + byte_val * 25.0


def goertzel(samples, target_freq: float, sample_rate: int = SAMPLE_RATE) -> float:
    """Evaluate the DTFT magnitude of samples at target_freq using the Goertzel algorithm.

    Unlike the standard DFT-bin form, this evaluates at the exact frequency
    rather than rounding to the nearest bin, giving clean discrimination between
    the 25 Hz-spaced tones used by yamlwav.
    """
    w = 2.0 * math.pi * target_freq / sample_rate
    cos_w = math.cos(w)
    sin_w = math.sin(w)
    coeff = 2.0 * cos_w
    s1 = s2 = 0.0
    for s in samples:
        s0 = s + coeff * s1 - s2
        s2, s1 = s1, s0
    real = s1 - s2 * cos_w
    imag = s2 * sin_w
    return math.sqrt(real * real + imag * imag)


def detect_char(window, sample_rate: int = SAMPLE_RATE) -> int:
    """Return the byte value (0-255) whose frequency dominates this audio window.

    Returns 0 (null byte) if the window appears to be silence.
    """
    best_mag = -1.0
    best_byte = 0
    for b in range(256):
        mag = goertzel(window, char_to_freq(b), sample_rate)
        if mag > best_mag:
            best_mag = mag
            best_byte = b
    if best_mag < SILENCE_THRESHOLD:
        return 0
    return best_byte
