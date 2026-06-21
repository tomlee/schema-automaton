"""Tests for the canonical (redesigned) Document and Schema models.

Covers the design in docs/design/model.md: edge-list Document, record/union/Ref
schema, field cardinality, conformance, the DSL, operations, and codecs.
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
    union,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)
from dataspec.errors import DocumentError, SchemaError, WriteError

yaml = pytest.importorskip("yaml")


# ----------------------------------------------------------- public API
class TestPublicApi:
    """The `import dataspec` surface: schema operations as methods, the `t`
    builder namespace, validation, codecs."""

    def test_methods_and_t_namespace(self):
        import dataspec as ds

        s = ds.parse_schema('record R { "n": integer, "s": string? }\nroot R')
        assert ds.__version__ == "0.1.1a3"
        # operations are Schema methods
        assert s.validate(ds.doc({"n": 1, "s": None})).ok
        assert s.equivalent(ds.parse_schema(ds.to_dsl(s)))
        wide = ds.parse_schema('record R { "n": integer | string, "s": string? }\nroot R')
        assert s.compatible_with(wide)
        assert s.normalize().equivalent(s)
        # the t namespace builds unions
        u = ds.union(ds.t.integer, "unknown")
        b = ds.schema(ds.ref("R"), R=ds.record(ds.field("v", u)))
        assert b.validate(ds.doc({"v": 7})).ok
        assert b.validate(ds.doc({"v": "unknown"})).ok
        assert not b.validate(ds.doc({"v": "other"})).ok

    def test_old_names_are_gone(self):
        import dataspec as ds
        for name in ("obj", "arr", "ObjectType", "ArrayType", "ScalarType", "mapping"):
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

    def test_enum_and_nullable(self):
        s = 'record R { "status": "open" | "closed" }\nroot R'
        assert valid(s, {"status": "open"}).ok
        assert not valid(s, {"status": "other"}).ok
        s2 = 'record R { "note": string? }\nroot R'
        assert valid(s2, {"note": None}).ok
        assert valid(s2, {"note": "hi"}).ok

    def test_kind_plus_literal_union(self):
        s = 'record R { "v": integer | "unknown" }\nroot R'
        assert valid(s, {"v": 7}).ok
        assert valid(s, {"v": "unknown"}).ok
        assert not valid(s, {"v": "other"}).ok

    def test_ref_and_recursion(self):
        s = ('record Node { "value": integer, "kids" [0,]: Node }\nroot Node')
        assert valid(s, {"value": 1, "kids": [{"value": 2, "kids": []}]}).ok
        assert not valid(s, {"value": 1, "kids": [{"value": "x", "kids": []}]}).ok

    def test_question_mark_on_ref_is_error(self):
        with pytest.raises(SchemaError):
            parse_schema('record A { "x": integer }\nrecord R { "a": A? }\nroot R')

    def test_named_union(self):
        s = ('union License { "auto", "manual", null }\n'
             'record Car { "license": License }\nroot Car')
        assert valid(s, {"license": "auto"}).ok
        assert valid(s, {"license": None}).ok
        assert not valid(s, {"license": "other"}).ok


# ----------------------------------------------------------- DSL round-trip
DSL_CASES = [
    'record R { "n": integer }\nroot R',
    'record R { "n": integer, "s": string? }\nroot R',
    'record R { "status": "a" | "b" | "c" }\nroot R',
    'record R { "v": integer | "x" }\nroot R',
    'record R { "xs" [0,]: integer }\nroot R',
    'record R { "xs" [1,5]: string }\nroot R',
    'record R { "first name": string }\nroot R',
    'record M { "name": string }\nrecord R { "m" [0,]: M }\nroot R',
    'union U { "x", "y", null }\nrecord R { "u": U }\nroot R',
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

    def test_widened_union_is_compatible(self):
        narrow = parse_schema('record R { "v": integer }\nroot R')
        wide = parse_schema('record R { "v": integer | string }\nroot R')
        assert compatible_with(narrow, wide)
        assert not compatible_with(wide, narrow)

    def test_array_bounds(self):
        a = parse_schema('record R { "xs" [2,3]: integer }\nroot R')
        b = parse_schema('record R { "xs" [1,5]: integer }\nroot R')
        assert compatible_with(a, b)
        assert not compatible_with(b, a)

    def test_enum_subset(self):
        a = parse_schema('record R { "s": "x" }\nroot R')
        b = parse_schema('record R { "s": "x" | "y" }\nroot R')
        assert compatible_with(a, b)
        assert not compatible_with(b, a)

    def test_temporal_enum_compatible_with_kind(self):
        narrow = schema(ref("R"), R=record(field("d", union(datetime.date(2024, 1, 1)))))
        from dataspec.canonical import DATE
        wide = schema(ref("R"), R=record(field("d", union(DATE))))
        assert compatible_with(narrow, wide)

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
