"""Tests for the canonical (redesigned) Document and Schema models.

Covers the design in docs/design/model.md: edge-list Document, record/Ref
schema with exactly seven scalars, field cardinality, conformance, OSD,
operations, and codecs.
"""
import datetime

import pytest

from omnist.canonical import (
    Doc,
    Field,
    Format,
    Record,
    Ref,
    Scalar,
    Schema,
    ValidationResult,
    WriteReport,
    check_json,
    check_toml,
    check_xml,
    check_yaml,
    compatible_with,
    doc,
    equivalent,
    field,
    formats,
    get_format,
    infer,
    materialize,
    normalize,
    parse_schema,
    read_json,
    read_toml,
    read_xml,
    read_yaml,
    record,
    ref,
    register_format,
    schema,
    t,
    to_osd,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)
from omnist.canonical.oml import check_oml
from omnist.canonical.schema import matches_kind, value_kind
from omnist.errors import DocumentError, ParseError, SchemaError, WriteError

yaml = pytest.importorskip("yaml")


# ----------------------------------------------------------- public API
class TestPublicApi:
    """The `import omnist` surface: schema operations as methods, the `t`
    builder namespace, validation, codecs."""

    def test_methods_and_t_namespace(self):
        import omnist as ds

        s = ds.parse_schema('record R { "n": integer, "s": string? }\nroot R')
        assert ds.__version__ == "0.2.10"
        # operations are Schema methods
        assert s.validate(ds.doc({"n": 1, "s": None})).ok
        assert s.equivalent(ds.parse_schema(ds.to_osd(s)))
        wide = ds.parse_schema('record R { "n": number, "s": string? }\nroot R')
        assert s.compatible_with(wide)
        assert s.normalize().equivalent(s)
        # the t namespace, used directly as a field's type -- no wrapping
        b = ds.schema(ds.ref("R"), R=ds.record(ds.field("v", ds.nullable(ds.t.integer))))
        assert b.validate(ds.doc({"v": 7})).ok
        assert b.validate(ds.doc({"v": None})).ok
        assert not b.validate(ds.doc({"v": "other"})).ok

    def test_old_names_are_gone(self):
        import omnist as ds
        for name in ("obj", "arr", "ObjectType", "ArrayType", "ScalarType", "mapping",
                     "Union", "union"):
            assert not hasattr(ds, name), f"{name} should be removed (clean break)"


# ----------------------------------------------------------- Document
class TestDocument:
    def test_build_and_navigate(self):
        d = doc({"name": "Ann", "age": 30})
        assert not d.is_leaf
        assert d.labels() == ["name", "age"]
        assert d.get_one("name").value == "Ann"
        assert d.get_one("age").value == 30

    def test_repeated_label_is_an_array(self):
        d = doc({"member": [{"n": 1}, {"n": 2}]})
        assert d.count("member") == 2
        members = d.get("member")
        assert members[0].get_one("n").value == 1
        assert members[1].get_one("n").value == 2

    def test_to_data_is_edge_list(self):
        d = doc({"a": 1, "xs": [1, 2]})
        assert d.to_data() == [("a", 1), ("xs", 1), ("xs", 2)]

    def test_to_grouped_projects_back(self):
        d = doc({"a": 1, "xs": [1, 2]})
        assert d.to_grouped() == {"a": 1, "xs": [1, 2]}

    def test_bare_array_rejected(self):
        with pytest.raises(DocumentError):
            doc([1, 2, 3])

    def test_array_of_arrays_rejected(self):
        with pytest.raises(DocumentError):
            doc({"m": [[1, 2], [3, 4]]})

    def test_non_string_key_rejected(self):
        with pytest.raises(DocumentError):
            doc({1: "a"})

    def test_editing(self):
        d = doc({"name": "Ann"})
        d.add("tag", "x").add("tag", "y")            # repeated label = array
        assert d.count("tag") == 2
        d.set("name", "Bob")
        assert d.get_one("name").value == "Bob"
        d.set("age", 30)                             # set() on an absent label adds it
        assert d.get_one("age").value == 30
        d.remove("tag")
        assert d.count("tag") == 0
        # nested editing through a cursor shares the underlying structure
        d2 = doc({"addr": {"city": "X"}})
        d2.child("addr").set("city", "Y")
        assert d2.to_grouped() == {"addr": {"city": "Y"}}


class TestInfer:
    def test_flat(self):
        from omnist.canonical import infer
        s = infer([doc({"name": "Ann", "age": 30}), doc({"name": "Bob"})])
        assert s.validate(doc({"name": "Cy"})).ok           # age optional
        assert not s.validate(doc({"age": 1})).ok           # name required

    def test_array_and_nested(self):
        from omnist.canonical import infer
        s = infer([doc({"id": 1, "tags": ["a", "b"], "addr": {"city": "X"}})])
        assert s.validate(doc({"id": 9, "tags": ["c"], "addr": {"city": "Y"}})).ok
        assert not s.validate(doc({"id": 9, "tags": [1], "addr": {"city": "Y"}})).ok

    def test_accepts_its_own_samples(self):
        from omnist.canonical import infer
        samples = [doc({"v": 1}), doc({"v": 2.5})]          # int + float -> number
        s = infer(samples)
        for sm in samples:
            assert s.validate(sm).ok

    def test_conflicting_scalars_raise(self):
        from omnist.canonical import infer
        with pytest.raises(SchemaError):
            infer([doc({"v": 1}), doc({"v": "x"})])

    def test_null_only_field_infers_nullable_string(self):
        from omnist.canonical import infer
        s = infer([doc({"v": None}), doc({"v": None})])
        assert s.validate(doc({"v": None})).ok
        assert s.validate(doc({"v": "anything"})).ok

    def test_null_alongside_a_kind_is_orthogonal(self):
        from omnist.canonical import infer
        s = infer([doc({"v": 1}), doc({"v": None})])
        assert s.validate(doc({"v": 7})).ok
        assert s.validate(doc({"v": None})).ok
        assert not s.validate(doc({"v": "x"})).ok

    def test_optional_field_detection_is_order_independent(self):
        # a field absent from an early sample but present in a later one
        # must still infer as optional, regardless of which sample order
        # it's passed in
        from omnist.canonical import infer
        absent_first = infer([doc({"host": "a"}), doc({"host": "b", "port": 80})])
        absent_last = infer([doc({"host": "b", "port": 80}), doc({"host": "a"})])
        assert absent_first.equivalent(absent_last)

        port = absent_first.env["Root"].fields[1]
        assert port.label == "port"
        assert (port.min, port.max) == (0, 1)

        assert absent_first.validate(doc({"host": "x"})).ok
        assert absent_first.validate(doc({"host": "x", "port": 1})).ok


