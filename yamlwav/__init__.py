"""yamlwav — YAML config files encoded as playable WAV audio."""
from .config import WavConfig
from .decoder import decode
from .encoder import encode, encode_dict

__all__ = ["encode", "encode_dict", "decode", "WavConfig"]
__version__ = "2.0.0"
