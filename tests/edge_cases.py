"""A shared corpus of edge-case Document values.

Used by tests/test_edge_cases.py to sweep every format and a few API
operations over the *same* values, instead of each test file picking its own
one-off examples. Building this corpus (running each value by hand, deciding
whether the actual behavior is correct before writing an assertion) is itself
how three real bugs were found and fixed in a prior change -- see
docs/formats/overview.md's adjustment-code table for `string.ambiguous`,
`container.empty.ambiguous`, and `integer.out_of_range`.

Each case is wrapped under a single key (``{"v": case.value}``) before being
written, so every case exercises the *value's* behavior uniformly without
also triggering top-level wrapping (`toplevel.wrapped`) -- that's a separate,
already-tested concern (see TestReports / TestXmlReports in test_formats.py).
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EdgeCase:
    id: str
    value: Any


CASES = [
    # -- strings ----------------------------------------------------------
    EdgeCase("string_empty", ""),
    EdgeCase("string_whitespace_only", "   \t\n  "),
    EdgeCase("string_long", "x" * 10_000),
    EdgeCase("string_unicode", "héllo wörld 你好 😀"),
    EdgeCase("string_quotes_and_backslash", 'she said "hi"\\n\\t'),
    EdgeCase("string_embedded_newline", "line1\nline2\r\nline3"),
    EdgeCase("string_xml_illegal_chars", "<tag> & </tag>"),
    EdgeCase("string_looks_like_int", "123"),
    EdgeCase("string_looks_like_negative_int", "-123"),
    EdgeCase("string_looks_like_float", "1.5"),
    EdgeCase("string_looks_like_bool_true", "true"),
    EdgeCase("string_looks_like_bool_false", "false"),
    EdgeCase("string_looks_like_null", "null"),
    EdgeCase("string_leading_zero", "007"),
    EdgeCase("string_not_ambiguous", "Ann"),

    # -- numbers ------------------------------------------------------------
    EdgeCase("int_zero", 0),
    EdgeCase("int_negative", -42),
    # Note: "in range" here is relative to TOML's i64 bound; 2**62 is well
    # past JSON's own interop boundary (JS's 2**53 safe-integer limit), so
    # this case is clean in TOML but reported in JSON -- both correctly, per
    # each format's own check.
    EdgeCase("int_large_in_range", 2 ** 62),
    EdgeCase("int_beyond_i64", 2 ** 63),
    EdgeCase("int_i64_min_boundary", -(2 ** 63)),
    EdgeCase("int_i64_max_boundary", 2 ** 63 - 1),
    EdgeCase("int_js_safe_boundary", 2 ** 53),    # exactly at JSON's interop limit
    EdgeCase("int_beyond_js_safe", 2 ** 53 + 1),  # one past it
    EdgeCase("float_zero", 0.0),
    EdgeCase("float_negative_zero", -0.0),
    EdgeCase("float_integral", 1.0),
    EdgeCase("float_small", 1e-300),
    EdgeCase("float_large", 1e300),
    EdgeCase("float_precise", 0.1 + 0.2),
    EdgeCase("float_nan", float("nan")),
    EdgeCase("float_inf", float("inf")),
    EdgeCase("float_neg_inf", float("-inf")),

    # -- booleans -----------------------------------------------------------
    EdgeCase("bool_true", True),
    EdgeCase("bool_false", False),

    # -- null -----------------------------------------------------------
    EdgeCase("null_alone", None),
    EdgeCase("null_in_array", [1, None, 2]),
    EdgeCase("null_only_array_item", [None]),
    EdgeCase("null_object_field", {"a": 1, "b": None}),

    # -- containers -----------------------------------------------------
    EdgeCase("empty_object", {}),
    EdgeCase("empty_array", []),
    EdgeCase("nested_empty_object", {"a": {}}),
    EdgeCase("nested_empty_array", {"a": []}),
    EdgeCase("array_of_mixed_scalars", [1, "two", 3.0, True, None]),
    EdgeCase("array_of_arrays", [[1, 2], [3, 4]]),
    EdgeCase("object_key_is_builtin_name", {"items": 1, "keys": 2}),
    EdgeCase("moderately_nested", {"a": {"b": {"c": {"d": {"e": [1, 2, 3]}}}}}),

    # -- keys -----------------------------------------------------------
    # Each of these is syntactically significant in at least one format
    # (TOML: . = [ ] denote nested tables/assignment/array literals; YAML: :
    # starts a mapping value, # starts a comment) but not in the others --
    # the formats that don't care write it as-is; the ones that do quote or
    # escape it. None of these should ever raise or lose the value.
    EdgeCase("key_with_space", {"my key": 1}),
    EdgeCase("key_unicode", {"clé": "valeur"}),
    EdgeCase("key_empty_string", {"": "value"}),
    EdgeCase("key_numeric_looking", {"123": "value"}),
    EdgeCase("key_digit_prefix", {"123abc": 1}),  # illegal XML name start
    EdgeCase("key_toml_dot", {"a.b": 1}),          # TOML dotted-key syntax
    EdgeCase("key_toml_equals", {"a=b": 1}),       # TOML key/value separator
    EdgeCase("key_toml_brackets", {"a[b]": 1}),    # TOML table-array syntax
    EdgeCase("key_yaml_colon", {"a:b": 1}),        # YAML key/value separator
    EdgeCase("key_shared_hash", {"a#b": 1}),       # comment marker (TOML/YAML)

    # -- temporal -----------------------------------------------------------
    EdgeCase("date_epoch", datetime.date(1970, 1, 1)),
    EdgeCase("date_leap_day", datetime.date(2024, 2, 29)),
    EdgeCase("date_far_future", datetime.date(9999, 12, 31)),
    EdgeCase("time_midnight", datetime.time(0, 0, 0)),
    EdgeCase("datetime_naive", datetime.datetime(2024, 1, 1, 12, 0, 0)),
    EdgeCase("datetime_aware_utc",
             datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)),
]


def deep_equal(a: Any, b: Any) -> bool:
    """Like ``==``, but ``NaN == NaN`` (Python's ``nan != nan`` would make
    every case touching float_nan look like a round-trip failure)."""
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(deep_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b
