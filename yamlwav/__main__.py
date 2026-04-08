"""Command-line interface for yamlwav.

Usage:
    python -m yamlwav encode config.yaml config.wav
    python -m yamlwav encode config.yaml config.wav --no-compress
    python -m yamlwav decode config.wav
"""
import argparse

from . import decode, encode


def main():
    parser = argparse.ArgumentParser(
        prog="python -m yamlwav",
        description="Encode YAML configs as WAV audio or decode them back.",
    )
    sub = parser.add_subparsers(dest="cmd")

    enc = sub.add_parser("encode", help="Encode a YAML file to a WAV file")
    enc.add_argument("yaml_path", help="Input YAML file")
    enc.add_argument("wav_path", help="Output WAV file")
    enc.add_argument(
        "--no-compress",
        dest="compress",
        action="store_false",
        default=True,
        help="Write raw uncompressed PCM WAV instead of zip-compressed output",
    )

    dec = sub.add_parser("decode", help="Decode a yamlwav file to key: value pairs")
    dec.add_argument("wav_path", help="WAV file produced by yamlwav (compressed or raw)")

    args = parser.parse_args()
    if args.cmd == "encode":
        encode(args.yaml_path, args.wav_path, compress=args.compress)
    elif args.cmd == "decode":
        for k, v in decode(args.wav_path).items():
            print(f"{k}: {v}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
