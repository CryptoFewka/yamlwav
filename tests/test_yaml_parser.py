"""Tests for YAML spec areas not covered by yaml-test-suite.

These tests exercise edge cases in the yamlwav parser that go beyond or between
the yaml-test-suite's test vectors.  Categories covered:

  - Unicode (non-ASCII scalars, BOM stripping)
  - Merge keys (<<) and alias references
  - Deep nesting
  - Float / int edge cases (inf, nan, hex, octal)
  - Block-scalar chomping combinations
  - Flow collection edge cases
  - Directive handling (%YAML, %TAG)
  - Multi-document streams (parse_all)
  - Error / empty document handling
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from yamlwav.yaml_parser import YAMLError, parse, parse_all


# ---------------------------------------------------------------------------
# Unicode
# ---------------------------------------------------------------------------

class TestUnicode:
    def test_non_ascii_scalar(self):
        assert parse("value: café\n") == {"value": "café"}

    def test_emoji_in_scalar(self):
        assert parse("icon: '🎵'\n") == {"icon": "🎵"}

    def test_bom_stripped(self):
        """UTF-8 BOM (U+FEFF) at the start of a document is silently removed."""
        text = "\uFEFFkey: value\n"
        assert parse(text) == {"key": "value"}

    def test_multibyte_key_and_value(self):
        assert parse("日本語: 漢字\n") == {"日本語": "漢字"}

    def test_unicode_escape_in_double_quoted(self):
        assert parse(r'"caf\u00e9"') == "café"

    def test_unicode_null_escape(self):
        assert parse(r'"a\0b"') == "a\x00b"


# ---------------------------------------------------------------------------
# Aliases & anchors
# ---------------------------------------------------------------------------

class TestAliases:
    def test_basic_alias(self):
        result = parse("a: &x 1\nb: *x\n")
        assert result == {"a": 1, "b": 1}

    def test_alias_in_sequence(self):
        result = parse("- &item hello\n- *item\n")
        assert result == ["hello", "hello"]

    def test_anchor_on_mapping(self):
        yaml = """\
defaults: &defaults
  color: blue
  size: large
item:
  <<: *defaults
  size: small
