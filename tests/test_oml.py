"""Tests for OML (Omnist Markup Language) -- omnist's native codec.

Covers happy-path round-tripping of every Document shape (all seven scalars
plus null, repeated/interleaved labels, arbitrary nesting) and the edge
cases worked out in the design: string escaping, raw strings (E2), multiline
strings (E3) and their interaction with the SEP/newline separator, numeric
edge cases, reserved words, top-level brace disambiguation, the integer
digit-count limit (DoS hardening), and the nesting-depth limit.
"""
import datetime

import pytest

from omnist import Doc, ParseError, check_oml, doc, parse_schema, read_oml, write_oml
from omnist.canonical.registry import formats, get_format

# ---------------------------------------------------------------------------
# Happy paths: round-tripping every scalar kind
# ---------------------------------------------------------------------------

def test_oml_is_a_registered_format():
    assert "oml" in formats()
    fmt = get_format("oml")
    assert fmt.read is read_oml and fmt.write is write_oml and fmt.check is check_oml


@pytest.mark.parametrize("src,expected", [
    ('a: "hello"', [("a", "hello")]),
    ("a: 42", [("a", 42)]),
    ("a: -42", [("a", -42)]),
    ("a: 3.14", [("a", 3.14)]),
    ("a: -3.14", [("a", -3.14)]),
    ("a: 1e10", [("a", 1e10)]),
    ("a: 1.5e-3", [("a", 1.5e-3)]),
    ("a: true", [("a", True)]),
    ("a: false", [("a", False)]),
    ("a: null", [("a", None)]),
    ("a: 2024-01-01", [("a", datetime.date(2024, 1, 1))]),
    ("a: 12:30:00", [("a", datetime.time(12, 30, 0))]),
    ("a: 2024-01-01T12:30:00", [("a", datetime.datetime(2024, 1, 1, 12, 30, 0))]),
    ("a: nan", None),   # NaN isn't self-equal; checked separately below
    ("a: inf", [("a", float("inf"))]),
    ("a: -inf", [("a", float("-inf"))]),
])
def test_scalar_round_trip(src, expected):
    node = read_oml(src)
    if expected is None:
        import math
        assert math.isnan(node[0][1])
    else:
        assert node == expected
    # round-trips through the canonical writer
    if expected is not None:
        assert read_oml(write_oml(node)) == node


def test_empty_document_is_empty_node():
    assert read_oml("") == []
    assert read_oml("   \n  \n") == []


def test_bare_leaf_document():
    assert read_oml("42") == 42
    assert read_oml('"just a string"') == "just a string"


def test_repeated_labels_and_interleaving():
    node = read_oml("a: 1\nb: 2\na: 3\nb: 4\na: 5")
    assert node == [("a", 1), ("b", 2), ("a", 3), ("b", 4), ("a", 5)]
    d = Doc(node)
    assert d.count("a") == 3
    assert [c.value for c in d.get("a")] == [1, 3, 5]


def test_nested_braces_arbitrary_depth():
    node = read_oml('a: { b: { c: { d: "leaf" } } }')
    assert node == [("a", [("b", [("c", [("d", "leaf")])])])]


def test_inline_brace_style_with_semicolons():
    assert read_oml('{ a: 1; b: 2 }') == [("a", 1), ("b", 2)]


def test_comments_are_ignored():
    node = read_oml("# a top comment\na: 1  # trailing comment\nb: 2\n")
    assert node == [("a", 1), ("b", 2)]


# ---------------------------------------------------------------------------
# String escaping
# ---------------------------------------------------------------------------

def test_basic_escapes():
    node = read_oml(r'a: "line1\nline2\ttabbed\\backslash\"quote"')
    assert node == [("a", 'line1\nline2\ttabbed\\backslash"quote')]


def test_unicode_escape_bmp():
    assert read_oml(r'a: "é"') == [("a", "é")]


