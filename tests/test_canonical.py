"""Tests for the canonical (redesigned) Document and Schema models.

Covers the design in docs/design/model.md: edge-list Document, record/Ref
schema with exactly seven scalars, field cardinality, conformance, the DSL,
operations, and codecs.
"""
import datetime

import pytest

from dataspec.canonical import (
    Doc,
    Format,
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
    to_dsl,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)
from dataspec.errors import DocumentError, ParseError, SchemaError, WriteError

yaml = pytest.importorskip("yaml")


# ----------------------------------------------------------- public API
class TestPublicApi:
    """The `import dataspec` surface: schema operations as methods, the `t`
    builder namespace, validation, codecs."""

    def test_methods_and_t_namespace(self):
        import dataspec as ds

        s = ds.parse_schema('record R { "n": integer, "s": string? }\nroot R')
        assert ds.__version__ == "0.1.1a7"
        # operations are Schema methods
        assert s.validate(ds.doc({"n": 1, "s": None})).ok
        assert s.equivalent(ds.parse_schema(ds.to_dsl(s)))
        wide = ds.parse_schema('record R { "n": number, "s": string? }\nroot R')
        assert s.compatible_with(wide)
        assert s.normalize().equivalent(s)
        # the t namespace, used directly as a field's type -- no wrapping
        b = ds.schema(ds.ref("R"), R=ds.record(ds.field("v", ds.nullable(ds.t.integer))))
        assert b.validate(ds.doc({"v": 7})).ok
        assert b.validate(ds.doc({"v": None})).ok
        assert not b.validate(ds.doc({"v": "other"})).ok

    def test_old_names_are_gone(self):
        import dataspec as ds
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
        d.remove("tag")
        assert d.count("tag") == 0
        # nested editing through a cursor shares the underlying structure
        d2 = doc({"addr": {"city": "X"}})
        d2.child("addr").set("city", "Y")
        assert d2.to_grouped() == {"addr": {"city": "Y"}}


class TestInfer:
    def test_flat(self):
        from dataspec.canonical import infer
        s = infer([doc({"name": "Ann", "age": 30}), doc({"name": "Bob"})])
        assert s.validate(doc({"name": "Cy"})).ok           # age optional
        assert not s.validate(doc({"age": 1})).ok           # name required

    def test_array_and_nested(self):
        from dataspec.canonical import infer
        s = infer([doc({"id": 1, "tags": ["a", "b"], "addr": {"city": "X"}})])
        assert s.validate(doc({"id": 9, "tags": ["c"], "addr": {"city": "Y"}})).ok
        assert not s.validate(doc({"id": 9, "tags": [1], "addr": {"city": "Y"}})).ok

    def test_accepts_its_own_samples(self):
        from dataspec.canonical import infer
        samples = [doc({"v": 1}), doc({"v": 2.5})]          # int + float -> number
        s = infer(samples)
        for sm in samples:
            assert s.validate(sm).ok

    def test_conflicting_scalars_raise(self):
        from dataspec.canonical import infer
        with pytest.raises(SchemaError):
            infer([doc({"v": 1}), doc({"v": "x"})])

    def test_null_only_field_infers_nullable_string(self):
        from dataspec.canonical import infer
        s = infer([doc({"v": None}), doc({"v": None})])
        assert s.validate(doc({"v": None})).ok
        assert s.validate(doc({"v": "anything"})).ok

    def test_null_alongside_a_kind_is_orthogonal(self):
        from dataspec.canonical import infer
        s = infer([doc({"v": 1}), doc({"v": None})])
        assert s.validate(doc({"v": 7})).ok
        assert s.validate(doc({"v": None})).ok
        assert not s.validate(doc({"v": "x"})).ok


# ----------------------------------------------------------- DSL + validation
def valid(dsl, data):
    return parse_schema(dsl).validate(doc(data))


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
        # value-domain composition (enums/literals) is no longer parseable
        with pytest.raises(SchemaError):
            parse_schema('record R { "status": "open" | "closed" }\nroot R')

    def test_union_keyword_is_rejected(self):
        with pytest.raises(SchemaError):
            parse_schema('union License { "auto", "manual" }\nrecord R { "a": integer }\nroot R')


# ----------------------------------------------------- DSL parser robustness
class TestDslRobustness:
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


# ----------------------------------------------------------- DSL round-trip
DSL_CASES = [
    'record R { "n": integer }\nroot R',
    'record R { "n": integer, "s": string? }\nroot R',
    'record R { "status": string }\nroot R',
    'record R { "v": number }\nroot R',
    'record R { "xs" [0,]: integer }\nroot R',
    'record R { "xs" [1,5]: string }\nroot R',
    'record R { "first name": string }\nroot R',
    'record M { "name": string }\nrecord R { "m" [0,]: M }\nroot R',
    'record Node { "v": integer, "kids" [0,]: Node }\nroot Node',
]


@pytest.mark.parametrize("text", DSL_CASES)
def test_dsl_round_trip(text):
    s = parse_schema(text)
    s2 = parse_schema(to_dsl(s))
    assert equivalent(s, s2), f"\n{text}\n->\n{to_dsl(s)}"


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
        from dataspec.canonical import DATE, STRING
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

    def test_unknown_field_and_missing_schema_passthrough(self):
        # shape problems (unexpected field) are validate()'s job, not raised here
        s = parse_schema('record R { "a": integer }\nroot R')
        node = read_json('{"a": 1, "b": "extra"}', schema=s)
        assert ("b", "extra") in node
        assert read_json('{"a": 1}') == [("a", 1)]      # no schema -> unchanged

    def test_schema_directed_via_doc_from_json(self):
        from dataspec.canonical import Doc
        s = parse_schema('record R { "d": date }\nroot R')
        d = Doc.from_json('{"d": "2024-01-01"}', schema=s)
        assert d.get_one("d").value == datetime.date(2024, 1, 1)

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
        node2 = [("x", float("nan"))]
        rep2 = check_json(node2)
        assert [a.code for a in rep2] == ["float.special"]
        assert rep2.errors

    def test_yaml_time_is_stringified(self):
        node = doc({"t": datetime.time(9, 30)}).to_data()
        rep = check_yaml(node)
        assert [a.code for a in rep] == ["temporal.stringified"]
        assert "09:30:00" in write_yaml(node)

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
        from dataspec.errors import DataspecError
        with pytest.raises(DataspecError):
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

    def test_check_format_matches_named_method(self):
        d = doc({"a": 1, "b": None})
        assert [a.code for a in d.check_format("toml")] == [a.code for a in d.check_toml()]
