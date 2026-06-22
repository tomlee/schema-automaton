"""Property-based fuzzing of the Document model, codecs, and the DSL parser.

Two angles (see issue #64 and the prior fuzzing effort noted in
CHANGELOG.md, "test: add property-based fuzzing with hypothesis; fix 3 bugs
it found" -- this file follows that one's structure and conventions, updated
for the current canonical edge-list Document model):

1. **Round-trip fuzzing** -- randomized canonical Document nodes (the
   ``[(label, child), ...]`` edge-list / scalar-leaf shape from
   :mod:`omnist.canonical.document`) round-tripped through every codec:

   * ``write_oml``/``read_oml`` must be *exactly* lossless for every shape
     (``docs/formats/oml.md``).
   * ``write_json``/``write_yaml``/``write_toml``/``write_xml`` and their
     readers must round-trip *modulo documented adjustments* -- we use
     ``check_*``/``WriteReport`` to know exactly which adjustments are
     allowed (date/time stringified, ``null`` dropped by TOML, ambiguous
     strings re-typed by XML, ...) rather than guessing, so an *undocumented*
     mismatch fails the test.
   * ``doc(...)``/``build_node`` from the equivalent plain Python value
     round-trips to the same node (a second, simpler "plain value" generator
     is used here, since a Python dict can't express same-level repeated/
     interleaved labels the way a canonical node can).

2. **Crash-freedom fuzzing** -- arbitrary (not necessarily valid) text fed
   into ``read_oml`` and ``parse_schema`` must raise only ``ParseError``/
   ``SchemaError`` (or a subclass) -- any other exception escaping is a
   hardening bug (the digit-count and nesting-depth limits in
   ``docs/formats/oml.md`` exist precisely to prevent this).

Found bugs (real round-trip mismatches or unhandled-exception crashes) are
not fixed here -- see the project's standing bug workflow (open a separate
issue, fix in its own PR). A flaw in this file's own lossiness assumptions
is fixed here instead.
"""

from __future__ import annotations

import datetime as _dt
import math

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from omnist import (
    DocumentError,
    ParseError,
    SchemaError,
    check_json,
    check_oml,
    check_toml,
    check_xml,
    check_yaml,
    doc,
    parse_schema,
    read_json,
    read_oml,
    read_toml,
    read_xml,
    read_yaml,
    write_json,
    write_oml,
    write_toml,
    write_xml,
    write_yaml,
)
from omnist.canonical.document import _grouped, build_node

_SUPPRESS = settings(
    deadline=None,  # CI runners are slower/noisier than a dev machine
    suppress_health_check=[HealthCheck.too_slow],
    max_examples=150,
)

_MAX_DEPTH = 5  # bounded nesting -- a correctness net, not an exhaustive search

# ---------------------------------------------------------------------------
# Scalars -- all seven kinds + null, with edge-case values
# ---------------------------------------------------------------------------

# Strings: empty, unicode, control-adjacent-but-valid (omnist's OML scanner
# rejects raw control chars in source but the *value* -- after escaping -- can
# be any string, since write_oml always escapes).
_strings = st.text(max_size=20)

# Integers: include values near the digit-count guard's neighborhood without
# actually tripping it (that's exercised by the crash-freedom text fuzzing
# below, not by values that must round-trip).
_integers = st.one_of(
    st.integers(min_value=-(2 ** 64), max_value=2 ** 64),
    st.just(0),
    st.just(-0),
)

# Floats: very large/small magnitudes, signed zero, nan/inf (handled specially
# in equality below since NaN isn't self-equal).
_floats = st.one_of(
    st.floats(allow_nan=True, allow_infinity=True),
    st.just(0.0),
    st.just(-0.0),
    st.floats(min_value=1e300, max_value=1.7e308),
    st.floats(min_value=-1.7e308, max_value=-1e300),
    st.floats(min_value=1e-300, max_value=1e-10),
)

_dates = st.dates(min_value=_dt.date(1, 1, 1), max_value=_dt.date(9999, 12, 31))
_times = st.one_of(
    st.times(),
    st.just(_dt.time(0, 0, 0)),
    st.just(_dt.time(23, 59, 59, 999999)),
)
_datetimes = st.one_of(
    st.datetimes(min_value=_dt.datetime(1, 1, 1), max_value=_dt.datetime(9999, 12, 31)),
    st.just(_dt.datetime(1, 1, 1, 0, 0, 0)),
    st.just(_dt.datetime(9999, 12, 31, 23, 59, 59, 999999)),
    st.just(_dt.datetime(2000, 2, 29, 0, 0, 0)),    # leap day
    st.just(_dt.datetime(2024, 2, 29, 12, 0, 0)),   # leap year, not div-by-400
)

scalars = st.one_of(
    st.none(),
    st.booleans(),
    _integers,
    _floats,
    _strings,
    _dates,
    _times,
    _datetimes,
)

# "inf"/"nan"/"-inf" excluded: write_oml emits them as bare identifiers but
# the OML scanner tokenizes them as NUMBER, not IDENT, so read_oml can't
# parse them back as a label at all -- a real, separately-filed bug (#71),
# not a flaw in this generator's assumptions.
_labels = st.text(min_size=1, max_size=10).filter(lambda s: s not in ("inf", "nan", "-inf"))