"""
        result = parse(yaml)
        # yamlwav does not expand merge keys (<<) — the alias is stored as-is
        # The << key holds the aliased mapping value
        assert result["defaults"] == {"color": "blue", "size": "large"}
        assert result["item"]["size"] == "small"
        assert result["item"]["<<"] == {"color": "blue", "size": "large"}

    def test_anchor_on_sequence(self):
        yaml = "seq: &s [1, 2, 3]\nref: *s\n"
        result = parse(yaml)
        assert result["seq"] == [1, 2, 3]
        assert result["ref"] == [1, 2, 3]

    def test_anchor_null(self):
        """An anchor with no following value produces null."""
        result = parse("a: &x\nb: *x\n")
        assert result["a"] is None
        assert result["b"] is None


# ---------------------------------------------------------------------------
# Scalars — type resolution
# ---------------------------------------------------------------------------

class TestScalarTypes:
    def test_integer(self):
        assert parse("42") == 42

    def test_negative_integer(self):
        assert parse("-7") == -7

    def test_float(self):
        assert abs(parse("3.14") - 3.14) < 1e-9

    def test_float_scientific(self):
        assert parse("1.5e3") == pytest.approx(1500.0)

    def test_bool_true_variants(self):
        for v in ("true", "True", "TRUE"):
            assert parse(v) is True, f"Expected True for {v!r}"

    def test_bool_false_variants(self):
        for v in ("false", "False", "FALSE"):
            assert parse(v) is False, f"Expected False for {v!r}"

    def test_null_variants(self):
        for v in ("null", "Null", "NULL", "~", ""):
            assert parse(v) is None, f"Expected None for {v!r}"

    def test_hex_integer(self):
        assert parse("0xFF") == 255

    def test_octal_integer(self):
        assert parse("0o17") == 15

    def test_inf(self):
        import math
        assert math.isinf(parse(".inf")) and parse(".inf") > 0

    def test_neg_inf(self):
        import math
        assert math.isinf(parse("-.inf")) and parse("-.inf") < 0

    def test_nan(self):
        import math
        assert math.isnan(parse(".nan"))

    def test_quoted_integer_stays_string(self):
        assert parse("'42'") == "42"
        assert isinstance(parse("'42'"), str)

    def test_quoted_true_stays_string(self):
        assert parse('"true"') == "true"
        assert isinstance(parse('"true"'), str)


# ---------------------------------------------------------------------------
# Block scalars — chomping and indentation
# ---------------------------------------------------------------------------

class TestBlockScalars:
    def test_literal_clip(self):
        yaml = "key: |\n  hello\n  world\n"
        assert parse(yaml) == {"key": "hello\nworld\n"}

    def test_literal_strip(self):
        yaml = "key: |-\n  hello\n\n"
        assert parse(yaml) == {"key": "hello"}

    def test_literal_keep(self):
        yaml = "key: |+\n  hello\n\n"
        assert parse(yaml) == {"key": "hello\n\n"}

    def test_folded_clip(self):
        yaml = "key: >\n  hello\n  world\n"
        assert parse(yaml) == {"key": "hello world\n"}

    def test_folded_strip(self):
        yaml = "key: >-\n  hello\n  world\n"
        assert parse(yaml) == {"key": "hello world"}

    def test_folded_keep(self):
        yaml = "key: >+\n  hello\n  world\n\n"
        assert parse(yaml) == {"key": "hello world\n\n"}

    def test_literal_explicit_indent(self):
        yaml = "key: |2\n    indented\n"
        assert parse(yaml) == {"key": "  indented\n"}

    def test_empty_block_scalar(self):
        yaml = "key: >-\n\nother: value\n"
        assert parse(yaml) == {"key": "", "other": "value"}

    def test_folded_more_indented_line(self):
        """More-indented lines in a folded scalar are preserved verbatim."""
        yaml = "key: >\n  normal\n    more indented\n  normal\n"
        assert parse(yaml) == {"key": "normal\n  more indented\nnormal\n"}

    def test_literal_whitespace_only_line(self):
        """Whitespace-only lines inside a literal scalar are preserved."""
        yaml = "key: |\n  line1\n  \n  line2\n"
        # The whitespace-only line becomes a blank line in the output
        assert parse(yaml) == {"key": "line1\n\nline2\n"}


# ---------------------------------------------------------------------------
# Flow collections
# ---------------------------------------------------------------------------

class TestFlowCollections:
    def test_flow_sequence(self):
        assert parse("[1, 2, 3]") == [1, 2, 3]

    def test_flow_mapping(self):
        assert parse("{a: 1, b: 2}") == {"a": 1, "b": 2}

    def test_nested_flow(self):
        assert parse("{a: [1, 2], b: {c: 3}}") == {"a": [1, 2], "b": {"c": 3}}

    def test_flow_sequence_trailing_comma(self):
        assert parse("[1, 2, 3,]") == [1, 2, 3]

    def test_empty_flow_sequence(self):
        assert parse("[]") == []

    def test_empty_flow_mapping(self):
        assert parse("{}") == {}

    def test_flow_mapping_with_quoted_keys(self):
        assert parse('{"key": "value"}') == {"key": "value"}

    def test_flow_sequence_mixed_types(self):
        assert parse("[1, true, null, 'hello']") == [1, True, None, "hello"]

    def test_flow_multiline(self):
        yaml = "[\n  1,\n  2,\n  3\n]"
        assert parse(yaml) == [1, 2, 3]


# ---------------------------------------------------------------------------
# Multi-document streams
# ---------------------------------------------------------------------------

class TestMultiDocument:
    def test_two_documents(self):
        yaml = "--- 1\n--- 2\n"
        assert parse_all(yaml) == [1, 2]

    def test_document_with_end_marker(self):
        yaml = "--- a\n...\n--- b\n"
        assert parse_all(yaml) == ["a", "b"]

    def test_empty_document(self):
        yaml = "---\n---\n"
        assert parse_all(yaml) == [None, None]

    def test_mixed_type_documents(self):
        yaml = "--- [1, 2]\n--- {a: b}\n--- scalar\n"
        assert parse_all(yaml) == [[1, 2], {"a": "b"}, "scalar"]

    def test_single_document_no_marker(self):
        assert parse_all("hello\n") == ["hello"]

    def test_parse_all_preserves_order(self):
        yaml = "".join(f"--- {i}\n" for i in range(5))
        assert parse_all(yaml) == list(range(5))


# ---------------------------------------------------------------------------
# Deep nesting
# ---------------------------------------------------------------------------

class TestDeepNesting:
    def test_deeply_nested_mapping(self):
        yaml = "a:\n  b:\n    c:\n      d: leaf\n"
        assert parse(yaml) == {"a": {"b": {"c": {"d": "leaf"}}}}

    def test_deeply_nested_sequence(self):
        yaml = "- - - - deep\n"
        result = parse(yaml)
        assert result == [[[["deep"]]]]

    def test_mixed_nesting(self):
        yaml = """\
