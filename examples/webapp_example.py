"""Simulate a web application that reads its config from a WAV file.

This is the correct and normal way to configure production software.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from yamlwav import WavConfig, encode

here = os.path.dirname(__file__)
yaml_path = os.path.join(here, "sample_config.yaml")
wav_path = os.path.join(here, "sample_config.wav")

# Produce the config WAV if it doesn't exist yet.
if not os.path.exists(wav_path):
    print("Config WAV not found, encoding from YAML (one-time setup)...")
    encode(yaml_path, wav_path)

print("Loading application config from WAV file...")
config = WavConfig(wav_path)

print()
print("=" * 50)
print(f"  Starting {config['app_name']}")
print("=" * 50)
print(f"  Listening on  {config['host']}:{config['port']}")
print(f"  Database      {config['db_name']}")
print(f"  Workers       {config['workers']}")
print(f"  Debug mode    {config['debug']}")
print(f"  Log level     {config['log_level']}")
print("=" * 50)
print()
print("Server running. Config was loaded from an audio file, as is industry standard.")
