"""Property-based fuzzing of the format codecs, Doc, and the DSL parser.

tests/edge_cases.py's corpus is a fixed, hand-curated list -- good for
pinning known-tricky values, but it only catches what a human thought to
include. The properties below generate randomized input instead, to catch
the same *class* of bug (a hand-written recursive function crashing on a
shape nobody happened to write a test for) without needing to anticipate the
specific shape. Two real bugs (read_json/read_toml leaking the underlying
parser's native exception instead of ParseError, and write_xml embedding
literal control characters that don't parse as XML at all) were found while
building this file, the same way bugs were found building edge_cases.py.
"""

from edge_cases import deep_equal
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dataspec import (
    DocumentError,
    ParseError,
    SchemaError,
    WriteError,
    doc,
    parse_schema,
    read_json,
    read_toml,
    read_xml,
    read_yaml,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)

_SUPPRESS = settings(
    deadline=None,  # CI runners are slower/noisier than a dev machine
    suppress_health_check=[HealthCheck.too_slow],
)

scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2 ** 62), max_value=2 ** 62),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=20),
    st.dates(),
    st.times(),
    st.datetimes(),
)

documents = st.recursive(
    scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=5),
    ),
    max_leaves=30,
)

FORMATS = {
    "json": (write_json, read_json),
    "yaml": (write_yaml, read_yaml),
    "toml": (write_toml, read_toml),
    "xml": (write_xml, read_xml),
}


@_SUPPRESS
@given(value=documents)
def test_doc_never_raises_unexpectedly(value):
    wrapped = {"v": value}
    try:
        d = doc(wrapped)
    except DocumentError:
        return  # a legal rejection (e.g. nesting past the depth limit)
    assert deep_equal(d.to_data(), wrapped)


@_SUPPRESS
@given(value=documents)
def test_lenient_round_trip_never_crashes(value):
    wrapped = {"v": value}
    for write, read in FORMATS.values():
        try:
            text = write(wrapped)
        except DocumentError:
            continue  # a legal rejection (e.g. nesting past the depth limit)
        except WriteError:
            # XML only: {"v": value} isn't single-rooted when value is
            # itself a list, or becomes empty after null-stripping -- an
            # intentional, always-raise rejection (no lossless fallback
            # shape exists), not a crash.
            continue
        read(text)  # lenient mode must never raise


@_SUPPRESS
@given(text=st.text(max_size=200))
def test_parse_schema_never_crashes_on_arbitrary_text(text):
    try:
        parse_schema(text)
    except SchemaError:
        pass  # malformed input is expected to be rejected this way


@_SUPPRESS
@given(text=st.text(max_size=200))
def test_read_never_crashes_on_arbitrary_text(text):
    for _write, read in FORMATS.values():
        try:
            read(text)
        except ParseError:
            pass  # malformed input is expected to be rejected this way


@_SUPPRESS
@given(value=documents)
def test_infer_always_validates_its_own_sample(value):
    from dataspec import infer

    wrapped = {"v": value}
    try:
        d = doc(wrapped)
    except DocumentError:
        return
    try:
        result = infer([d]).validate(d)
    except SchemaError:
        # documented, intentional: infer() rejects a position that mixes an
        # object/array with a scalar, or an object with an array (see
        # docs/infer.md) -- not a crash, just an unsupported shape.
        return
    assert result.ok, f"inferred schema rejects its own sample: {result}"


@_SUPPRESS
@given(d1=st.dates(), d2=st.dates(), dt1=st.datetimes(), dt2=st.datetimes())
def test_date_and_datetime_values_round_trip_through_toml_exactly(d1, d2, dt1, dt2):
    # TOML's standout feature is native temporal types -- spot-check that
    # randomized dates/datetimes never hit a corner the fixed corpus missed.
    value = {"a": d1, "b": d2, "c": dt1, "d": dt2}
    assert read_toml(write_toml(value)) == value