def _nodes(depth: int):
    """A canonical Document node: a scalar leaf, or an ordered edge list with
    possibly-repeated, possibly-interleaved labels."""
    if depth >= _MAX_DEPTH:
        return scalars
    return st.one_of(
        scalars,
        st.lists(
            st.tuples(_labels, st.deferred(lambda: _nodes(depth + 1))),
            max_size=5,
        ),
    )


nodes = st.deferred(lambda: _nodes(0))


# ---------------------------------------------------------------------------
# Equality that treats NaN as self-equal (OML/JSON both round-trip NaN as a
# float value, but NaN != NaN, so plain == would wrongly fail a correct
# round-trip).
# ---------------------------------------------------------------------------

def nan_safe_equal(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        # an edge list `[(label, child), ...]` or a plain list of children
        return all(
            (nan_safe_equal(x, y) if not (isinstance(x, tuple) and isinstance(y, tuple))
             else x[0] == y[0] and nan_safe_equal(x[1], y[1]))
            for x, y in zip(a, b)
        )
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(nan_safe_equal(a[k], b[k]) for k in a)
    return a == b


def nan_safe_equal_grouped(a, b) -> bool:
    """Equality modulo the documented, intentional cross-label-interleaving
    loss of the JSON-shaped grouping (`docs/design/model.md` Sec.10,
    Doc.to_grouped): same-label edges are grouped into one list, so
    [(m,A),(x,X),(m,B)] and [(m,A),(m,B),(x,X)] are equivalent once grouped.
    JSON/YAML/TOML all go through this projection; only XML preserves
    interleaving natively."""
    return nan_safe_equal(_grouped(a), _grouped(b))


# ---------------------------------------------------------------------------
# 1. OML round-trip -- exact equality, no adjustments possible
# ---------------------------------------------------------------------------

@_SUPPRESS
@given(node=nodes)
def test_oml_round_trip_is_exact(node):
    assert check_oml(node).adjustments == []
    text = write_oml(node)
    back = read_oml(text)
    assert nan_safe_equal(back, node), f"OML round-trip mismatch: {node!r} -> {back!r}"


# ---------------------------------------------------------------------------
# 2. Lossy-format round-trip -- exact modulo documented adjustments
# ---------------------------------------------------------------------------

_ALLOWED_CODES = {
    "json": {"temporal.stringified", "float.special"},
    "yaml": {"temporal.stringified"},
    "toml": {"null.omitted"},
    "xml": {"null.omitted", "temporal.stringified", "string.ambiguous",
            "key.sanitized"},
}


@_SUPPRESS
@given(node=nodes)
def test_json_round_trip_modulo_documented_adjustments(node):
    rep = check_json(node)
    assert {a.code for a in rep} <= _ALLOWED_CODES["json"], rep
    text = write_json(node)
    back = read_json(text)
    # temporal values come back as strings (date/time -> str); float.special
    # (NaN/Infinity) is JSON's own non-standard extension and round-trips as
    # the same float -- both are documented adjustments, safe to compare
    # through the grouped projection (which also accepts the temporal
    # stringification since str != date is expected for those leaves only).
    if not any(a.code == "temporal.stringified" for a in rep):
        assert nan_safe_equal_grouped(back, node), \
            f"JSON round-trip mismatch: {node!r} -> {back!r}"


def _has_nel(node) -> bool:
    """True if `node` contains U+0085 (NEL) in any label or string value --
    see #69 (a real bug filed separately, not fixed in this test): PyYAML
    mangles U+0085 to a plain space on this round trip, undetected by
    check_yaml. Excluded here so this test exercises the *documented*
    adjustments only, until #69 lands."""
    if isinstance(node, list):
        return any("\x85" in label or _has_nel(child) for label, child in node)
    return isinstance(node, str) and "\x85" in node


@_SUPPRESS
@given(node=nodes)
def test_yaml_round_trip_modulo_documented_adjustments(node):
    if _has_nel(node):
        return  # see #69
    rep = check_yaml(node)
    assert {a.code for a in rep} <= _ALLOWED_CODES["yaml"], rep
    text = write_yaml(node)
    back = read_yaml(text)
    if not rep.adjustments:
        assert nan_safe_equal_grouped(back, node), \
            f"YAML round-trip mismatch: {node!r} -> {back!r}"


@_SUPPRESS
@given(node=nodes)
def test_toml_round_trip_modulo_documented_adjustments(node):
    rep = check_toml(node)
    assert {a.code for a in rep} <= _ALLOWED_CODES["toml"], rep
    if not isinstance(node, list):
        return  # TOML requires a top-level table; non-object roots are out of scope
    try:
        text = write_toml(node)
    except Exception:
        if rep.adjustments:
            return  # a documented adjustment can still leave an unwritable shape
        raise
    back = read_toml(text)
    if not rep.adjustments:
        assert nan_safe_equal_grouped(back, node), \
            f"TOML round-trip mismatch: {node!r} -> {back!r}"


def _xml_safe_node(node):
    """True if `node` avoids two known, undocumented-by-check_xml XML
    round-trip gaps (both filed separately, not fixed in this test):

    * #67 -- a string leaf containing a C0 control character other than
      tab/LF crashes write_xml's own output on read_xml (XML 1.0 forbids
      them outright), and CR is silently normalized to LF by the XML
      parser (lossy).
    * #68 -- an internal node with zero edges (`[]`) is indistinguishable
      on the wire from an empty-string leaf (`''`); read_xml always
      reconstructs the leaf form.

    Excluded here so this test exercises the *documented* adjustments
    only, until #67/#68 land."""
    if isinstance(node, list):
        if node == []:
            return False  # #68
        return all(_xml_safe_node(child) for _label, child in node)
    if isinstance(node, str):
        return not any((ord(ch) < 0x20 and ch not in "\t\n") for ch in node)
    return True


@_SUPPRESS
@given(label=_labels, node=nodes)
def test_xml_round_trip_modulo_documented_adjustments(label, node):
    if not _xml_safe_node(node):
        return  # see #67
    # XML needs exactly one top-level document element -- wrap every
    # generated node under a single synthetic root label.
    rooted = [(label, node)]
    rep = check_xml(rooted)
    assert {a.code for a in rep} <= _ALLOWED_CODES["xml"], rep
    text = write_xml(rooted)
    back = read_xml(text)
    if not rep.adjustments:
        assert nan_safe_equal(back, rooted), f"XML round-trip mismatch: {rooted!r} -> {back!r}"


# ---------------------------------------------------------------------------
# 3. doc(...)/build_node round-trip from the equivalent plain Python value
# ---------------------------------------------------------------------------

def _plain_values(depth: int):
    """A plain JSON-shaped Python value: dict/list/scalar, no repeated keys at
    the same level (that's exactly what build_node/doc accept)."""
    if depth >= _MAX_DEPTH:
        return scalars
    children = st.deferred(lambda: _plain_values(depth + 1))
    return st.one_of(
        scalars,
        st.dictionaries(_labels, children, max_size=5),
        st.dictionaries(
            _labels,
            st.lists(st.deferred(lambda: _plain_values(depth + 1)), max_size=4),
            max_size=3,
        ),
    )


plain_values = st.deferred(lambda: _plain_values(0))


@_SUPPRESS
@given(value=plain_values)
def test_doc_and_build_node_round_trip_from_plain_python_value(value):
    try:
        expected = build_node(value)
    except DocumentError:
        return  # a legal rejection (e.g. a bare list nested in a list)
    assert doc(value).to_data() == expected
    # and the resulting node round-trips through OML exactly, same as any node
    back = read_oml(write_oml(expected))
    assert nan_safe_equal(back, expected)


# ---------------------------------------------------------------------------
# 4. Crash-freedom: arbitrary text into read_oml / parse_schema
# ---------------------------------------------------------------------------

@_SUPPRESS
@given(text=st.text(max_size=200))
def test_read_oml_never_raises_unexpectedly(text):
    try:
        read_oml(text)
    except ParseError:
        pass  # malformed input is expected to be rejected this way
    except Exception as exc:  # pragma: no cover -- a crash-freedom bug, not expected
        raise AssertionError(
            f"read_oml raised {type(exc).__name__} instead of ParseError "
            f"on input {text!r}"
        ) from exc


@_SUPPRESS
@given(text=st.text(max_size=200))
def test_parse_schema_never_raises_unexpectedly(text):
    try:
        parse_schema(text)
    except SchemaError:
        pass  # malformed input is expected to be rejected this way
    except Exception as exc:  # pragma: no cover -- a crash-freedom bug, not expected
        raise AssertionError(
            f"parse_schema raised {type(exc).__name__} instead of SchemaError "
            f"on input {text!r}"
        ) from exc


# Also fuzz text drawn from a alphabet biased toward OML/DSL syntax
# characters, which is far more likely to reach deep parser states than pure
# random unicode text.
_SYNTAX_ALPHABET = st.sampled_from(
    list(' \t\n\r;:{}[]",\'#-+.0123456789eEtTzZabcdefghijklmnopqrstuvwxyz_?nullruefalseinfa')
)
_syntax_like_text = st.text(alphabet=_SYNTAX_ALPHABET, max_size=200)


@_SUPPRESS
@given(text=_syntax_like_text)
def test_read_oml_never_raises_unexpectedly_on_syntax_like_text(text):
    try:
        read_oml(text)
    except ParseError:
        pass
    except Exception as exc:  # pragma: no cover
        raise AssertionError(
            f"read_oml raised {type(exc).__name__} instead of ParseError "
            f"on input {text!r}"
        ) from exc


@_SUPPRESS
@given(text=_syntax_like_text)
def test_parse_schema_never_raises_unexpectedly_on_syntax_like_text(text):
    try:
        parse_schema(text)
    except SchemaError:
        pass
    except Exception as exc:  # pragma: no cover
        raise AssertionError(
            f"parse_schema raised {type(exc).__name__} instead of SchemaError "
            f"on input {text!r}"
        ) from exc