outer:
  - a: 1
    b:
      - x
      - y
  - c: 3
"""
        result = parse(yaml)
        assert result["outer"][0]["a"] == 1
        assert result["outer"][0]["b"] == ["x", "y"]
        assert result["outer"][1]["c"] == 3


# ---------------------------------------------------------------------------
# Quoted scalars — escape sequences
# ---------------------------------------------------------------------------

class TestQuotedScalars:
    def test_double_quoted_newline_escape(self):
        assert parse(r'"line1\nline2"') == "line1\nline2"

    def test_double_quoted_tab_escape(self):
        assert parse(r'"col1\tcol2"') == "col1\tcol2"

    def test_double_quoted_backslash(self):
        assert parse(r'"back\\slash"') == "back\\slash"

    def test_double_quoted_fold(self):
        """Newlines inside double-quoted scalars fold to a space."""
        yaml = '"hello\n  world"'
        assert parse(yaml) == "hello world"

    def test_single_quoted_escape(self):
        """Single-quoted scalars only escape '' → '."""
        assert parse("'it''s'") == "it's"

    def test_single_quoted_preserves_backslash(self):
        assert parse(r"'back\slash'") == r"back\slash"

    def test_double_quoted_backslash_newline_continuation(self):
        """Backslash at end of line in double-quoted scalar: no space added."""
        yaml = '"hello \\\n  world"'
        assert parse(yaml) == "hello world"


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

class TestDirectives:
    def test_yaml_directive_ignored(self):
        yaml = "%YAML 1.2\n---\nvalue: 42\n"
        assert parse(yaml) == {"value": 42}

    def test_tag_directive_basic(self):
        """A %TAG directive is accepted without error."""
        yaml = "%TAG ! tag:example.com,2024:\n---\nvalue: hello\n"
        assert parse(yaml) == {"value": "hello"}


# ---------------------------------------------------------------------------
# Edge cases — empty / degenerate inputs
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string(self):
        assert parse("") is None

    def test_whitespace_only(self):
        assert parse("   \n  \n") is None

    def test_comment_only(self):
        assert parse("# just a comment\n") is None

    def test_null_mapping_value(self):
        assert parse("key:\n") == {"key": None}

    def test_null_sequence_item(self):
        result = parse("- \n- value\n")
        assert result[0] is None
        assert result[1] == "value"

    def test_key_with_colon_in_quoted(self):
        assert parse('{"a:b": 1}') == {"a:b": 1}

    def test_integer_key(self):
        # yamlwav converts all mapping keys to strings (JSON/config-friendly)
        result = parse("{1: one, 2: two}")
        assert result["1"] == "one"
        assert result["2"] == "two"

    def test_boolean_key(self):
        # Boolean keys are stringified (True → "True")
        result = parse("{true: yes, false: no}")
        assert result.get("True") == "yes" or result.get("true") == "yes"

    def test_multiline_plain_scalar(self):
        yaml = "value: hello\n  world\n"
        result = parse(yaml)
        assert result["value"] == "hello world"
