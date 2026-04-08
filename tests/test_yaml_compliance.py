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

from yamlwav.yaml_parser import YAMLError, parse as yamlwav_parse


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return None  # empty in.json means the document produces null/None
    return json.loads(content)


def _load_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_yamlwav_compliance(yaml_test_case):
    """yamlwav parser output matches the expected JSON for each test case."""
    test_id, in_yaml, in_json = yaml_test_case
    expected = _load_json(in_json)
    try:
        result = yamlwav_parse(_load_text(in_yaml))
    except YAMLError as exc:
        pytest.fail(f"{test_id}: unexpected YAMLError: {exc}")
    assert result == expected, f"{test_id}: got {result!r}, expected {expected!r}"


def test_exceeds_pyyaml(yaml_test_case):
    """Passes only for test cases where yamlwav succeeds but PyYAML fails.

    These are the cases where yamlwav demonstrably beats PyYAML.
    """
    try:
        import yaml as pyyaml
    except ImportError:
        pytest.skip("pyyaml not installed")

    test_id, in_yaml, in_json = yaml_test_case
    expected = _load_json(in_json)
    yaml_text = _load_text(in_yaml)

    pyyaml_ok = False
    try:
        pyyaml_result = pyyaml.safe_load(yaml_text)
        if pyyaml_result == expected:
            pyyaml_ok = True
    except Exception:
        pass

    if pyyaml_ok:
        pytest.skip("PyYAML also passes this case")

    # PyYAML failed or got a wrong answer — assert yamlwav gets it right
    try:
        result = yamlwav_parse(yaml_text)
    except YAMLError as exc:
        pytest.fail(f"{test_id}: yamlwav also failed with YAMLError: {exc}")
    assert result == expected, f"{test_id}: got {result!r}, expected {expected!r}"
