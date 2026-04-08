"""Dict-like interface for reading config values directly from WAV files."""
from .decoder import decode


def _set_nested(d: dict, keys: list, value) -> None:
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


class _WavConfigView:
    """A read-only view into a namespace prefix of a WavConfig flat dict."""

    def __init__(self, data: dict, prefix: str) -> None:
        self._data = data
        self._prefix = prefix

    def __getitem__(self, key):
        full = f"{self._prefix}.{key}"
        if full in self._data:
            return self._data[full]
        if any(k.startswith(full + ".") for k in self._data):
            return _WavConfigView(self._data, full)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def to_nested(self) -> dict:
        result = {}
        prefix_dot = self._prefix + "."
        for k, v in self._data.items():
            if k.startswith(prefix_dot):
                parts = k[len(prefix_dot):].split(".")
                _set_nested(result, parts, v)
        return result

    def __repr__(self) -> str:
        return f"_WavConfigView(prefix={self._prefix!r}, {self.to_nested()!r})"


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
        if key in self._data:
            return self._data[key]
        if any(k.startswith(key + ".") for k in self._data):
            return _WavConfigView(self._data, key)
        raise KeyError(key)

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

    def to_nested(self) -> dict:
        """Reconstruct the full nested dict from dot-notation flat keys."""
        result = {}
        for k, v in self._data.items():
            _set_nested(result, k.split("."), v)
        return result
