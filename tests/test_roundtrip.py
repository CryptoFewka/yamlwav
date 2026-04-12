"""Roundtrip tests for yamlwav encode/decode."""
import io
import math
import os
import string
import struct
import sys
import tempfile
import wave
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from yamlwav import WavConfig, decode, encode, encode_dict


def test_roundtrip_basic_types(tmp_path):
    """String, int, float, bool, and null values survive encode → decode → WavConfig."""
    wav = str(tmp_path / "config.wav")
    data = {
        "host": "localhost",
        "port": "8080",
        "ratio": "3.14",
        "debug": "true",
        "flag": "false",
        "nothing": "null",
    }
    encode_dict(data, wav)
    cfg = WavConfig(wav)

    assert cfg["host"] == "localhost"
    assert cfg["port"] == 8080
    assert cfg["ratio"] == pytest.approx(3.14)
    assert cfg["debug"] is True
    assert cfg["flag"] is False
    assert cfg["nothing"] is None


def test_roundtrip_all_printable_ascii(tmp_path):
    """All printable ASCII characters survive an encode → decode cycle intact."""
    wav = str(tmp_path / "ascii.wav")
    printable = string.printable.strip()  # remove surrounding whitespace chars
    data = {"chars": printable}
    encode_dict(data, wav)
    result = decode(wav)
    assert result["chars"] == printable


def test_type_coercion(tmp_path):
    """WavConfig applies correct type conversions."""
    wav = str(tmp_path / "types.wav")
    encode_dict(
        {
            "an_int": "42",
            "a_float": "2.718",
            "a_true": "true",
            "a_false": "False",
            "a_null": "null",
            "a_tilde": "~",
            "a_string": "hello",
        },
        wav,
    )
    cfg = WavConfig(wav)
    assert cfg["an_int"] == 42 and isinstance(cfg["an_int"], int)
    assert cfg["a_float"] == pytest.approx(2.718) and isinstance(cfg["a_float"], float)
    assert cfg["a_true"] is True
    assert cfg["a_false"] is False
    assert cfg["a_null"] is None
    assert cfg["a_tilde"] is None
    assert cfg["a_string"] == "hello"


def test_roundtrip_nested_dict(tmp_path):
    """Nested dicts survive encode_dict → WAV → WavConfig with nested access."""
    wav = str(tmp_path / "nested.wav")
    data = {
        "db": {"host": "localhost", "port": 5432},
        "server": {"debug": True, "workers": 4},
        "name": "myapp",
    }
    encode_dict(data, wav)
    cfg = WavConfig(wav)

    assert cfg["db"]["host"] == "localhost"
    assert cfg["db"]["port"] == 5432
    assert cfg["server"]["debug"] is True
    assert cfg["server"]["workers"] == 4
    assert cfg["name"] == "myapp"

    nested = cfg.to_nested()
    assert nested == {
        "db": {"host": "localhost", "port": 5432},
        "server": {"debug": True, "workers": 4},
        "name": "myapp",
    }


def test_roundtrip_nested_yaml(tmp_path):
    """Nested YAML files are parsed and survive encode → WAV → WavConfig."""
    yaml_content = """\
database:
  host: db.example.com
  port: 5432
  replica:
    host: replica.example.com
    port: 5433
app:
  name: yamlwav
  debug: false
"""
    yaml_path = str(tmp_path / "nested.yaml")
    wav_path = str(tmp_path / "nested.wav")
    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    encode(yaml_path, wav_path)
    cfg = WavConfig(wav_path)

    assert cfg["database"]["host"] == "db.example.com"
    assert cfg["database"]["port"] == 5432
    assert cfg["database"]["replica"]["host"] == "replica.example.com"
    assert cfg["database"]["replica"]["port"] == 5433
    assert cfg["app"]["name"] == "yamlwav"
    assert cfg["app"]["debug"] is False


def test_determinism(tmp_path):
    """Encoding the same config twice produces byte-for-byte identical WAV files."""
    wav1 = str(tmp_path / "c1.wav")
    wav2 = str(tmp_path / "c2.wav")
    data = {"host": "localhost", "port": "8080", "debug": "true"}
    encode_dict(data, wav1)
    encode_dict(data, wav2)
    with open(wav1, "rb") as f1, open(wav2, "rb") as f2:
        assert f1.read() == f2.read()


def test_roundtrip_compress_default(tmp_path):
    """Default encode produces a raw WAV file that decodes correctly."""
    wav = str(tmp_path / "raw.wav")
    data = {"host": "localhost", "port": "8080", "debug": "true"}
    encode_dict(data, wav)

    assert not zipfile.is_zipfile(wav), "Default output should be raw WAV"

    result = decode(wav)
    assert result["host"] == "localhost"
    assert result["port"] == "8080"
    assert result["debug"] == "true"


