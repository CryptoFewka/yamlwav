"""Core logic for the yamlwav GitHub Action.

Handles both encode and decode modes. Reads configuration from INPUT_*
environment variables set by the composite action, writes results to
$GITHUB_OUTPUT and $GITHUB_ENV.
"""

import glob
import json
import os
import sys
from pathlib import Path

from yamlwav import decode, encode


def _github_output(key: str, value: str) -> None:
    """Write a key=value pair to $GITHUB_OUTPUT, handling multiline values."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if not output_file:
        return
    with open(output_file, "a") as f:
        if "\n" in value:
            f.write(f"{key}<<YAMLWAV_EOF\n{value}\nYAMLWAV_EOF\n")
        else:
            f.write(f"{key}={value}\n")


def _github_env(key: str, value: str) -> None:
    """Write a key=value pair to $GITHUB_ENV, handling multiline values."""
    env_file = os.environ.get("GITHUB_ENV", "")
    if not env_file:
        return
    with open(env_file, "a") as f:
        if "\n" in value:
            f.write(f"{key}<<YAMLWAV_EOF\n{value}\nYAMLWAV_EOF\n")
        else:
            f.write(f"{key}={value}\n")


_VALID_TRANSFORMS = ("upper", "flat", "preserve")


def _transform_key(key: str, mode: str, prefix: str) -> str:
    """Transform a dot-notation key based on the chosen mode and prefix."""
    if mode == "upper":
        transformed = key.replace(".", "_").replace("-", "_").upper()
    elif mode == "flat":
        transformed = key.replace(".", "_").replace("-", "_")
    else:  # preserve (validated in decode_mode)
        transformed = key
    return prefix + transformed


def _quote_dotenv_value(value: str) -> str:
    """Quote a value for .env file format."""
    if "\n" in value or '"' in value or "'" in value or " " in value or "=" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return value


def encode_mode() -> None:
    """Handle encode mode: convert YAML files to WAV."""
    files_input = os.environ.get("INPUT_FILES", "").strip()
    compress = os.environ.get("INPUT_COMPRESS", "false").lower() == "true"
    output_dir = os.environ.get("INPUT_OUTPUT_DIR", "").strip()

    if not files_input:
        print("::error::No files specified. Set the 'files' input.")
        sys.exit(1)

    generated = []

    # Split on newlines for multiple patterns
    patterns = [p.strip() for p in files_input.splitlines() if p.strip()]

    for pattern in patterns:
        matches = sorted(glob.glob(pattern, recursive=True))
        for yaml_file in matches:
            if not os.path.isfile(yaml_file):
                continue

            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                basename = os.path.basename(yaml_file)
                wav_path = os.path.join(output_dir, basename + ".wav")
            else:
                wav_path = yaml_file + ".wav"

            encode(yaml_file, wav_path, compress=compress)
            print(f"Encoded: {yaml_file} -> {wav_path}")
            generated.append(wav_path)

    if not generated:
        print(f"::error::No YAML files matched the pattern(s): {files_input}")
        sys.exit(1)

    _github_output("file-count", str(len(generated)))
    _github_output("files", "\n".join(generated))
    print(f"::notice::Encoded {len(generated)} YAML file(s) to .yaml.wav")


def decode_mode() -> None:
    """Handle decode mode: convert WAV back to CI-usable outputs."""
    file_input = os.environ.get("INPUT_FILE", "").strip()
    formats = [
        f.strip()
        for f in os.environ.get("INPUT_FORMAT", "").split(",")
        if f.strip()
    ]
    prefix = os.environ.get("INPUT_PREFIX", "")
    key_transform = os.environ.get("INPUT_KEY_TRANSFORM", "upper").strip()
    mask_all = os.environ.get("INPUT_MASK_VALUES", "false").lower() == "true"
    output_path = os.environ.get("INPUT_OUTPUT", "").strip()

    if not file_input:
        print("::error::No file specified. Set the 'file' input.")
        sys.exit(1)

    if not os.path.isfile(file_input):
        print(f"::error::File not found: {file_input}")
        sys.exit(1)

    if key_transform not in _VALID_TRANSFORMS:
        print(
            f"::warning::Unknown key-transform '{key_transform}', "
            f"falling back to 'upper'"
        )
        key_transform = "upper"

    data = decode(file_input)
    print(f"Decoded {len(data)} key(s) from {file_input}")

    # Transform keys and build output dict
    transformed = {}
    for key, value in data.items():
        new_key = _transform_key(key, key_transform, prefix)

        # Check for collisions
        if new_key in transformed:
            print(
                f"::warning::Key collision: '{key}' maps to '{new_key}' "
                f"which already exists. Using latest value."
            )

        transformed[new_key] = value

    # Apply masking before writing any outputs
    for key, value in transformed.items():
        if mask_all:
            print(f"::add-mask::{value}")

    # Always output JSON as a step output for fromJSON() access
    _github_output("json", json.dumps(transformed))

    # Determine which formats write files so we can handle the output path.
    # If only one file format is requested, output_path applies to it.
    # If multiple file formats are requested, use defaults for each.
    file_formats = [f for f in formats if f in ("dotenv", "json")]
    use_explicit_path = len(file_formats) == 1

    # Write outputs in each requested format
    for fmt in formats:
        if fmt == "env":
            for key, value in transformed.items():
                _github_env(key, value)
            print(f"Wrote {len(transformed)} environment variable(s)")

        elif fmt == "dotenv":
            dotenv_path = (output_path if use_explicit_path else "") or ".env"
            with open(dotenv_path, "w") as f:
                for key, value in transformed.items():
                    f.write(f"{key}={_quote_dotenv_value(value)}\n")
            print(f"Wrote .env file: {dotenv_path}")

        elif fmt == "json":
            json_path = (output_path if use_explicit_path else "") or "config.json"
            with open(json_path, "w") as f:
                json.dump(transformed, f, indent=2)
                f.write("\n")
            print(f"Wrote JSON file: {json_path}")

        else:
            print(f"::warning::Unknown format '{fmt}', skipping")


def main() -> None:
    try:
        mode = os.environ.get("INPUT_MODE", "").strip().lower()
        if mode not in ("encode", "decode"):
            print(f"::error::Invalid mode '{mode}'. Set mode to 'encode' or 'decode'.")
            sys.exit(1)
        print(f"Mode: {mode}")

        if mode == "encode":
            encode_mode()
        else:
            decode_mode()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"::error::{type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
