# yamlwav

A totally serious, production-ready configuration format that stores your YAML settings as playable WAV audio files.

## Why

- **Auditable configs** — you can literally hear your settings. Does your production database sound right? Now you'll know.
- **WAV is everywhere** — your OS, your DAW, your 2003 DVD player. YAML parsers, on the other hand, are not in the Python standard library. `wave` is.
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