# ----------------------------------------------------------- OSD + validation
def valid(text, data):
    return parse_schema(text).validate(doc(data))


class TestValidation:
    def test_scalar_kinds(self):
        s = 'record R { "n": integer, "s": string }\nroot R'
        assert valid(s, {"n": 1, "s": "x"}).ok
        assert not valid(s, {"n": "x", "s": "x"}).ok

    def test_required_and_optional(self):
        s = 'record R { "name": string, "age" [0,1]: integer }\nroot R'
        assert valid(s, {"name": "a"}).ok
        assert valid(s, {"name": "a", "age": 3}).ok
        assert not valid(s, {"age": 3}).ok               # name required

    def test_closed_rejects_unexpected(self):
        s = 'record R { "a": integer }\nroot R'
        r = valid(s, {"a": 1, "b": 2})
        assert not r.ok
        assert any("unexpected field" in m for _, m in r.errors)

    def test_array_cardinality(self):
        s = 'record R { "xs" [0,]: integer }\nroot R'
        assert valid(s, {"xs": [1, 2, 3]}).ok
        assert valid(s, {}).ok                            # 0 occurrences ok
        s2 = 'record R { "xs" [1,]: integer }\nroot R'
        assert not valid(s2, {}).ok                       # needs at least one
        assert valid(s2, {"xs": [1]}).ok
        s3 = 'record R { "xs" [2]: integer }\nroot R'
        assert valid(s3, {"xs": [1, 2]}).ok
        assert not valid(s3, {"xs": [1]}).ok

    def test_nullable(self):
        s2 = 'record R { "note": string? }\nroot R'
        assert valid(s2, {"note": None}).ok
        assert valid(s2, {"note": "hi"}).ok
        assert not valid(s2, {"note": 1}).ok

    def test_integer_satisfies_number(self):
        s = 'record R { "v": number }\nroot R'
        assert valid(s, {"v": 7}).ok
        assert valid(s, {"v": 7.5}).ok
        assert not valid(s, {"v": "x"}).ok

    def test_ref_and_recursion(self):
        s = ('record Node { "value": integer, "kids" [0,]: Node }\nroot Node')
        assert valid(s, {"value": 1, "kids": [{"value": 2, "kids": []}]}).ok
        assert not valid(s, {"value": 1, "kids": [{"value": "x", "kids": []}]}).ok

    def test_question_mark_on_ref_is_error(self):
        with pytest.raises(SchemaError):
            parse_schema('record A { "x": integer }\nrecord R { "a": A? }\nroot R')

    def test_enum_syntax_is_rejected(self):
        # the '|' character itself isn't in the grammar at all anymore, so
        # this is rejected by the tokenizer, before the parser ever gets to
        # look at what's in type position
        with pytest.raises(SchemaError, match="unexpected character '\\|'"):
            parse_schema('record R { "status": "open" | "closed" }\nroot R')

    def test_literal_valued_field_is_rejected(self):
        # a single literal (no '|') reaches the parser and is rejected by
        # _type() itself, with a more specific message than a bad character
        with pytest.raises(SchemaError, match="enums and literal-valued fields"):
            parse_schema('record R { "status": "open" }\nroot R')
        with pytest.raises(SchemaError, match="enums and literal-valued fields"):
            parse_schema('record R { "n": 5 }\nroot R')

    def test_union_keyword_is_rejected(self):
        with pytest.raises(SchemaError):
            parse_schema('union License { "auto", "manual" }\nrecord R { "a": integer }\nroot R')


# ----------------------------------------------------- OSD parser robustness
class TestOsdRobustness:
    """Regressions for three real defects found by probing the parser
    against its own grammar: a crash, a broken depth guard, and a silent
    name-shadowing footgun."""

    def test_float_cardinality_raises_cleanly(self):
        # used to crash with an uncaught ValueError instead of SchemaError
        with pytest.raises(SchemaError):
            parse_schema('record R { "a" [1.5,3]: integer }\nroot R')

    def test_many_flat_definitions_are_not_rejected(self):
        # the old "depth guard" counted total '{' across the whole file, so
        # 150 unrelated, non-nested records were falsely rejected even
        # though nothing here recurses at all
        flat = "".join(f'record R{i} {{ "a": integer }}\n' for i in range(150))
        s = parse_schema(flat + "root R0")
        assert s.root.name == "R0"

    def test_record_named_a_scalar_keyword_is_rejected(self):
        # used to silently succeed, but the record could never be
        # referenced -- "string" in a type position always meant the
        # builtin scalar, never a Ref to this record
        with pytest.raises(SchemaError):
            parse_schema('record string { "x": integer }\nrecord R { "a": string }\nroot R')

    def test_record_named_a_non_scalar_word_is_fine(self):
        s = parse_schema('record Address { "city": string }\nrecord R { "a": Address }\nroot R')
        assert s.validate(doc({"a": {"city": "X"}})).ok


# --------------------------------------------- date/time/datetime boundary
class TestTemporalBoundary:
    """date / time / datetime are mutually exclusive, including for the
    string form (dates/times arrive as ISO-8601 text from JSON/XML).
    datetime.fromisoformat is lenient -- a bare date-only string parses fine,
    defaulting the missing time to midnight -- so a bare date string must
    NOT satisfy datetime, only date."""

    DATE = 'record R { "v": date }\nroot R'
    TIME = 'record R { "v": time }\nroot R'
    DATETIME = 'record R { "v": datetime }\nroot R'

    def test_bare_date_string_satisfies_only_date(self):
        v = "2024-01-01"
        assert valid(self.DATE, {"v": v}).ok
        assert not valid(self.DATETIME, {"v": v}).ok
        assert not valid(self.TIME, {"v": v}).ok

    def test_bare_time_string_satisfies_only_time(self):
        v = "12:00:00"
        assert valid(self.TIME, {"v": v}).ok
        assert not valid(self.DATE, {"v": v}).ok
        assert not valid(self.DATETIME, {"v": v}).ok

    def test_full_timestamp_string_satisfies_only_datetime(self):
        for v in ("2024-01-01T12:00:00", "2024-01-01T00:00:00"):
            assert valid(self.DATETIME, {"v": v}).ok, v
            assert not valid(self.DATE, {"v": v}).ok, v
            assert not valid(self.TIME, {"v": v}).ok, v

    def test_unparseable_string_satisfies_none(self):
        v = "not-a-date"
        assert not valid(self.DATE, {"v": v}).ok
        assert not valid(self.TIME, {"v": v}).ok
        assert not valid(self.DATETIME, {"v": v}).ok

    def test_real_objects_unaffected(self):
        import datetime as dt
        assert valid(self.DATETIME, {"v": dt.datetime(2024, 1, 1, 12, 0)}).ok
        assert not valid(self.DATETIME, {"v": dt.date(2024, 1, 1)}).ok
        assert valid(self.DATE, {"v": dt.date(2024, 1, 1)}).ok
        assert not valid(self.DATE, {"v": dt.datetime(2024, 1, 1, 12, 0)}).ok