def test_unicode_escape_astral_surrogate_pair():
    assert read_oml(r'a: "😀"') == [("a", "\U0001F600")]


def test_unpaired_surrogate_rejected():
    with pytest.raises(ParseError):
        read_oml(r'a: "\uD83D"')
    with pytest.raises(ParseError):
        read_oml(r'a: "\uDE00"')


def test_control_character_must_be_escaped():
    with pytest.raises(ParseError):
        read_oml('a: "tab\there"')  # literal tab byte, not escaped


def test_writer_emits_minimal_escapes_only():
    text = write_oml([("a", 'has "quotes" and \\backslash\\ and \n newline')])
    assert text == r'a: "has \"quotes\" and \\backslash\\ and \n newline"'
    # / is never escaped on write even though \/ is accepted on read
    assert write_oml([("a", "a/b")]) == 'a: "a/b"'
    assert read_oml(r'a: "a\/b"') == [("a", "a/b")]


# ---------------------------------------------------------------------------
# Raw strings (E2)
# ---------------------------------------------------------------------------

def test_raw_string_no_escape_processing():
    node = read_oml(r"a: 'C:\talks\ada\slides.key'")
    assert node == [("a", r"C:\talks\ada\slides.key")]


def test_raw_string_cannot_contain_apostrophe():
    with pytest.raises(ParseError):
        read_oml("a: 'it''s broken'")  # terminates at the first '


def test_raw_string_canonical_writer_never_emits_it():
    node = read_oml(r"a: 'C:\x'")
    text = write_oml(node)
    assert "'" not in text
    assert text == r'a: "C:\\x"'


# ---------------------------------------------------------------------------
# Multiline strings (E3) and SEP/newline interaction
# ---------------------------------------------------------------------------

def test_multiline_basic():
    node = read_oml('a: """\nline one\nline two\n"""')
    assert node == [("a", "line one\nline two\n")]


def test_multiline_leading_newline_stripped_but_internal_kept():
    node = read_oml('a: """\nx\ny\n"""')
    assert node[0][1] == "x\ny\n"


def test_multiline_no_leading_newline_needed():
    node = read_oml('a: """same line start"""')
    assert node == [("a", "same line start")]


def test_multiline_internal_newlines_never_act_as_sep():
    node = read_oml('a: """\nx\ny\n"""\nb: 1')
    assert node == [("a", "x\ny\n"), ("b", 1)]


def test_multiline_immediately_followed_by_label_is_parse_error():
    # closing """ with no SEP before the next label -- G5 "no silent concatenation"
    with pytest.raises(ParseError):
        read_oml('a: """\nx\ny\n"""b: 1')


def test_multiline_followed_by_semicolon_sep_is_valid():
    node = read_oml('a: """\nx\ny\n""";b: 1')
    assert node == [("a", "x\ny\n"), ("b", 1)]


def test_multiline_escapes_still_processed():
    node = read_oml('a: """back\\\\slash and \\"escaped quote\\""""')
    assert node == [("a", 'back\\slash and "escaped quote"')]


@pytest.mark.parametrize("src,value", [
    ('a: """x"""', "x"),
    ('a: """"""', ""),
    ('a: """"x"""', '"x'),
    ('a: """""x"""', '""x'),
])
def test_multiline_touching_quote_runs(src, value):
    assert read_oml(src) == [("a", value)]


def test_multiline_four_touching_quotes_leaves_dangling_string():
    # open(3) + close(3) consumes 6 of the 7 quotes; 1 left over starts a new,
    # unterminated ordinary STRING token -> ParseError
    with pytest.raises(ParseError):
        read_oml('a: """""""')


def test_multiline_escaped_quote_breaks_terminator_run():
    node = read_oml('a: """x\\"""y"""')
    assert node == [("a", 'x"""y')]


def test_multiline_canonical_writer_never_emits_it():
    node = read_oml('a: """\nx\ny\n"""')
    text = write_oml(node)
    assert '"""' not in text
    assert text == 'a: "x\\ny\\n"'


