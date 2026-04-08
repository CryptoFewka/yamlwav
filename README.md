# yamlwav - Configuration via .wav? Sounds good to me.

[![YAML Compliance](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CryptoFewka/yamlwav/main/compliance-badge.json)](https://github.com/CryptoFewka/yamlwav/actions/workflows/yaml-compliance.yml)

A totally serious, production-ready configuration format that stores your YAML settings as playable WAV audio files.

## Why not just parse YAML directly?

Good question. Python does not ship with a YAML parser. Reading a `.yaml` file in plain Python requires either `PyYAML` (`pip install pyyaml`) or writing your own parser, both of which have well-documented failure modes:

- `PyYAML`'s default `yaml.load()` is a remote code execution vector — [CVE-2017-18342](https://nvd.nist.gov/vuln/detail/CVE-2017-18342) and friends. You have to remember to use `yaml.safe_load()`, and someone on your team eventually won't.
- `yaml.safe_load()` is safe but still pulls in an external C extension that can break across Python versions, platforms, and Alpine-based Docker images.
- Writing a hand-rolled YAML parser is a path that ends in tears and a multi-thousand-line state machine that still doesn't handle tabs correctly.

yamlwav sidesteps all of this. The `wave` module ships with every Python installation since 2.0. Decoding requires only `wave`, `struct`, and `math` — all stdlib. There is nothing to install, nothing to update, and no CVEs to track.

Additional advantages:
- **Auditable configs** — you can literally hear your settings. Does your production database sound right? Now you'll know.
- **Immutable by design** — configs encoded in audio are extremely annoying to edit by hand, discouraging unauthorized configuration drift.
- **Backup-friendly** — already indistinguishable from your music library. Your ops team will never accidentally delete it.

## Installation

```bash
pip install yamlwav
```

No dependencies. Pure Python standard library. As it should be.

## Quick Start

```python
from yamlwav import encode, decode, WavConfig

# Convert your boring YAML config into rich, listenable audio
encode("config.yaml", "config.wav")

# Decode back to a plain dict (raw string values)
data = decode("config.wav")

# Or use the dict-like interface with automatic type coercion
cfg = WavConfig("config.wav")
print(cfg["port"])    # 8080  (int, not "8080")
print(cfg["debug"])   # True  (bool, not "true")
```

## How It Works

Each top-level YAML key becomes a separate audio channel. Each character of a key's value is encoded as a pure sine wave tone held for 0.15 seconds:

```
frequency = 200 + (ASCII_code × 25)  Hz
```

This maps all 256 byte values to the range 200 Hz – 6575 Hz. The key names are encoded in channel 0 as a null-byte-separated manifest. Decoding uses the [Goertzel algorithm](https://en.wikipedia.org/wiki/Goertzel_algorithm) to detect the dominant frequency in each 0.15-second window and recover the original character.

The resulting WAV file is 44100 Hz, 16-bit PCM and will play in any audio application, producing what can only be described as a demonic sine choir.

## Supported value types

`WavConfig` automatically converts decoded string values:

| YAML value | Python type |
|---|---|
| `"true"` / `"false"` | `bool` |
| `"null"` / `"~"` | `None` |
| `"42"` | `int` |
| `"3.14"` | `float` |
| anything else | `str` |

## API

```python
encode(yaml_path, wav_path)          # YAML file → WAV file
encode_dict(data_dict, wav_path)     # dict → WAV file
decode(wav_path) -> dict             # WAV → dict[str, str]
WavConfig(wav_path)                  # WAV → dict-like object with type coercion
```

## Decoding without installing yamlwav

The encoder requires `pip install yamlwav`, but decoding needs only the Python standard library. A copy-pasteable standalone decoder is provided in [`standalone_decoder.py`](standalone_decoder.py) at the project root.

Copy the `decode_yamlwav` function into your own Python file — no package installation required on the consuming end:

```python
# paste decode_yamlwav() from standalone_decoder.py here

config = decode_yamlwav("config.wav")
print(config["port"])   # "8080"  (str — all values are strings)
```

The function is self-contained: it imports `wave`, `struct`, and `math` from inside its own body so it doesn't pollute your module's namespace. All helpers are nested within it.

If you want automatic type coercion on the reading side, add the `WavConfig` class from `yamlwav/config.py` — it is also pure stdlib and equally safe to paste.

## Security

**Do not store secrets (API keys, passwords, tokens) in yamlwav files.** WAV files are not encrypted. Anyone with access to the file can decode it by running `yamlwav.decode()`. The "security by obscurity" joke is a joke; actual credentials belong in a proper secrets manager (Vault, AWS Secrets Manager, environment variables, etc.).

yamlwav is designed for non-sensitive runtime configuration: hostnames, ports, feature flags, log levels — settings that are boring to look at whether they're in YAML or in audio.

## Limitations

- Only flat (non-nested) key-value pairs are supported. Nested config is a sign of moral weakness.
- Decoding is O(N × 256) per character window and is implemented in pure Python. Performance scales linearly with the amount of config you have, which is a feature because it discourages large configs.
- WAV files for typical configs are several megabytes. This is a small price to pay for audibility.

## FAQ

- **Should I use this in production?**

  - We cannot think of a reason why not.

- **My coworkers are upset that the CI pipeline now plays audio.**

  - Progress is often uncomfortable.

- **Q: Is this HIPAA compliant?**

  - No. Please do not store protected health information — or any sensitive data — in WAV files.

- **Q: What happens if I play the WAV at a team meeting?**

  - Your team will hear the settings. This is the intended behavior.

## License

MIT