# ----------------------------------------------------------- OSD round-trip
OSD_CASES = [
    'record R { "n": integer }\nroot R',
    'record R { "n": integer, "s": string? }\nroot R',
    'record R { "status": string }\nroot R',
    'record R { "v": number }\nroot R',
    'record R { "xs" [0,]: integer }\nroot R',
    'record R { "xs" [1,5]: string }\nroot R',
    'record R { "xs" [2]: integer }\nroot R',
    'record R { "first name": string }\nroot R',
    'record M { "name": string }\nrecord R { "m" [0,]: M }\nroot R',
    'record Node { "v": integer, "kids" [0,]: Node }\nroot Node',
]


@pytest.mark.parametrize("text", OSD_CASES)
def test_osd_round_trip(text):
    s = parse_schema(text)
    s2 = parse_schema(to_osd(s))
    assert equivalent(s, s2), f"\n{text}\n->\n{to_osd(s)}"


# ----------------------------------------------------------- operations
class TestOperations:
    def test_added_optional_field_is_compatible(self):
        v1 = parse_schema('record R { "a": integer }\nroot R')
        v2 = parse_schema('record R { "a": integer, "b" [0,1]: integer }\nroot R')
        assert compatible_with(v1, v2)
        assert not compatible_with(v2, v1)

    def test_required_to_optional_is_compatible(self):
        strict = parse_schema('record R { "a": integer, "b": integer }\nroot R')
        loose = parse_schema('record R { "a": integer, "b" [0,1]: integer }\nroot R')
        assert compatible_with(strict, loose)
        assert not compatible_with(loose, strict)

    def test_integer_is_compatible_with_number(self):
        narrow = parse_schema('record R { "v": integer }\nroot R')
        wide = parse_schema('record R { "v": number }\nroot R')
        assert compatible_with(narrow, wide)
        assert not compatible_with(wide, narrow)

    def test_nullable_is_one_directional(self):
        narrow = parse_schema('record R { "v": string }\nroot R')
        wide = parse_schema('record R { "v": string? }\nroot R')
        assert compatible_with(narrow, wide)
        assert not compatible_with(wide, narrow)

    def test_array_bounds(self):
        a = parse_schema('record R { "xs" [2,3]: integer }\nroot R')
        b = parse_schema('record R { "xs" [1,5]: integer }\nroot R')
        assert compatible_with(a, b)
        assert not compatible_with(b, a)

    def test_temporal_date_not_compatible_with_string(self):
        from omnist.canonical import DATE, STRING
        a = schema(ref("R"), R=record(field("d", DATE)))
        b = schema(ref("R"), R=record(field("d", STRING)))
        assert not compatible_with(a, b)

    def test_equivalent_reordered(self):
        a = parse_schema('record R { "a": integer, "b": string }\nroot R')
        b = parse_schema('record R { "b": string, "a": integer }\nroot R')
        assert equivalent(a, b)

    def test_normalize_merges_identical(self):
        s = parse_schema('record A { "x": integer }\nrecord B { "x": integer }\n'
                         'record R { "a": A, "b": B }\nroot R')
        n = normalize(s)
        assert len(n.env) < len(s.env)
        assert equivalent(s, n)


# ----------------------------------------------------------- codecs
class TestMalformedInput:
    def test_invalid_json_raises_parse_error(self):
        with pytest.raises(ParseError, match="invalid JSON"):
            read_json("{not json")

    def test_invalid_yaml_raises_parse_error(self):
        with pytest.raises(ParseError, match="invalid YAML"):
            read_yaml("a: [1, 2\n")

    def test_invalid_toml_raises_parse_error(self):
        with pytest.raises(ParseError, match="invalid TOML"):
            read_toml("not [ valid toml")

    def test_invalid_xml_raises_parse_error(self):
        with pytest.raises(ParseError, match="invalid XML"):
            read_xml("<unclosed>")