def test_roundtrip_compress_true(tmp_path):
    """compress=True produces a zip-compressed file that decodes correctly."""
    wav = str(tmp_path / "compressed.wav")
    data = {"host": "localhost", "port": "8080", "debug": "true"}
    encode_dict(data, wav, compress=True)

    assert zipfile.is_zipfile(wav), "compress=True output should be zip-compressed"

    result = decode(wav)
    assert result["host"] == "localhost"
    assert result["port"] == "8080"
    assert result["debug"] == "true"


def test_compression_reduces_size(tmp_path):
    """Compressed output is smaller than raw WAV output for the same config."""
    compressed = str(tmp_path / "compressed.wav")
    raw = str(tmp_path / "raw.wav")
    data = {"host": "localhost", "port": "8080", "debug": "true", "workers": "4"}
    encode_dict(data, compressed, compress=True)
    encode_dict(data, raw, compress=False)

    assert os.path.getsize(compressed) < os.path.getsize(raw)


def test_default_output_path(tmp_path):
    """encode() without wav_path writes to <yaml_path>.wav."""
    yaml_path = str(tmp_path / "config.yaml")
    with open(yaml_path, "w") as f:
        f.write("host: localhost\nport: 8080\n")

    encode(yaml_path)  # no wav_path given

    expected = yaml_path + ".wav"
    assert os.path.exists(expected), f"Expected output at {expected}"
    result = decode(expected)
    assert result["host"] == "localhost"
    assert result["port"] == "8080"


def test_standalone_decoder_handles_compressed(tmp_path):
    """The standalone decoder transparently handles zip-compressed files."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from standalone_decoder import decode_yamlwav

    wav = str(tmp_path / "compressed.wav")
    data = {"service": "web", "port": "443", "tls": "true"}
    encode_dict(data, wav, compress=True)

    result = decode_yamlwav(wav)
    assert result["service"] == "web"
    assert result["port"] == "443"
    assert result["tls"] == "true"


def test_stereo_channel_count(tmp_path):
    """v2 encoder always produces exactly 2-channel (stereo) WAV files."""
    wav = str(tmp_path / "stereo.wav")
    encode_dict({"a": "1", "b": "2", "c": "3"}, wav)
    with wave.open(wav, "r") as wf:
        assert wf.getnchannels() == 2


def test_v1_backward_compat(tmp_path):
    """Decoder can still read v1 N-channel WAV files."""
    from yamlwav.goertzel import AMPLITUDE, SAMPLE_RATE, SAMPLES_PER_CHAR, char_to_freq

    # Generate a v1 WAV file using the old N-channel encoding inline.
    data = {"host": "localhost", "port": "8080"}
    keys = list(data.keys())
    manifest = "\x00".join(keys)

    def encode_string(s):
        samples = []
        for ch in s:
            freq = char_to_freq(ord(ch))
            for i in range(SAMPLES_PER_CHAR):
                t = i / SAMPLE_RATE
                samples.append(int(AMPLITUDE * math.sin(2.0 * math.pi * freq * t)))
        return samples

    channels = [encode_string(manifest)]
    for key in keys:
        channels.append(encode_string(data[key]))

    max_len = max(len(ch) for ch in channels)
    padded = [ch + [0] * (max_len - len(ch)) for ch in channels]
    n_channels = len(padded)
    interleaved = bytearray()
    for frame_idx in range(max_len):
        for ch in padded:
            sample = max(-32768, min(32767, ch[frame_idx]))
            interleaved += struct.pack("<h", sample)

    wav = str(tmp_path / "v1.wav")
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(interleaved))
    with open(wav, "wb") as f:
        f.write(buf.getvalue())

    result = decode(wav)
    assert result["host"] == "localhost"
    assert result["port"] == "8080"


def test_odd_length_stream(tmp_path):
    """Config whose serialized stream has odd length roundtrips correctly."""
    wav = str(tmp_path / "odd.wav")
    # Pick values that produce an odd total serialized length.
    data = {"x": "ab"}
    encode_dict(data, wav)
    result = decode(wav)
    assert result["x"] == "ab"


def test_single_key(tmp_path):
    """Single key-value pair roundtrips correctly."""
    wav = str(tmp_path / "single.wav")
    data = {"only": "one"}
    encode_dict(data, wav)
    result = decode(wav)
    assert result["only"] == "one"
