![yamlwav social preview](https://raw.githubusercontent.com/CryptoFewka/yamlwav/main/social_preview.png)

# yamlwav - Configuration via .wav? Sounds good to me.

[![YAML Compliance](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CryptoFewka/yamlwav/main/compliance-badge.json)](https://github.com/CryptoFewka/yamlwav/actions/workflows/yaml-compliance.yml)
[![Action Tests](https://github.com/CryptoFewka/yamlwav/actions/workflows/test-action.yml/badge.svg)](https://github.com/CryptoFewka/yamlwav/actions/workflows/test-action.yml)
[![Python 3.9-3.14](https://img.shields.io/badge/python-3.9--3.14-blue)](https://pypi.org/project/yamlwav/)

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
# Output defaults to <yaml_path>.wav — e.g. config.yaml → config.yaml.wav
encode("config.yaml")

# Or specify the output path explicitly
encode("config.yaml", "config.yaml.wav")

# Decode back to a plain dict (raw string values)
data = decode("config.yaml.wav")

# Or use the dict-like interface with automatic type coercion
cfg = WavConfig("config.yaml.wav")
print(cfg["port"])    # 8080  (int, not "8080")
print(cfg["debug"])   # True  (bool, not "true")

# Nested YAML works too — keys flatten to dot-notation
print(cfg["db"]["host"])  # "localhost"  (nested access)
print(cfg.to_nested())    # {"db": {"host": "localhost", "port": 5432}, ...}
```

## How It Works

Each YAML key becomes a separate audio channel. Nested keys are flattened to dot-notation (e.g. `db.host`) before encoding. Each character of a key's value is encoded as a pure sine wave tone held for 0.15 seconds:

```
frequency = 200 + (ASCII_code × 25)  Hz
```

This maps all 256 byte values to the range 200 Hz – 6575 Hz. The key names are encoded in channel 0 as a null-byte-separated manifest. Decoding uses the [Goertzel algorithm](https://en.wikipedia.org/wiki/Goertzel_algorithm) to detect the dominant frequency in each 0.15-second window and recover the original character.

The resulting WAV file is 44100 Hz, 16-bit PCM and will play in any audio application, producing what can only be described as a demonic sine choir.

### Hear it yourself

This config:

```yaml
host: localhost
port: 8080
debug: true
```

sounds like this (unmute to listen):

https://github.com/CryptoFewka/yamlwav/raw/refs/heads/docs/demo-audio/examples/demo.mp4

## YAML Compliance

In the course of eliminating YAML dependencies, we accidentally wrote a complete YAML 1.2 parser. It is 1,660 lines of pure Python, has zero external dependencies, and passes the official YAML test suite at a rate that may surprise you.

| Feature | yamlwav | PyYAML | ruamel.yaml |
|---|---|---|---|
| YAML spec version | 1.2 | 1.1 | 1.2 |
| Official test-suite pass rate | 231/231 (100%) | ~60% | ~99% |
| External dependencies | 0 | libyaml (C) | yes |
| Known RCE CVEs | 0 | CVE-2017-18342 | 0 |
| Also plays audio | yes | no | no |

The parser supports anchors and aliases, tags, multi-document streams, flow collections, block scalars (literal and folded with all chomping modes), single- and double-quoted strings with full escape sequences, YAML 1.2 Core Schema type resolution, Unicode, and directives.

```python
from yamlwav.yaml_parser import parse, parse_all

doc = parse("port: 8080\ndebug: true")       # single document
docs = parse_all("---\na: 1\n---\nb: 2\n")   # multi-document stream
```

## Supported value types

`WavConfig` automatically converts decoded string values:

| YAML value | Python type |
|---|---|
| `"true"` / `"false"` | `bool` |
| `"null"` / `"~"` | `None` |
| `"42"` | `int` |
| `"3.14"` | `float` |
| anything else | `str` |

## Compression

By default yamlwav writes a standard, playable WAV file. To reduce file size, pass
`compress=True` — the output will be wrapped in a `zipfile.ZIP_DEFLATED` archive, typically
shrinking the file by ~95% (e.g. 5.3 MB → 271 KB). The extension stays `.yaml.wav` either way;
decoders auto-detect which format they received.

```python
# Default: raw PCM WAV — playable in any audio application
encode("config.yaml")

# Opt in to compression for smaller files
encode("config.yaml", compress=True)
encode_dict(data, "config.yaml.wav", compress=True)
```

Output is deterministic — the same input always produces byte-identical WAV files, compressed or not.

## Command-line interface

```bash
# Encode — output defaults to config.yaml.wav
yamlwav encode config.yaml

# Encode with compression
yamlwav encode config.yaml --compress

# Specify output path explicitly
yamlwav encode config.yaml output.yaml.wav

# Decode back to key: value pairs
yamlwav decode config.yaml.wav
```

## GitHub Action

yamlwav is available as a GitHub Action for encoding YAML files to WAV and decoding them back to CI-usable formats.

### Encode YAML to WAV

```yaml
- uses: CryptoFewka/yamlwav@v1
  with:
    mode: encode
    files: config.yaml
```

With all options:

```yaml
- uses: CryptoFewka/yamlwav@v1
  with:
    mode: encode
    files: |
      configs/**/*.yaml
      settings/*.yml
    compress: "true"
    output-dir: wav-output
    upload-artifact: "true"
    artifact-name: config-audio-${{ github.sha }}
```

### Decode WAV to step outputs

```yaml
- name: Decode config
  id: cfg
  uses: CryptoFewka/yamlwav@v1
  with:
    mode: decode
    file: config.yaml.wav

# All decoded values are available via fromJSON()
- run: echo "Host is ${{ fromJSON(steps.cfg.outputs.json).HOST }}"
```

### Decode WAV to environment variables

```yaml
- uses: CryptoFewka/yamlwav@v1
  with:
    mode: decode
    file: config.yaml.wav
    format: env
    prefix: APP_

- run: echo "Host is $APP_HOST"
```

### Decode WAV to .env or JSON file

```yaml
- uses: CryptoFewka/yamlwav@v1
  with:
    mode: decode
    file: config.yaml.wav
    format: dotenv
    output: .env
```

### Action inputs

| Input | Mode | Default | Description |
|---|---|---|---|
| `mode` | both | *required* | `encode` or `decode`. |
| `files` | encode | | YAML files or glob patterns (newline-separated). |
| `file` | decode | | Single `.yaml.wav` file to decode. |
| `compress` | encode | `false` | Zip compression (~95% size reduction). |
| `output-dir` | encode | | Directory for WAV output. |
| `upload-artifact` | encode | `false` | Upload WAV files as GitHub Actions artifacts. |
| `artifact-name` | encode | `yamlwav-files` | Name for the uploaded artifact. |
| `format` | decode | | Comma-separated: `env`, `dotenv`, `json`. All values always available via `json` output. |
| `prefix` | decode | | Prefix for output keys (e.g. `APP_`). |
| `key-transform` | decode | `upper` | `upper` (`db.host` -> `DB_HOST`), `flat` (`db_host`), `preserve`. |
| `mask-values` | decode | `false` | Mask all decoded values in logs. |
| `output` | decode | | File path for dotenv/json output. |
| `python-version` | both | `3.x` | Python version. |

### Version pinning

- `@v1` -- recommended. Gets bug fixes and new features, no breaking changes.
- `@v1.0.0` -- exact version pin for maximum reproducibility.
- `@main` -- latest development. Not recommended for production.

## API

```python
encode(yaml_path, wav_path=None, compress=False)  # YAML file → WAV file (default output: <yaml_path>.wav)
encode_dict(data_dict, wav_path, compress=False)   # dict → WAV file (nested dicts auto-flattened)
decode(wav_path) -> dict                           # WAV → dict[str, str]  (auto-detects compression)
WavConfig(wav_path)                                # WAV → dict-like object with type coercion
WavConfig["section"]["key"]                        # nested access via dot-notation keys
WavConfig.to_nested() -> dict                      # reconstruct full nested dict

# Standalone YAML 1.2 parser (no WAV involved)
from yamlwav.yaml_parser import parse, parse_all
parse(text) -> object                              # parse a single YAML 1.2 document
parse_all(text) -> list                            # parse all documents in a YAML stream
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

- Nested YAML is supported but flattened internally to dot-notation keys. Deep nesting remains a sign of moral weakness.
- Decoding is O(N × 256) per character window and is implemented in pure Python. Performance scales linearly with the amount of config you have, which is a feature because it discourages large configs.
- WAV files for typical configs are several megabytes. Pass `compress=True` to reduce this substantially, at the cost of the file no longer being directly playable as audio.

## FAQ

- **Should I use this in production?**

  - We cannot think of a reason why not.

- **My coworkers are upset that the CI pipeline now plays audio.**

  - Progress is often uncomfortable.

- **Q: Is this HIPAA compliant?**

  - No. Please do not store protected health information — or any sensitive data — in WAV files.

- **Q: What happens if I play the WAV at a team meeting?**

  - Your team will hear the settings. This is the intended behavior.

## Acknowledgments

Inspired by an offhand comment from [@bbkane](https://github.com/bbkane) on Reddit.

## License

MIT
