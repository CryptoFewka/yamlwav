"""Roundtrip tests for yamlwav encode/decode."""
import os
import string
import sys
import tempfile

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