class TestCodecs:
    SCHEMA = ('record Member { "name": string, "role": string }\n'
              'record Team { "name": string, "members" [0,]: Member }\nroot Team')

    def test_json_round_trip(self):
        d = read_json('{"name":"P","members":[{"name":"Ann","role":"dev"},'
                      '{"name":"Bob","role":"pm"}]}')
        s = parse_schema(self.SCHEMA)
        assert s.validate(Doc(d)).ok
        # two members -> a list (count > 1), unambiguous
        assert read_json(write_json(d)) == d

    def test_count_one_serializes_bare_without_a_schema(self):
        # the documented count-1 ambiguity: a single-element array projects to
        # a bare value when no schema is available (schema-less fallback).
        d = read_json('{"members":[{"name":"Ann"}]}')
        assert write_json(d) == '{"members": {"name": "Ann"}}'

    def test_write_json_rejects_unsupported_scalar(self):
        # A node built by hand (bypassing build_node's type check) can carry
        # a leaf value that's neither a JSON-native type nor date/time/
        # datetime -- json.dumps' default= hook then raises TypeError.
        class Unsupported:
            pass
        with pytest.raises(TypeError, match="cannot serialize"):
            write_json([("a", Unsupported())])

    def test_all_formats_same_document(self):
        j = read_json('{"name":"P","members":[{"name":"Ann","role":"dev"},'
                      '{"name":"Bob","role":"pm"}]}')
        y = read_yaml("name: P\nmembers:\n  - name: Ann\n    role: dev\n"
                      "  - name: Bob\n    role: pm\n")
        t = read_toml('name = "P"\n[[members]]\nname = "Ann"\nrole = "dev"\n'
                      '[[members]]\nname = "Bob"\nrole = "pm"\n')
        assert j == y == t

    def test_xml_is_single_rooted(self):
        # XML wraps in one document element -> a single top-level edge.
        d = read_xml("<team><name>P</name><member>x</member><member>y</member></team>")
        assert d == [("team", [("name", "P"), ("member", "x"), ("member", "y")])]
        # round-trips
        assert read_xml(write_xml(d)) == d

    def test_xml_interleaving_preserved_in_document(self):
        # the edge list keeps order, including a label between two repeats
        d = read_xml("<t><m>a</m><x>1</x><m>b</m></t>")
        assert d == [("t", [("m", "a"), ("x", 1), ("m", "b")])]

    def test_xml_write_needs_single_root(self):
        with pytest.raises(WriteError):
            write_xml([("a", 1), ("b", 2)])      # two top-level edges

    def test_xml_label_sanitized_when_not_a_valid_xml_name(self):
        # a label with spaces/punctuation isn't a valid XML name -- write_xml
        # sanitizes it (and prefixes "_" if sanitizing leaves nothing usable).
        out = write_xml([("a b", "1")])
        assert "<a_b>" in out

    def test_xml_label_starting_with_digit_gets_underscore_prefix(self):
        out = write_xml([("1tag", "x")])
        assert "<_1tag>" in out

    def test_xml_leaf_types_round_trip_as_text(self):
        # bool/None/date leaves all go through _xml_text's special-casing.
        d = [("r", [("flag", True), ("nothing", None),
                    ("d", datetime.date(2024, 1, 1))])]
        out = write_xml(d)
        assert "<flag>true</flag>" in out
        assert "<nothing />" in out or "<nothing/>" in out or "<nothing></nothing>" in out
        assert "<d>2024-01-01</d>" in out

    def test_xml_text_coerces_empty_and_boolish_strings(self):
        d = read_xml("<r><a></a><b>true</b><c>false</c></r>")
        assert d == [("r", [("a", ""), ("b", True), ("c", False)])]

    def test_xml_parser_falls_back_to_stdlib_without_defusedxml(self):
        # When defusedxml isn't installed, read_xml() must still work, via the
        # standard library parser, with a warning about the XXE risk.
        import builtins

        from omnist.canonical.formats import _xml_parser
        from omnist.errors import UnsafeXMLWarning

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("defusedxml"):
                raise ImportError("simulated: defusedxml not installed")
            return real_import(name, *args, **kwargs)

        import unittest.mock
        with unittest.mock.patch("builtins.__import__", side_effect=fake_import):
            with pytest.warns(UnsafeXMLWarning):
                ET = _xml_parser()
        import xml.etree.ElementTree as stdlib_ET
        assert ET is stdlib_ET


