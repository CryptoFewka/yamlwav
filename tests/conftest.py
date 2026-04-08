"""Shared pytest fixtures, including yaml-test-suite parametrization."""
import json
import os

import pytest

SUITE_DIR = os.path.join(os.path.dirname(__file__), "yaml-test-suite")


def _load_cases():
    cases = []
    if not os.path.isdir(SUITE_DIR):
        return cases
    for entry in sorted(os.listdir(SUITE_DIR)):
        path = os.path.join(SUITE_DIR, entry)
        if not os.path.isdir(path):
            continue
        in_yaml = os.path.join(path, "in.yaml")
        in_json = os.path.join(path, "in.json")
        if (
            os.path.exists(in_yaml)
            and os.path.exists(in_json)
            and not os.path.exists(os.path.join(path, "error"))
        ):
            cases.append(pytest.param((entry, in_yaml, in_json), id=entry))
    return cases


@pytest.fixture(params=_load_cases())
def yaml_test_case(request):
    """Yields (test_id, in_yaml_path, in_json_path) for each yaml-test-suite case."""
    return request.param
