"""Encode sample_config.yaml into sample_config.wav."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from yamlwav import encode

here = os.path.dirname(__file__)
yaml_path = os.path.join(here, "sample_config.yaml")
wav_path = os.path.join(here, "sample_config.wav")

print(f"Encoding {yaml_path} → {wav_path}")
encode(yaml_path, wav_path)
size_kb = os.path.getsize(wav_path) / 1024
print(f"Done. Output: {size_kb:.1f} KB")
print("You may now open sample_config.wav in any audio player to experience enterprise-grade config management.")
