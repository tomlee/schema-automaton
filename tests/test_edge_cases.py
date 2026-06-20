"""Sweep tests/edge_cases.py's shared corpus across every format and a few
API operations.

Rather than hand-encoding an expected output per case (error-prone, and
indistinguishable from "the test is wrong about what should happen" when it
fails), each test below checks a general invariant the library already
documents -- e.g. "if the adjustment report is empty, the round-trip must be
exact." This is how three real bugs were found and fixed in a prior change:
each one was a case where the report was empty but the round-trip wasn't
exact, which is exactly what these invariants catch.
"""
import pytest
from edge_cases import CASES, deep_equal

from dataspec import (
    WriteError,
    check_json,
    check_toml,
    check_xml,
    check_yaml,
    doc,
    infer,
    parse_schema,
    read_json,
    read_toml,
    read_xml,
    read_yaml,
    to_dsl,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)

pytest.importorskip("yaml")

FORMATS = {
    "json": (write_json, read_json, check_json),
    "yaml": (write_yaml, read_yaml, check_yaml),
    "toml": (write_toml, read_toml, check_toml),
    "xml": (write_xml, read_xml, check_xml),
}


def _wrapped(case):
    # Wrap two levels deep so every case exercises the *value's* own
    # behavior, without also triggering top-level handling (a separate,
    # already-tested concern -- see TestReports/TestXmlReports in
    # test_formats.py). Two levels, not one, because XML additionally
    # requires its single top-level key's content to be an object/scalar,
    # not a list -- a case whose value is itself a list (e.g.
    # array_of_mixed_scalars) would make {"v": case.value} structurally
    # un-representable as a single XML document (it would need repeated
    # <v> elements), even though that's not what the case is testing.
    return {"root": {"v": case.value}}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("fmt_name", sorted(FORMATS))
def test_clean_report_implies_exact_round_trip(fmt_name, case):
    write, read, check = FORMATS[fmt_name]
    value = _wrapped(case)
    rep = check(value)
    if rep.adjustments:
        pytest.skip("documented lossy case; covered by format-specific report tests")
    back = read(write(value))
    assert deep_equal(back, value), (
        f"{fmt_name}/{case.id}: report was empty but the round-trip changed "
        f"the value\noriginal: {value!r}\nback:     {back!r}"
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("fmt_name", sorted(FORMATS))
def test_strict_raises_iff_report_has_adjustments(fmt_name, case):
    write, _read, check = FORMATS[fmt_name]
    value = _wrapped(case)
    rep = check(value)
    if rep.adjustments:
        with pytest.raises(WriteError):
            write(value, strict=True)
    else:
        assert write(value, strict=True) == write(value)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("fmt_name", sorted(FORMATS))
def test_lenient_write_and_read_never_raise(fmt_name, case):
    write, read, _check = FORMATS[fmt_name]
    value = _wrapped(case)
    read(write(value))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("dst", sorted(FORMATS))
@pytest.mark.parametrize("src", sorted(FORMATS))
def test_cross_format_conversion_never_raises(src, dst, case):
    if src == dst:
        pytest.skip("same-format path covered by test_lenient_write_and_read_never_raise")
    write_src, read_src, _ = FORMATS[src]
    write_dst, read_dst, _ = FORMATS[dst]
    value = _wrapped(case)
    intermediate = read_src(write_src(value))
    read_dst(write_dst(intermediate))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_doc_accepts_every_case_and_round_trips(case):
    value = _wrapped(case)
    d = doc(value)
    assert deep_equal(d.to_data(), value)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_infer_produces_a_schema_that_validates_its_own_sample(case):
    value = _wrapped(case)
    d = doc(value)
    result = infer([d]).validate(d)
    assert result.ok, f"{case.id}: inferred schema rejects its own sample: {result}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_inferred_schema_survives_a_dsl_round_trip(case):
    value = _wrapped(case)
    schema = infer([doc(value)])
    s2 = parse_schema(to_dsl(schema))
    assert schema.equivalent(s2), f"{case.id}: schema doesn't survive a DSL round-trip"