# ---------------------------------------------------------------------------
# Top-level brace / structural disambiguation
# ---------------------------------------------------------------------------

def test_brace_must_wrap_entire_document():
    with pytest.raises(ParseError):
        read_oml("{ a: 1 }\nb: 2")


def test_one_set_of_braces_around_everything_is_fine():
    assert read_oml("{ a: 1; b: 2 }") == [("a", 1), ("b", 2)]


def test_two_bare_leaves_is_an_error():
    with pytest.raises(ParseError):
        read_oml("42\n43")


def test_empty_braces_is_empty_node():
    assert read_oml("{ ;;; }") == []
    assert read_oml("{ }") == []


def test_two_edges_without_separator_is_error():
    with pytest.raises(ParseError):
        read_oml("a: 1 b: 2")


def test_two_edges_with_newline_separator_is_fine():
    assert read_oml("a: 1\nb: 2") == [("a", 1), ("b", 2)]


# ---------------------------------------------------------------------------
# Reserved words and labels
# ---------------------------------------------------------------------------

def test_reserved_word_as_bare_label_is_error():
    with pytest.raises(ParseError):
        read_oml("true: 1")


def test_quoted_reserved_word_label_is_fine():
    assert read_oml('"true": 1') == [("true", 1)]


def test_nullable_is_not_reserved():
    assert read_oml("nullable: 1") == [("nullable", 1)]


def test_capitalized_nan_is_bare_ident_not_keyword():
    with pytest.raises(ParseError):
        read_oml("a: NaN")
    assert read_oml('a: "NaN"') == [("a", "NaN")]


def test_label_cannot_start_with_digit():
    with pytest.raises(ParseError):
        read_oml("123: 1")
    assert read_oml('"123": 1') == [("123", 1)]


def test_hyphenated_label():
    assert read_oml("a-b: 1") == [("a-b", 1)]


# ---------------------------------------------------------------------------
# Numeric edge cases
# ---------------------------------------------------------------------------

def test_negative_zero_integer_is_exactly_zero():
    node = read_oml("a: -0")
    assert node[0][1] == 0
    assert not isinstance(node[0][1], bool)


def test_negative_zero_float_is_sign_preserving():
    import math
    node = read_oml("a: -0.0")
    assert math.copysign(1.0, node[0][1]) == -1.0


def test_integer_digit_limit_enforced():
    ok = "9" * 4300
    assert read_oml(f"a: {ok}")[0][1] == int(ok)
    too_big = "9" * 4301
    with pytest.raises(ParseError):
        read_oml(f"a: {too_big}")


def test_overflow_and_underflow_are_defined_not_errors():
    assert read_oml("a: 1e400")[0][1] == float("inf")
    assert read_oml("a: 1e-400")[0][1] == 0.0


# ---------------------------------------------------------------------------
# Depth limit
# ---------------------------------------------------------------------------

def test_nesting_depth_limit():
    too_deep = "a: " + "{ b: " * 201 + "1" + " }" * 201
    with pytest.raises(ParseError):
        read_oml(too_deep)


# ---------------------------------------------------------------------------
# BOM / encoding
# ---------------------------------------------------------------------------

def test_bom_is_ignored():
    assert read_oml("﻿a: 1") == [("a", 1)]


# ---------------------------------------------------------------------------
# Document round-trip: every scalar kind, repeats, interleaving, nesting
# ---------------------------------------------------------------------------

def test_full_document_round_trip_lossless():
    node = [
        ("title", "Conference"),
        ("attendee", "Ann"),
        ("session", [
            ("id", 1),
            ("active", True),
        ]),
        ("attendee", "Bob"),
        ("session", [
            ("id", 2),
            ("active", False),
        ]),
        ("when", datetime.datetime(2024, 1, 1, 9, 30)),
        ("opens", datetime.time(9, 0)),
        ("on", datetime.date(2024, 6, 1)),
        ("price", 29.99),
        ("capacity", 4300 and 250),
        ("notes", None),
    ]
    text = write_oml(node)
    assert read_oml(text) == node
    # OML never needs an adjustment -- check_oml is always empty
    assert list(check_oml(node)) == []


