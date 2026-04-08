"""YAML 1.2 compliance tests against the official yaml-test-suite.

Each test case is a directory in tests/yaml-test-suite/ (git submodule,
data branch of https://github.com/yaml/yaml-test-suite).

Run:
    pytest tests/test_yaml_compliance.py -v

The compliance score (X passed / 231 total) is the completion criterion.
test_exceeds_pyyaml tracks cases where yamlwav succeeds but PyYAML fails.
"""
import json
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from yamlwav.yaml_parser import YAMLError, parse as yamlwav_parse, parse_all as yamlwav_parse_all


def _load_json(path):
    """Load expected output from in.json.

    Multi-document streams have multiple JSON values in the file (one per line
    or separated by whitespace).  We detect this case by attempting json.loads()
    on the whole file; if it raises "Extra data" we parse each value individually
    and return a list.
    """
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return None, False  # empty in.json means null/None, single document

    try:
        return json.loads(content), False  # single document
    except json.JSONDecodeError as exc:
        if "Extra data" not in str(exc):
            raise
        # Multiple JSON documents in file — parse them one by one
        docs = []
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(content):
            # Skip whitespace
            while idx < len(content) and content[idx] in (" ", "\t", "\n", "\r"):
                idx += 1
            if idx >= len(content):
                break
            value, end = decoder.raw_decode(content, idx)
            docs.append(value)
            idx = end
        return docs, True  # multi-document


def _load_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_yamlwav_compliance(yaml_test_case):
    """yamlwav parser output matches the expected JSON for each test case."""
    test_id, in_yaml, in_json = yaml_test_case
    expected, is_multi = _load_json(in_json)
    yaml_text = _load_text(in_yaml)
    try:
        if is_multi:
            result = yamlwav_parse_all(yaml_text)
        else:
            result = yamlwav_parse(yaml_text)
    except YAMLError as exc:
        pytest.fail(f"{test_id}: unexpected YAMLError: {exc}")
    assert result == expected, f"{test_id}: got {result!r}, expected {expected!r}"


def test_rejects_invalid_yaml(yaml_error_case):
    """Parser must raise on inputs the YAML spec considers invalid.

    These cases come from the yaml-test-suite error cases.  Many will initially
    fail — that is expected and informative: it shows exactly where
    error-detection is lacking.  Any exception (not just YAMLError) counts as a
    correct rejection; a clean return value is a failure.  A 3-second alarm
    guards against the parser hanging on pathological invalid input.
    """
    import signal

    test_id, in_yaml = yaml_error_case
    yaml_text = _load_text(in_yaml)

    def _alarm(signum, frame):
        raise TimeoutError(f"{test_id}: parser hung on invalid YAML (infinite loop)")

    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(3)
    try:
        result = yamlwav_parse(yaml_text)
    except TimeoutError as exc:
        pytest.fail(str(exc))
    except Exception:
        return  # any exception = parser rejected the input, which is correct
    finally:
        signal.alarm(0)
    pytest.fail(
        f"{test_id}: parser accepted invalid YAML without error (returned {result!r})"
    )


def test_exceeds_pyyaml(yaml_test_case):
    """Passes only for test cases where yamlwav succeeds but PyYAML fails.

    These are the cases where yamlwav demonstrably beats PyYAML.
    """
    try:
        import yaml as pyyaml
    except ImportError:
        pytest.skip("pyyaml not installed")

    test_id, in_yaml, in_json = yaml_test_case
    expected, is_multi = _load_json(in_json)
    yaml_text = _load_text(in_yaml)

    pyyaml_ok = False
    try:
        if is_multi:
            pyyaml_result = list(pyyaml.safe_load_all(yaml_text))
        else:
            pyyaml_result = pyyaml.safe_load(yaml_text)
        if pyyaml_result == expected:
            pyyaml_ok = True
    except Exception:
        pass

    if pyyaml_ok:
        pytest.skip("PyYAML also passes this case")

    # PyYAML failed or got a wrong answer — assert yamlwav gets it right
    try:
        if is_multi:
            result = yamlwav_parse_all(yaml_text)
        else:
            result = yamlwav_parse(yaml_text)
    except YAMLError as exc:
        pytest.fail(f"{test_id}: yamlwav also failed with YAMLError: {exc}")
    assert result == expected, f"{test_id}: got {result!r}, expected {expected!r}"
