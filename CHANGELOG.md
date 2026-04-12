# Changelog

## [Unreleased]

## [2.0.0] - 2026-04-11

### Changed
- **Breaking**: Encoding format switched from N-channel to stereo (2-channel) WAV for universal audio player compatibility
- Data throughput doubled — two characters encoded per 0.15s window (one per stereo channel) instead of one, halving WAV file size and duration

### Added
- Backward-compatible decoding of v1 (N-channel) WAV files — the decoder auto-detects the format

## [1.0.1] - 2026-04-11

### Added
- GitHub Action for encoding YAML to WAV and decoding WAV back to CI/CD outputs (env vars, .env files, JSON, step outputs)
- Python 3.14 support
- Acknowledgment for [@bbkane](https://github.com/bbkane) in README

### Changed
- Upgraded GitHub Actions dependencies to Node.js 24 (checkout v6, setup-python v6, upload-artifact v6)

### Fixed
- Version bump for PyPI publish (v1.0.0 release failed due to stale version in pyproject.toml)

## [0.1.1] - 2026-04-08

### Fixed
- Use absolute URL for social preview image on PyPI

## [0.1.0] - 2026-04-07

### Added
- YAML to WAV encoding with frequency-based character mapping
- WAV to dict decoding using Goertzel algorithm
- `WavConfig` dict-like interface with automatic type coercion
- Full YAML 1.2 parser (231/231 official test suite, 100% compliance)
- Optional zip compression (~95% size reduction)
- Command-line interface (`yamlwav encode` / `yamlwav decode`)
- Standalone decoder for zero-install decoding
- Zero external dependencies (pure Python stdlib)