# ----------------------------------------------------- schema-directed deserialization
class TestDeserialize:
    """``materialize`` (and the ``schema=`` kwarg on read_*) upgrades leaf
    values to match what the schema declares, when the conversion is
    value-exact, and raises otherwise."""

    SCHEMA = ('record R { "d": date, "t": time, "dt": datetime, "n": number, '
              '"i": integer, "s": string, "b": boolean }\nroot R')

    def test_iso_strings_become_real_temporal_objects(self):
        s = parse_schema(self.SCHEMA)
        node = read_json(
            '{"d":"2024-01-01","t":"12:00:00","dt":"2024-01-01T10:00:00",'
            '"n":1,"i":1,"s":"x","b":true}', schema=s)
        values = dict(node)
        assert values["d"] == datetime.date(2024, 1, 1)
        assert values["t"] == datetime.time(12, 0)
        assert values["dt"] == datetime.datetime(2024, 1, 1, 10, 0)

    def test_numeric_exactness_both_directions(self):
        s = parse_schema('record R { "n": number, "i": integer }\nroot R')
        node = read_json('{"n": 3, "i": 4.0}', schema=s)
        values = dict(node)
        assert values["n"] == 3.0 and isinstance(values["n"], float)
        assert values["i"] == 4 and isinstance(values["i"], int)

    def test_inexact_numeric_conversion_raises(self):
        s = parse_schema('record R { "i": integer }\nroot R')
        with pytest.raises(ParseError):
            read_json('{"i": 4.5}', schema=s)

    def test_unparseable_value_raises(self):
        s = parse_schema(self.SCHEMA)
        with pytest.raises(ParseError):
            read_json('{"d":1,"t":"12:00:00","dt":"x","n":1,"i":1,"s":"x","b":true}',
                      schema=s)
        with pytest.raises(ParseError):
            read_json('{"d":"2024-01-01","t":"12:00:00","dt":"x","n":1,"i":1,'
                      '"s":"x","b":true}', schema=s)

    def test_already_typed_values_pass_through(self):
        s = parse_schema(self.SCHEMA)
        node = read_json(
            '{"d":"2024-01-01","t":"12:00:00","dt":"2024-01-01T10:00:00",'
            '"n":1,"i":1,"s":"x","b":true}', schema=s)
        again = materialize(node, s)
        assert again == node

    def test_unknown_field_raises(self):
        # a schema is a request for a guaranteed-conforming Document --
        # an unexpected field is a shape problem, and now raises too
        s = parse_schema('record R { "a": integer }\nroot R')
        with pytest.raises(ParseError, match="unexpected field"):
            read_json('{"a": 1, "b": "extra"}', schema=s)
        assert read_json('{"a": 1}') == [("a", 1)]      # no schema -> unchanged

    def test_shape_mismatches_raise(self):
        # a record expected but the node holds a scalar, or vice versa
        s = parse_schema('record R { "a": R2 }\nrecord R2 { "x": integer }\nroot R')
        with pytest.raises(ParseError, match="expected an object"):
            materialize([("a", 5)], s)
        s2 = parse_schema('record R { "a": integer }\nroot R')
        with pytest.raises(ParseError, match="expected a integer value"):
            materialize([("a", [("x", 1)])], s2)

    def test_missing_field_raises(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        with pytest.raises(ParseError, match="expected exactly 1"):
            materialize([], s)

    def test_multiple_problems_all_reported_together(self):
        s = parse_schema('record R { "a": integer, "b": string }\nroot R')
        with pytest.raises(ParseError) as exc:
            materialize([("a", "x"), ("c", 1)], s)
        msg = str(exc.value)
        assert "unexpected field" in msg          # "c"
        assert "cannot be read as integer" in msg  # "a"
        assert "expected exactly 1" in msg          # missing "b"

    def test_bool_never_satisfies_integer_or_number(self):
        # bool is an int subclass, but a Scalar("integer")/Scalar("number")
        # must reject it explicitly -- "True" is not a value-exact 1
        s = parse_schema('record R { "i": integer, "n": number }\nroot R')
        with pytest.raises(ParseError):
            materialize([("i", True)], s)
        with pytest.raises(ParseError):
            materialize([("n", True)], s)

    def test_a_real_datetime_object_never_satisfies_date(self):
        s = parse_schema('record R { "d": date }\nroot R')
        with pytest.raises(ParseError):
            materialize([("d", datetime.datetime(2024, 1, 1, 9, 0))], s)

    def test_bare_date_string_never_satisfies_datetime(self):
        s = parse_schema('record R { "dt": datetime }\nroot R')
        with pytest.raises(ParseError):
            materialize([("dt", "2024-01-01")], s)

    def test_schema_directed_via_doc_from_json(self):
        from omnist.canonical import Doc
        s = parse_schema('record R { "d": date }\nroot R')
        d = Doc.from_json('{"d": "2024-01-01"}', schema=s)
        assert d.get_one("d").value == datetime.date(2024, 1, 1)

    def test_schema_directed_via_doc_from_yaml_toml_xml(self):
        s = parse_schema('record R { "d": date }\nroot R')
        assert Doc.from_yaml('d: "2024-01-01"\n', schema=s).get_one("d").value == \
            datetime.date(2024, 1, 1)
        assert Doc.from_toml('d = "2024-01-01"\n', schema=s).get_one("d").value == \
            datetime.date(2024, 1, 1)
        sx = parse_schema('record Root { "d": date }\nroot Root')
        assert Doc.from_xml("<d>2024-01-01</d>", schema=sx).get_one("d").value == \
            datetime.date(2024, 1, 1)

    def test_xml_temporal_round_trip(self):
        # the XML document element's tag is the schema's single top-level
        # field label (here "t"), per the single-rooted Document model
        s = parse_schema('record Item { "d": date }\nrecord Root { "t": Item }\nroot Root')
        node = read_xml("<t><d>2024-01-01</d></t>", schema=s)
        assert dict(dict(node)["t"])["d"] == datetime.date(2024, 1, 1)


# ----------------------------------------------------------- adjustment reports
class TestReports:
    def test_toml_drops_null_with_a_warning(self):
        node = doc({"a": 1, "b": None}).to_data()
        rep = check_toml(node)
        assert [a.code for a in rep] == ["null.omitted"]
        assert rep.warnings and not rep.errors
        assert "b" not in write_toml(node)

    def test_toml_strict_raises_on_null(self):
        node = doc({"a": 1, "b": None}).to_data()
        with pytest.raises(WriteError):
            write_toml(node, strict=True)

    def test_toml_clean_write_has_empty_report(self):
        node = doc({"a": 1}).to_data()
        rep = WriteReport()
        write_toml(node, report=rep)
        assert rep.adjustments == []
        assert bool(rep) is True

    def test_json_temporal_and_special_float(self):
        node = doc({"d": datetime.date(2024, 1, 1)}).to_data()
        rep = check_json(node)
        assert [a.code for a in rep] == ["temporal.stringified"]
        assert write_json(node) == '{"d": "2024-01-01"}'   # actually adjusted, not just reported
        node2 = [("x", float("nan"))]
        rep2 = check_json(node2)
        assert [a.code for a in rep2] == ["float.special"]
        assert rep2.errors

    def test_xml_null_omitted(self):
        node = doc({"a": None}).to_data()
        rep = check_xml(node)
        assert [a.code for a in rep] == ["null.omitted"]

    def test_yaml_time_is_stringified(self):
        node = doc({"t": datetime.time(9, 30)}).to_data()
        rep = check_yaml(node)
        assert [a.code for a in rep] == ["temporal.stringified"]
        assert "09:30:00" in write_yaml(node)

    def test_yaml_nel_value_round_trips_and_is_reported(self):
        # U+0085 (NEL) is normalized to a space by YAML's default scalar
        # styles; omnist forces double-quoted style for it so it round-trips.
        node = [("a", "\x85")]
        rep = check_yaml(node)
        assert [a.code for a in rep] == ["string.line-break-char"]
        assert read_yaml(write_yaml(node)) == node

    def test_yaml_nel_label_round_trips_and_is_reported(self):
        node = [("\x85", None)]
        rep = check_yaml(node)
        assert [a.code for a in rep] == ["string.line-break-char"]
        assert read_yaml(write_yaml(node)) == node

    def test_xml_sanitizes_bad_key_and_reports_temporal(self):
        node = doc({"r": {"a b": 1, "d": datetime.date(2024, 1, 1)}}).to_data()
        rep = check_xml(node)
        codes = {a.code for a in rep}
        assert "key.sanitized" in codes
        assert "temporal.stringified" in codes

    def test_report_arg_and_strict_share_events(self):
        node = doc({"a": 1, "b": None}).to_data()
        rep = WriteReport()
        with pytest.raises(WriteError) as ei:
            write_toml(node, strict=True, report=rep)
        assert [a.code for a in rep] == ["null.omitted"]
        assert ei.value.report.errors == [] and ei.value.report.warnings


# ----------------------------------------------------------- format registry
class TestRegistry:
    def test_builtins_registered(self):
        assert set(formats()) >= {"json", "yaml", "toml", "xml"}

    def test_get_format_round_trips(self):
        fmt = get_format("json")
        node = fmt.read('{"a": 1}')
        assert fmt.write(node) == '{"a": 1}'

    def test_unknown_format_raises(self):
        from omnist.errors import OmnistError
        with pytest.raises(OmnistError):
            get_format("nope")

    def test_register_a_plugin(self):
        register_format(Format(
            "lines",
            read=lambda text: [("n", int(x)) for x in text.split()],
            write=lambda node, **o: " ".join(str(c) for _, c in node),
        ))
        assert "lines" in formats()
        d = Doc.from_format("lines", "1 2 3")
        assert d.to_format("lines") == "1 2 3"

    def test_plugin_without_check_raises_on_check_format(self):
        register_format(Format(
            "nocheck",
            read=lambda text: [("n", int(x)) for x in text.split()],
            write=lambda node, **o: " ".join(str(c) for _, c in node),
        ))
        with pytest.raises(DocumentError):
            Doc.from_format("nocheck", "1 2 3").check_format("nocheck")


# ----------------------------------------------------- Doc.check_* parity
class TestDocCheckParity:
    def test_check_methods_match_module_functions(self):
        node = doc({"a": 1, "b": None}).to_data()
        d = Doc(node)
        assert [a.code for a in d.check_toml()] == [a.code for a in check_toml(node)]
        assert [a.code for a in d.check_json()] == [a.code for a in check_json(node)]
        assert [a.code for a in d.check_yaml()] == [a.code for a in check_yaml(node)]

    def test_check_xml_matches(self):
        node = doc({"r": {"a b": 1}}).to_data()
        d = Doc(node)
        assert [a.code for a in d.check_xml()] == [a.code for a in check_xml(node)]

    def test_check_oml_matches(self):
        node = doc({"a": 1, "b": None}).to_data()
        d = Doc(node)
        assert [a.code for a in d.check_oml()] == [a.code for a in check_oml(node)]

    def test_check_format_matches_named_method(self):
        d = doc({"a": 1, "b": None})
        assert [a.code for a in d.check_format("toml")] == [a.code for a in d.check_toml()]


# ----------------------------------------------------------------- WriteReport
class TestWriteReportStr:
    def test_str_with_no_adjustments(self):
        assert str(WriteReport()) == "no adjustments"

    def test_str_with_adjustments(self):
        node = doc({"a": 1, "b": None}).to_data()
        rep = check_toml(node)
        assert str(rep) == "\n".join(
            f"{a.severity}: {a.path}: {a.message}" for a in rep)
        assert "null value dropped" in str(rep)


# ----------------------------------------------------------- OSD error paths
class TestOsdErrors:
    """Every distinct error the parser can raise, found by reading the
    grammar against the implementation -- not just the happy path."""

    def test_missing_colon(self):
        with pytest.raises(SchemaError, match="expected ':'"):
            parse_schema('record R { "a" integer }\nroot R')

    def test_garbage_top_level_token(self):
        with pytest.raises(SchemaError, match="expected 'record' or 'root'"):
            parse_schema('bogus X\nroot R')

    def test_missing_root_declaration(self):
        with pytest.raises(SchemaError, match="must declare a root"):
            parse_schema('record R { "a": integer }')

    def test_duplicate_definition(self):
        with pytest.raises(SchemaError, match="duplicate definition 'A'"):
            parse_schema('record A { "x": integer }\nrecord A { "y": string }\nroot A')

    def test_unquoted_field_label(self):
        with pytest.raises(SchemaError, match="expected a quoted field name"):
            parse_schema('record R { x: integer }\nroot R')

    def test_empty_cardinality(self):
        with pytest.raises(SchemaError, match="empty cardinality"):
            parse_schema('record R { "a" []: integer }\nroot R')

    def test_missing_closing_brace(self):
        with pytest.raises(SchemaError):
            parse_schema('record R { "a": integer\nroot R')

    def test_unknown_referenced_name(self):
        with pytest.raises(SchemaError, match="unknown type 'Missing'"):
            parse_schema('record R { "a": Missing }\nroot R')


# --------------------------------------------------- Document robustness
class TestDocumentRobustness:
    """The recursion/cycle guards SECURITY.md describes -- verified, not
    just asserted."""

    def test_deeply_nested_input_raises_cleanly(self):
        value = "leaf"
        for _ in range(250):
            value = {"x": value}
        with pytest.raises(DocumentError, match="nesting exceeds the maximum depth"):
            doc(value)

    def test_self_referential_dict_raises_cleanly(self):
        d = {}
        d["self"] = d
        with pytest.raises(DocumentError, match="cycle detected"):
            doc(d)

    def test_unsupported_python_type_raises(self):
        with pytest.raises(DocumentError, match="is not a Document value"):
            doc({"a": {1, 2, 3}})

    def test_value_on_internal_node_raises(self):
        d = doc({"a": 1})
        with pytest.raises(DocumentError, match="not a leaf"):
            d.value

    def test_edges_on_leaf_raises(self):
        d = doc({"a": 1}).get_one("a")
        with pytest.raises(DocumentError, match="a leaf has no edges"):
            d.edges()

    def test_get_one_wrong_count_raises(self):
        d = doc({"a": 1, "b": 2})
        with pytest.raises(DocumentError, match="found 0"):
            d.get_one("missing")
        d2 = doc({"a": 1, "a2": 2})
        d2._node.append(("a", 3))  # force a second "a" via direct node access
        with pytest.raises(DocumentError, match="found 2"):
            d2.get_one("a")

    def test_editing_a_leaf_raises(self):
        leaf = doc({"a": 1}).get_one("a")
        with pytest.raises(DocumentError, match="cannot add on a leaf"):
            leaf.add("x", 1)
        with pytest.raises(DocumentError, match="cannot set on a leaf"):
            leaf.set("x", 1)
        with pytest.raises(DocumentError, match="cannot remove on a leaf"):
            leaf.remove("x")

    def test_eq_against_non_document_value(self):
        assert doc({"a": 1}) != {1, 2, 3}    # a set has no Document form

    def test_repr(self):
        assert repr(doc(1)) == "Doc(leaf: 1)"
        assert "node:" in repr(doc({"a": 1}))

    def test_doc_to_json_yaml_xml_methods(self):
        d = doc({"a": 1})
        assert d.to_json() == '{"a": 1}'
        assert d.to_yaml() == "a: 1\n"
        assert d.to_xml() == "<a>1</a>"

    def test_doc_equals_doc(self):
        assert doc({"a": 1}) == doc({"a": 1})
        assert doc({"a": 1}) != doc({"a": 2})

    def test_doc_validate_delegates_to_schema(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        assert doc({"a": 1}).validate(s).ok


# --------------------------------------------------------- Schema/builder misuse
class TestSchemaConstructionErrors:
    """Defensive validation in the model classes themselves, not just
    OSD -- the Python builder is just as much a public surface."""

    def test_field_type_must_be_ref_or_scalar(self):
        with pytest.raises(SchemaError, match="must be a Ref or Scalar"):
            Field("x", "not-a-type")

    def test_field_invalid_cardinality(self):
        with pytest.raises(SchemaError, match="invalid cardinality"):
            Field("x", t.string, min=2, max=1)

    def test_record_duplicate_label(self):
        with pytest.raises(SchemaError, match="duplicate field label"):
            Record([Field("a", t.string), Field("a", t.integer)])

    def test_schema_root_must_be_a_ref(self):
        with pytest.raises(SchemaError, match="root must be a Ref"):
            Schema("R", {})

    def test_schema_env_value_must_be_a_record(self):
        # a loosely-typed caller (the schema()/Schema() constructors don't
        # enforce this at the type level) handing in a bare Scalar used to
        # crash with AttributeError instead of raising SchemaError
        with pytest.raises(SchemaError, match="must be a Record"):
            schema(ref("R"), R=t.string)


# ----------------------------------------------------------------- dunders
class TestSchemaModelDunders:
    """__repr__/__eq__/__hash__/__str__/__bool__ on the small model classes
    -- not exercised by the OSD/validation-focused tests elsewhere."""

    def test_scalar_unknown_name_raises(self):
        with pytest.raises(SchemaError, match="unknown scalar"):
            Scalar("not-a-real-scalar")

    def test_scalar_eq_and_hash(self):
        assert Scalar("string") == Scalar("string")
        assert Scalar("string") != Scalar("integer")
        assert Scalar("string") != "string"          # not a Scalar at all
        assert hash(Scalar("string")) == hash(Scalar("string"))

    def test_ref_repr_eq_and_hash(self):
        assert repr(Ref("R")) == "ref(R)"
        assert Ref("R") == Ref("R")
        assert Ref("R") != Ref("S")
        assert Ref("R") != "R"
        assert hash(Ref("R")) == hash(Ref("R"))

    def test_types_namespace_repr(self):
        assert "seven scalars" in repr(t)

    def test_field_cardinality_str_zero_or_one(self):
        f = Field("x", t.string, min=0, max=1)
        assert f.cardinality_str() == "0 or 1"

    def test_field_repr(self):
        f = Field("x", t.string, min=0, max=2)
        assert repr(f) == "Field('x'[0,2]: string)"

    def test_record_repr(self):
        rec = Record([Field("a", t.string)])
        assert repr(rec) == "record{Field('a'[1,1]: string)}"

    def test_validation_result_bool_str_repr(self):
        ok = ValidationResult()
        assert bool(ok) is True
        assert str(ok) == "valid"
        assert repr(ok) == "ValidationResult(ok=True, errors=0)"

        bad = ValidationResult()
        bad.add("$.a", "boom")
        assert bool(bad) is False
        assert str(bad) == "invalid:\n  at $.a: boom"
        assert repr(bad) == "ValidationResult(ok=False, errors=1)"

    def test_schema_repr(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        assert repr(s) == "Schema(root=ref(R), env=['R'])"

    def test_resolve_cyclic_reference_raises(self):
        # check_refs() (run at construction) requires every env value to be
        # a Record, so resolve()'s while-loop can never naturally see the
        # same Ref name twice through the public API -- env[name] always
        # becomes a Record after one hop. The cycle guard is defense in
        # depth for a caller who mutates .env directly after construction
        # (env is a plain public dict, not enforced immutable).
        s = schema(ref("A"), A=record(field("x", ref("A"), min=0, max=1)))
        s.env["A"] = ref("A")
        with pytest.raises(SchemaError, match="cyclic reference chain"):
            s.resolve(ref("A"))

    def test_resolve_unknown_type_raises(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        with pytest.raises(SchemaError, match="unknown type 'Ghost'"):
            s.resolve(ref("Ghost"))

    def test_validate_requires_a_doc(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        with pytest.raises(TypeError, match=r"validate\(\) expects a Doc"):
            s.validate({"a": 1})

    def test_accepts_delegates_to_validate(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        assert s.accepts(doc({"a": 1})) is True
        assert s.accepts(doc({"a": "x"})) is False

    def test_conform_scalar_leaf_required_got_object(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        bad = doc({"a": {"nested": 1}})
        res = s.validate(bad)
        assert not res.ok
        assert any("got an object" in e.message for e in res.errors)

    def test_conform_scalar_null_not_allowed(self):
        s = parse_schema('record R { "a": integer }\nroot R')
        bad = doc({"a": None})
        res = s.validate(bad)
        assert not res.ok
        assert any("null not allowed here" in e.message for e in res.errors)

    def test_conform_record_leaf_required_object(self):
        s = parse_schema('record Inner { "x": integer }\nrecord R { "a": Inner }\nroot R')
        bad = doc({"a": 1})
        res = s.validate(bad)
        assert not res.ok
        assert any("expected an object, got a value" in e.message for e in res.errors)


# ------------------------------------------------------- matches_kind / value_kind
class TestMatchesKindAndValueKind:
    def test_matches_kind_time_object(self):
        assert matches_kind(datetime.time(12, 0), "time")

    def test_matches_kind_datetime_not_a_date(self):
        assert not matches_kind(datetime.datetime(2024, 1, 1), "date")

    def test_value_kind_temporal_types(self):
        assert value_kind(datetime.datetime(2024, 1, 1)) == "datetime"
        assert value_kind(datetime.date(2024, 1, 1)) == "date"
        assert value_kind(datetime.time(12, 0)) == "time"

    def test_value_kind_boolean(self):
        assert value_kind(True) == "boolean"

    def test_matches_kind_unknown_name_never_matches(self):
        # matches_kind is only ever called by _conform_scalar with a name
        # taken from a Scalar, and Scalar.__init__ already restricts names
        # to SCALAR_NAMES -- so an unrecognized name can't arrive through
        # the public API. This guards the function's own contract directly.
        assert matches_kind("anything", "not-a-real-scalar-name") is False


# ----------------------------------------------------------- infer() errors
class TestInferErrors:
    def test_zero_samples_raises(self):
        with pytest.raises(SchemaError, match="zero samples"):
            infer([])

    def test_non_object_root_raises(self):
        with pytest.raises(SchemaError, match="object .record. samples"):
            infer([doc(5)])

    def test_mixed_object_and_scalar_for_one_label_raises(self):
        with pytest.raises(SchemaError, match="mixes objects and values"):
            infer([doc({"a": {"x": 1}}), doc({"a": 5})])

    def test_generated_record_names_dont_collide(self):
        # "item" and "Item" both capitalize to the generated name "Item"
        s = infer([doc({"item": {"a": 1}, "Item": {"b": 2}})])
        assert {"Item", "Item2"} <= set(s.env)


# --------------------------------------------------- operations edge cases
class TestOperationsEdgeCases:
    def test_scalar_vs_record_never_compatible(self):
        a = parse_schema('record R { "v": integer }\nroot R')
        b = parse_schema('record R { "v": V }\nrecord V { "x": integer }\nroot R')
        assert not compatible_with(a, b)
        assert not compatible_with(b, a)

    def test_a_must_guarantee_every_field_b_requires(self):
        a = parse_schema('record R { "v": integer }\nroot R')
        b = parse_schema('record R { "v": integer, "w": string }\nroot R')
        # b requires "w"; a has no "w" at all (not just insufficient cardinality)
        assert not compatible_with(a, b)

    def test_unbounded_max_not_compatible_with_a_bounded_one(self):
        a = parse_schema('record R { "xs" [1,]: integer }\nroot R')    # unbounded
        b = parse_schema('record R { "xs" [1,5]: integer }\nroot R')   # bounded
        assert not compatible_with(a, b)
        assert compatible_with(b, a)

    def test_extra_field_b_doesnt_know_about_is_not_compatible(self):
        a = parse_schema('record R { "v": integer, "extra": string }\nroot R')
        b = parse_schema('record R { "v": integer }\nroot R')          # closed, no "extra"
        assert not compatible_with(a, b)

    def test_a_field_with_max_zero_is_skipped_even_if_b_lacks_it(self):
        # cardinality [0,0] means the field is declared but never actually
        # emitted -- B doesn't need to know about it at all
        a = parse_schema('record R { "never" [0,0]: integer, "v": integer }\nroot R')
        b = parse_schema('record R { "v": integer }\nroot R')
        assert compatible_with(a, b)


# --------------------------------------------------------- XML adjustment codes
class TestXmlAdjustmentCodes:
    def test_string_ambiguous_code(self):
        # a string that looks like a number/bool reads back as that type from
        # XML text, since XML has no native type tagging -- check_xml flags it
        node = doc({"a": "123"}).to_data()
        rep = check_xml(node)
        assert [a.code for a in rep] == ["string.ambiguous"]

    def test_empty_internal_node_vs_empty_string_leaf(self):
        # An internal node with zero edges ([]) and a leaf holding the empty
        # string ('') both serialize to the same XML element, <tag />, so
        # read_xml can't tell them apart -- see issue #68.
        empty_internal = [("A", [])]
        empty_leaf = [("A", "")]

        # Both write to the identical XML text.
        assert write_xml(empty_internal) == write_xml(empty_leaf)

        # Writing the empty internal node is the lossy direction: check_xml
        # flags it, and reading it back never reconstructs [] -- it always
        # comes back as the empty-string leaf.
        rep_internal = check_xml(empty_internal)
        assert [a.code for a in rep_internal] == ["shape.empty_ambiguous"]
        assert read_xml(write_xml(empty_internal)) == [("A", "")]
        assert read_xml(write_xml(empty_internal)) != empty_internal

        # Writing the empty-string leaf is not lossy: it round-trips fine and
        # is not flagged.
        rep_leaf = check_xml(empty_leaf)
        assert list(rep_leaf) == []
        assert read_xml(write_xml(empty_leaf)) == empty_leaf

    def test_illegal_xml_control_char_is_sanitized_and_reported(self):
        # XML 1.0 forbids most C0 control characters in character data (only
        # tab/LF/CR and U+0020+ are legal).  write_xml used to emit them
        # verbatim, producing text that read_xml's own parser then rejected
        # -- see issue #67.  It should now substitute U+FFFD and flag it.
        node = [("a", "x\x08y")]
        rep = check_xml(node)
        assert [a.code for a in rep] == ["string.illegal_xml_char"]
        assert rep.errors                      # error severity, not a warning

        text = write_xml(node)
        assert "\x08" not in text              # the illegal byte is gone
        assert "�" in text                # replaced with U+FFFD
        assert read_xml(text) == [("a", "x�y")]   # round-trips cleanly now

        with pytest.raises(WriteError) as ei:
            write_xml(node, strict=True)
        assert [a.code for a in ei.value.report] == ["string.illegal_xml_char"]

    def test_carriage_return_normalization_is_reported(self):
        # CR is legal XML, but XML's mandated line-ending normalization on
        # parse turns '\r' (and '\r\n') into '\n', so it's a documented,
        # non-error lossiness rather than a crash -- see issue #67.
        node = [("a", "x\ry")]
        rep = check_xml(node)
        assert [a.code for a in rep] == ["string.cr_normalized"]
        assert rep.warnings and not rep.errors

        text = write_xml(node)
        assert "\r" in text                    # CR is left as-is on write
        assert read_xml(text) == [("a", "x\ny")]   # but reads back as LF

    def test_label_with_trailing_newline_is_sanitized_and_reported(self):
        # A label like 'A\n' isn't a valid XML name, but the old _XML_NAME
        # regex used a bare '$' anchor, which in Python matches just before a
        # trailing '\n' as well as at the absolute end of string -- so
        # 'A\n' was treated as already-valid and wasn't flagged or
        # sanitized, even though ElementTree happily wrote a tag literally
        # containing the newline. check_xml's empty report then lied: the
        # label silently lost its trailing newline on round-trip -- see
        # issue #95. It should be sanitized and flagged like any other
        # illegal-XML-name label.
        node = [("A\n", False)]
        rep = check_xml(node)
        assert [a.code for a in rep] == ["key.sanitized"]
        assert rep.warnings and not rep.errors

        text = write_xml(node)
        assert "\n" not in text.split(">", 1)[0]   # no raw newline in the tag
        assert read_xml(text) == [("A_", False)]   # round-trips via sanitized name

    def test_embedded_newline_label_is_sanitized_and_reported(self):
        # Same bug class as above, but with the newline in the middle of the
        # label rather than at the very end.
        node = [("A\nB", False)]
        rep = check_xml(node)
        assert [a.code for a in rep] == ["key.sanitized"]

        text = write_xml(node)
        assert read_xml(text) == [("A_B", False)]


# ----------------------------------------------------------- TOML write errors
class TestTomlWriteErrors:
    def test_non_object_root_raises(self):
        with pytest.raises(WriteError, match="top-level table"):
            write_toml("bare leaf")