def test_doc_to_oml_and_from_oml_methods():
    d = doc({"name": "Ann", "tags": ["x", "y"]})
    text = d.to_oml()
    d2 = Doc.from_oml(text)
    assert d2.to_grouped() == d.to_grouped()


# ---------------------------------------------------------------------------
# Schema-directed read
# ---------------------------------------------------------------------------

def test_schema_directed_deserialization():
    s = parse_schema('record R { "d": date, "n": number }\nroot R')
    node = read_oml('d: "2024-01-01"\nn: 3', schema=s)
    assert node == [("d", datetime.date(2024, 1, 1)), ("n", 3.0)]


def test_validate_against_schema_after_read():
    s = parse_schema(
        'record Member { "name": string, "role": string }\n'
        'record Team { "name": string, "members" [1,]: Member }\nroot Team')
    d = Doc.from_oml(
        'name: "Platform"\n'
        'members: {\n'
        '  name: "Ann"\n'
        '  role: "dev"\n'
        '}\n'
    )
    assert s.validate(d).ok


# ---------------------------------------------------------------------------
# Full real-life document (matches the design doc's worked example)
# ---------------------------------------------------------------------------

REAL_LIFE_OML = r'''
venue: {
    name: "Strange Loop"
    building: {
        address: {
            street: "123 Main St"
            city: "St. Louis"
            country: "US"
        }
        room: "Ballroom A"
    }
}
session: {
    title: "Schema Compatibility, Revisited"
    speaker: {
        name: "Ada Lovelace"
        bio: """
Works on data models and provenance.
Quote: "Hopper said it best".
Path: C:\\talks\\ada\\slides.key
"""
    }
    note: "Recording starts five minutes late."
    note: 'Slides posted after the talk -- path on the laptop: C:\talks\ada\slides.key'
    start: 2024-09-18T14:00:00
    duration: 50
    tags: "schemas"
    tags: "compatibility"
}
attendee_count: 312
virtual: false
'''


def test_real_life_document_round_trips():
    node = read_oml(REAL_LIFE_OML)
    d = Doc(node)
    assert d.get_one("venue").get_one("name").value == "Strange Loop"
    address = d.get_one("venue").get_one("building").get_one("address")
    assert address.get_one("city").value == "St. Louis"
    session = d.get_one("session")
    assert [t.value for t in session.get("tags")] == ["schemas", "compatibility"]
    assert [n.value for n in session.get("note")] == [
        "Recording starts five minutes late.",
        "Slides posted after the talk -- path on the laptop: C:\\talks\\ada\\slides.key",
    ]
    bio = session.get_one("speaker").get_one("bio").value
    assert bio.startswith("Works on data models")
    assert 'Quote: "Hopper said it best".' in bio
    assert session.get_one("start").value == datetime.datetime(2024, 9, 18, 14, 0, 0)

    text = write_oml(node)
    assert read_oml(text) == node


def test_real_life_document_validates_against_a_schema():
    s = parse_schema('''
        record Address { "street": string, "city": string, "country": string }
        record Building { "address": Address, "room": string }
        record Venue { "name": string, "building": Building }
        record Speaker { "name": string, "bio": string }
        record Session {
            "title": string,
            "speaker": Speaker,
            "note" [0,]: string,
            "start": datetime,
            "duration": integer,
            "tags" [0,]: string,
        }
        record Root {
            "venue": Venue,
            "session": Session,
            "attendee_count": integer,
            "virtual": boolean,
        }
        root Root
    ''')
    d = Doc.from_oml(REAL_LIFE_OML)
    result = s.validate(d)
    assert result.ok, result.errors
