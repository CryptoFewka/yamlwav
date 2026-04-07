"""Dict-like interface for reading config values directly from WAV files."""
from .decoder import decode


class WavConfig:
    """Read a yamlwav WAV file as a dict-like config object.

    Values are automatically coerced to their natural Python types:
    - "true" / "false" (case-insensitive) → bool
    - "null" / "~" → None
    - Integer-looking strings → int
    - Float-looking strings → float
    - Everything else stays as str
    """

    def __init__(self, path: str) -> None:
        raw = decode(path)
        self._data = {k: self._coerce(v) for k, v in raw.items()}

    @staticmethod
    def _coerce(value: str):
        if value.lower() in ("true",):
            return True
        if value.lower() in ("false",):
            return False
        if value.lower() in ("null", "~"):
            return None
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"WavConfig({self._data!r})"

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()
