"""Format codecs: round-trip, cross-format transcode, and profile limits."""
import datetime
import json
import time

import pytest

from dataspec import (
    DocumentError,
    ParseError,
    UnsafeXMLWarning,
    WriteError,
    WriteReport,
    check_json,
    check_toml,
    check_xml,
    check_yaml,
    read_json,
    read_toml,
    read_xml,
    read_yaml,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)

yaml = pytest.importorskip("yaml")
import tomllib  # noqa: E402  (3.11+)

SAMPLE = {
    "name": "Ann",
    "age": 30,
    "active": True,
    "ratio": 0.5,
    "tags": ["x", "y"],
    "zip": "999",                # a numeric-looking string stays a string
    "address": {"city": "HK", "nums": [1, 2, 3]},
}


# ---------------------------------------------------------------- JSON
class TestJson:
    def test_round_trip(self):
        assert read_json(write_json(SAMPLE)) == SAMPLE

    def test_type_fidelity(self):
        d = read_json(write_json({"i": 1, "f": 1.0, "b": True, "s": "1"}))
        assert d["i"] == 1 and isinstance(d["i"], int)
        assert isinstance(d["f"], float)
        assert d["b"] is True
        assert d["s"] == "1" and isinstance(d["s"], str)

    def test_null(self):
        assert read_json(write_json({"x": None})) == {"x": None}

    def test_datetime_downgrades_to_iso(self):
        out = write_json({"t": datetime.date(2024, 1, 1)})
        assert json.loads(out)["t"] == "2024-01-01"

    def test_invalid_json_raises_parse_error_not_the_stdlib_exception(self):
        # used to leak json.JSONDecodeError directly, breaking the "catch
        # everything with except ParseError" contract docs/api.md promises.
        with pytest.raises(ParseError):
            read_json("not json{{{")


# ---------------------------------------------------------------- YAML
class TestYaml:
    def test_round_trip(self):
        assert yaml.safe_load(write_yaml(SAMPLE)) == SAMPLE

    def test_read(self):
        assert read_yaml("name: Ann\ntags: [a, b]\n") == {"name": "Ann", "tags": ["a", "b"]}

    def test_null(self):
        assert read_yaml("x: null\n") == {"x": None}

    def test_rejects_non_string_keys(self):
        with pytest.raises(ParseError):
            read_yaml("1: a\n2: b\n")

    def test_rejects_genuine_cycle(self):
        with pytest.raises(ParseError):
            read_yaml("a: &a\n  b: *a\n")

    def test_aliases_share_the_underlying_object(self):
        # PyYAML reuses the same constructed object for every reference to
        # an anchor -- not a bug, just how YAML represents shared structure.
        result = read_yaml("shared: &s [1, 2, 3]\nx: *s\ny: *s\n")
        assert result["x"] is result["y"]

    def test_aliased_structure_validates_in_linear_not_exponential_time(self):
        # Regression: _yaml_core_check used to re-walk a shared/aliased
        # subtree once per *reference* rather than once per unique object,
        # so a small, ordinary YAML payload using aliases took time
        # exponential in the nesting depth to validate -- even though
        # yaml.safe_load parses it instantly, since PyYAML shares the
        # constructed objects rather than duplicating them. 50 levels would
        # be a logical size of 10**50 if it were actually expanded; this
        # must stay fast because nothing is actually duplicated.
        levels = 50
        lines = ["a0: &a0 [" + ", ".join(["x"] * 30) + "]"]
        for i in range(1, levels):
            lines.append(f"a{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 10) + "]")
        text = "\n".join(lines)
        start = time.monotonic()
        read_yaml(text)
        elapsed = time.monotonic() - start
        # generous bound -- this finishes in ~0.05s when not exponential;
        # a regression back to exponential would take longer than the age
        # of the universe at 50 levels, so 5s has no realistic false-fail risk
        assert elapsed < 5, f"took {elapsed:.2f}s -- looks exponential again"


# ---------------------------------------------------------------- TOML
class TestToml:
    def test_round_trip(self):
        assert tomllib.loads(write_toml(SAMPLE)) == SAMPLE

    def test_read(self):
        assert read_toml('a = 1\n[b]\nc = "x"\n') == {"a": 1, "b": {"c": "x"}}

    def test_invalid_toml_raises_parse_error_not_the_stdlib_exception(self):
        # used to leak tomllib.TOMLDecodeError directly, breaking the
        # "catch everything with except ParseError" contract docs/api.md
        # promises.
        with pytest.raises(ParseError):
            read_toml("not = = toml")

    def test_datetime_native(self):
        d = {"created": datetime.datetime(2024, 1, 1, 12, 0)}
        assert tomllib.loads(write_toml(d)) == d

    def test_omits_null_field(self):
        # null Option C: a null object-field is omitted
        assert tomllib.loads(write_toml({"a": 1, "b": None})) == {"a": 1}

    def test_strict_rejects_null_field(self):
        with pytest.raises(WriteError):
            write_toml({"a": 1, "b": None}, strict=True)

    def test_drops_null_in_array_lenient(self):
        # lenient default: the null item is dropped, the rest survive
        assert tomllib.loads(write_toml({"xs": [1, None, 2]})) == {"xs": [1, 2]}

    def test_strict_rejects_null_in_array(self):
        with pytest.raises(WriteError):
            write_toml({"xs": [1, None, 2]}, strict=True)

    def test_wraps_top_level_non_object_lenient(self):
        # lenient default: a top-level array is wrapped under `wrap_key`
        assert tomllib.loads(write_toml([1, 2, 3])) == {"value": [1, 2, 3]}
        assert tomllib.loads(write_toml([1, 2], wrap_key="items")) == {"items": [1, 2]}

    def test_strict_rejects_top_level_non_object(self):
        with pytest.raises(WriteError):
            write_toml([1, 2, 3], strict=True)


# ---------------------------------------------------------------- XML
class TestXml:
    def test_round_trip_with_typing(self):
        data = {"name": "Ann", "age": 30, "active": True,
                "tags": ["x", "y"], "addr": {"city": "HK"}}
        assert read_xml(write_xml(data, root="rec")) == data

    def test_repeated_names_become_list(self):
        xml = "<r><item>1</item><item>2</item><other>x</other></r>"
        assert read_xml(xml) == {"item": [1, 2], "other": "x"}

    def test_rejects_attributes(self):
        with pytest.raises(ParseError):
            read_xml('<r><a x="1">v</a></r>')

    def test_rejects_mixed_content(self):
        with pytest.raises(ParseError):
            read_xml("<r>text<a>1</a></r>")

    def test_namespaces_stripped(self):
        assert read_xml('<r xmlns:n="urn:x"><n:a>1</n:a></r>') == {"a": 1}

    def test_root_element_name_is_arbitrary_on_read(self):
        # read_xml never inspects the root tag itself, only its children --
        # the name is a wrapper, not part of the data, on both write (the
        # `root=` parameter) and read.
        a = read_xml("<r><name>Ann</name></r>")
        b = read_xml("<totallydifferent><name>Ann</name></totallydifferent>")
        assert a == b == {"name": "Ann"}

    def test_write_then_read_with_different_root_names(self):
        data = {"name": "Ann"}
        out = write_xml(data, root="person")
        assert "<person>" in out
        assert read_xml(out) == data
        # the reader doesn't care what the writer called it, either
        assert read_xml(out.replace("person", "anything")) == data

    def test_warns_when_defusedxml_is_unavailable(self, monkeypatch):
        # read_xml() used to silently fall back to the standard library's
        # XML parser (vulnerable to XXE / entity expansion) with no
        # indication to the caller that defusedxml wasn't being used.
        import builtins

        real_import = builtins.__import__

        def blocking_import(name, *args, **kwargs):
            if name == "defusedxml" or name.startswith("defusedxml."):
                raise ImportError("simulated: not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocking_import)
        with pytest.warns(UnsafeXMLWarning):
            assert read_xml("<r><a>1</a></r>") == {"a": 1}

    def test_no_warning_when_defusedxml_is_available(self, recwarn):
        read_xml("<r><a>1</a></r>")
        assert not any(isinstance(w.message, UnsafeXMLWarning) for w in recwarn.list)

    def test_omits_null_field(self):
        assert "<b>" not in write_xml({"a": 1, "b": None}, root="r")

    def test_drops_null_in_array_lenient(self):
        assert read_xml(write_xml({"xs": [1, None, 2]}, root="r")) == {"xs": [1, 2]}

    def test_strict_rejects_null_in_array(self):
        with pytest.raises(WriteError):
            write_xml({"xs": [1, None]}, root="r", strict=True)

    def test_wraps_top_level_array_lenient(self):
        assert read_xml(write_xml([1, 2, 3], wrap_key="items")) == {"items": [1, 2, 3]}

    def test_strict_rejects_top_level_array(self):
        with pytest.raises(WriteError):
            write_xml([1, 2, 3], strict=True)


# ---------------------------------------------------- cross-format transcode
class TestTranscode:
    def test_json_to_toml(self):
        toml = write_toml(read_json('{"name": "Ann", "tags": ["a", "b"]}'))
        assert tomllib.loads(toml) == {"name": "Ann", "tags": ["a", "b"]}

    def test_toml_to_json(self):
        out = write_json(read_toml('title = "t"\n[o]\nk = 1\n'))
        assert json.loads(out) == {"title": "t", "o": {"k": 1}}

    def test_json_to_yaml_to_json(self):
        original = '{"a": 1, "b": [true, null, "s"], "c": {"d": 2.5}}'
        back = read_yaml(write_yaml(read_json(original)))
        assert back == json.loads(original)

    def test_json_with_null_to_toml_omits(self):
        # a null field drops out of TOML (lenient default)
        out = write_toml(read_json('{"a": 1, "b": null}'))
        assert tomllib.loads(out) == {"a": 1}


# ---------------------------------------------------- adjustment reports
class TestReports:
    def test_clean_write_has_empty_report(self):
        rep = WriteReport()
        write_toml({"a": 1}, report=rep)
        assert rep.adjustments == []
        assert bool(rep) is True

    def test_check_does_not_produce_output(self):
        rep = check_toml({"a": 1, "b": None})
        assert isinstance(rep, WriteReport)
        codes = [a.code for a in rep]
        assert codes == ["null.field.omitted"]
        assert rep.warnings and not rep.errors
        assert bool(rep) is True            # warnings only -> still "safe"

    def test_null_array_item_is_an_error(self):
        rep = check_toml({"xs": [1, None, 2]})
        assert [a.code for a in rep.errors] == ["null.item.dropped"]
        assert rep.errors[0].path == "$.xs[1]"
        assert bool(rep) is False           # has an error -> not safe

    def test_null_style_drop_demotes_to_warning(self):
        rep = check_toml({"xs": [1, None]}, null_style="drop")
        assert rep.errors == []
        assert [a.code for a in rep.warnings] == ["null.item.dropped"]

    def test_report_arg_and_strict_share_events(self):
        rep = WriteReport()
        with pytest.raises(WriteError) as ei:
            write_toml({"xs": [1, None]}, strict=True, report=rep)
        # the collector is filled even on the strict path...
        assert [a.code for a in rep] == ["null.item.dropped"]
        # ...and the exception carries the same report
        assert ei.value.report.errors

    def test_json_temporal_and_special_float(self):
        rep = check_json({"when": datetime.date(2024, 1, 1), "x": float("nan")})
        codes = {a.code for a in rep}
        assert codes == {"temporal.stringified", "float.special"}
        assert any(a.severity == "error" for a in rep)     # nan is an error

    def test_yaml_time_downgrades(self):
        rep = check_yaml({"t": datetime.time(9, 30)})
        assert [a.code for a in rep] == ["temporal.stringified"]

    def test_xml_sanitizes_bad_key(self):
        rep = WriteReport()
        out = write_xml({"a b": 1}, root="r", report=rep)
        assert [a.code for a in rep] == ["key.sanitized"]
        assert "<a_b>" in out

    def test_xml_nested_array_is_error(self):
        rep = check_xml({"grid": [[1, 2], [3, 4]]}, root="r")
        assert any(a.code == "array.nested.ambiguous" for a in rep.errors)

    def test_xml_string_that_looks_like_a_bool_is_reported(self):
        # write_xml({"a": "true"}) used to silently round-trip as a bool with
        # no adjustment at all -- this must be flagged so a caller can tell.
        rep = check_xml({"a": "true", "b": "123", "c": "1.5"}, root="r")
        assert [a.code for a in rep] == ["string.ambiguous"] * 3

    def test_xml_string_that_does_not_look_like_anything_else_is_silent(self):
        rep = check_xml({"a": "Ann", "b": ""}, root="r")
        assert rep.adjustments == []

    def test_xml_string_with_crlf_is_reported(self):
        # The XML spec requires \r\n/\r to be normalized to \n on read --
        # found by the edge-case sweep (tests/test_edge_cases.py), which
        # caught it via a string that doesn't look like a different type,
        # just one with different line endings.
        rep = check_xml({"a": "line1\r\nline2"}, root="r")
        assert [a.code for a in rep] == ["string.line_ending_normalized"]

    def test_xml_string_with_plain_newline_is_silent(self):
        rep = check_xml({"a": "line1\nline2"}, root="r")
        assert rep.adjustments == []

    def test_xml_strict_raises_on_crlf(self):
        with pytest.raises(WriteError):
            write_xml({"a": "line1\r\nline2"}, root="r", strict=True)

    def test_xml_illegal_char_is_stripped_and_reported(self):
        # write_xml used to embed control characters like NUL directly in
        # the output with no warning -- producing XML that isn't just lossy,
        # it doesn't parse at all (verified: the old output raised ParseError
        # from dataspec's own read_xml, not just from other implementations).
        rep = WriteReport()
        out = write_xml({"a": chr(0) + "hello"}, root="r", report=rep)
        assert [a.code for a in rep] == ["string.illegal_xml_char"]
        assert rep.errors  # data is destroyed, not just reshaped -- an error
        assert read_xml(out) == {"a": "hello"}

    def test_xml_strict_raises_on_illegal_char(self):
        with pytest.raises(WriteError):
            write_xml({"a": chr(0)}, root="r", strict=True)

    def test_xml_ordinary_control_chars_are_legal(self):
        # tab, LF, CR are explicitly legal XML Chars -- must not be stripped
        rep = check_xml({"a": "a\tb\nc"}, root="r")
        assert [a.code for a in rep if a.code == "string.illegal_xml_char"] == []

    def test_xml_strict_raises_on_ambiguous_string(self):
        with pytest.raises(WriteError):
            write_xml({"a": "true"}, root="r", strict=True)

    def test_xml_empty_array_value_keeps_the_key_and_is_reported(self):
        # write_xml({"xs": []}) used to silently drop the key entirely --
        # no <xs> element was written at all.
        rep = WriteReport()
        out = write_xml({"xs": []}, root="r", report=rep)
        assert "<xs" in out
        assert [a.code for a in rep] == ["container.empty.ambiguous"]

    def test_xml_empty_object_value_is_reported(self):
        rep = check_xml({"meta": {}}, root="r")
        assert [a.code for a in rep] == ["container.empty.ambiguous"]

    def test_xml_empty_top_level_object_is_reported(self):
        rep = check_xml({}, root="r")
        assert [a.code for a in rep] == ["container.empty.ambiguous"]

    def test_xml_non_empty_object_value_is_silent(self):
        rep = check_xml({"address": {"city": "London"}}, root="r")
        assert rep.adjustments == []

    def test_toml_integer_beyond_i64_is_a_warning(self):
        rep = check_toml({"x": 2 ** 63})
        assert [a.code for a in rep] == ["integer.out_of_range"]
        assert rep.warnings and not rep.errors

    def test_toml_integer_within_i64_is_silent(self):
        rep = check_toml({"x": 2 ** 62, "y": -(2 ** 63), "z": 2 ** 63 - 1})
        assert rep.adjustments == []

    def test_toml_strict_raises_on_integer_beyond_i64(self):
        with pytest.raises(WriteError):
            write_toml({"x": 2 ** 63}, strict=True)


# ------------------------------------------------- check_json / write_json reports
class TestJsonReports:
    def test_clean_doc_has_empty_report(self):
        rep = check_json({"a": 1, "b": "x", "c": True, "d": None})
        assert rep.adjustments == []
        assert bool(rep) is True

    def test_temporal_date_is_warning(self):
        rep = check_json({"d": datetime.date(2024, 1, 1)})
        assert len(rep.adjustments) == 1
        assert rep.adjustments[0].code == "temporal.stringified"
        assert rep.adjustments[0].severity == "warning"
        assert bool(rep) is True

    def test_temporal_time_is_warning(self):
        rep = check_json({"t": datetime.time(9, 30)})
        assert rep.adjustments[0].code == "temporal.stringified"

    def test_temporal_datetime_is_warning(self):
        rep = check_json({"dt": datetime.datetime(2024, 1, 1, 12, 0)})
        assert rep.adjustments[0].code == "temporal.stringified"

    def test_nan_is_error(self):
        rep = check_json({"x": float("nan")})
        assert rep.adjustments[0].code == "float.special"
        assert rep.adjustments[0].severity == "error"
        assert bool(rep) is False

    def test_infinity_is_error(self):
        rep = check_json({"x": float("inf")})
        assert rep.adjustments[0].code == "float.special"
        assert bool(rep) is False

    def test_nested_temporal_path(self):
        rep = check_json({"meta": {"created": datetime.date(2024, 1, 1)}})
        assert rep.adjustments[0].path == "$.meta.created"

    def test_temporal_in_array(self):
        rep = check_json({"dates": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]})
        codes = [a.code for a in rep]
        assert codes == ["temporal.stringified", "temporal.stringified"]
        assert rep.adjustments[0].path == "$.dates[0]"

    def test_report_arg_collects_from_write_json(self):
        rep = WriteReport()
        out = write_json({"d": datetime.date(2024, 6, 1)}, report=rep)
        assert json.loads(out)["d"] == "2024-06-01"
        assert rep.adjustments[0].code == "temporal.stringified"

    def test_strict_raises_on_temporal(self):
        with pytest.raises(WriteError):
            write_json({"d": datetime.date(2024, 1, 1)}, strict=True)

    def test_strict_raises_on_nan(self):
        with pytest.raises(WriteError):
            write_json({"x": float("nan")}, strict=True)

    def test_strict_clean_doc_does_not_raise(self):
        out = write_json({"a": 1}, strict=True)
        assert json.loads(out) == {"a": 1}

    def test_colliding_keys_after_coercion_is_error(self):
        # 1 and "1" are distinct dict keys but coerce to the same JSON key,
        # silently dropping one value on read-back -- this must be an error,
        # not a soft warning, since it corrupts the data.
        rep = check_json({1: "a", "1": "b"})
        collisions = [a for a in rep if a.code == "key.collision"]
        assert len(collisions) == 1
        assert collisions[0].severity == "error"
        assert bool(rep) is False

    def test_strict_raises_on_key_collision(self):
        with pytest.raises(WriteError):
            write_json({1: "a", "1": "b"}, strict=True)

    def test_distinct_string_keys_no_collision(self):
        rep = check_json({"a": 1, "b": 2})
        assert [a.code for a in rep if a.code == "key.collision"] == []


class TestDepthGuard:
    """Deeply/adversarially nested input must raise a clean error, not crash
    the process with an uncatchable RecursionError."""

    def _deep(self, n):
        d = {}
        cur = d
        for _ in range(n):
            cur["x"] = {}
            cur = cur["x"]
        return d

    def test_write_json_rejects_excessive_nesting(self):
        with pytest.raises(DocumentError, match="maximum depth"):
            write_json(self._deep(10_000))

    def test_write_yaml_rejects_excessive_nesting(self):
        with pytest.raises(DocumentError, match="maximum depth"):
            write_yaml(self._deep(10_000))

    def test_write_toml_rejects_excessive_nesting(self):
        with pytest.raises(DocumentError, match="maximum depth"):
            write_toml(self._deep(10_000))

    def test_write_xml_rejects_excessive_nesting(self):
        with pytest.raises(DocumentError, match="maximum depth"):
            write_xml(self._deep(10_000))


# ------------------------------------------------- check_yaml / write_yaml reports
class TestYamlReports:
    def test_clean_doc_has_empty_report(self):
        rep = check_yaml({"a": 1, "b": None, "c": True})
        assert rep.adjustments == []
        assert bool(rep) is True

    def test_date_and_datetime_are_native_no_adjustment(self):
        # YAML carries dates/datetimes natively — no adjustment needed
        rep = check_yaml({
            "d": datetime.date(2024, 1, 1),
            "dt": datetime.datetime(2024, 1, 1, 12, 0),
        })
        assert rep.adjustments == []

    def test_time_downgrades_to_string(self):
        rep = check_yaml({"t": datetime.time(9, 30)})
        assert len(rep.adjustments) == 1
        assert rep.adjustments[0].code == "temporal.stringified"
        assert rep.adjustments[0].severity == "warning"
        assert bool(rep) is True

    def test_time_path_is_correct(self):
        rep = check_yaml({"schedule": {"start": datetime.time(8, 0)}})
        assert rep.adjustments[0].path == "$.schedule.start"

    def test_time_in_array(self):
        rep = check_yaml({"times": [datetime.time(9, 0), datetime.time(10, 0)]})
        assert len(rep.adjustments) == 2
        assert rep.adjustments[0].path == "$.times[0]"

    def test_report_arg_collects_from_write_yaml(self):
        rep = WriteReport()
        out = write_yaml({"t": datetime.time(9, 30)}, report=rep)
        assert "09:30:00" in out
        assert rep.adjustments[0].code == "temporal.stringified"

    def test_strict_raises_on_time(self):
        with pytest.raises(WriteError):
            write_yaml({"t": datetime.time(9, 30)}, strict=True)

    def test_strict_clean_doc_does_not_raise(self):
        out = write_yaml({"a": 1, "b": None})
        assert "a: 1" in out


# ------------------------------------------ XML-specific report coverage
class TestXmlReports:
    def test_nested_array_single_report_per_item(self):
        # regression: the double-report bug produced two entries per item
        rep = check_xml({"grid": [[1, 2], [3, 4]]}, root="r")
        nested = [a for a in rep if a.code == "array.nested.ambiguous"]
        # two rows -> two entries, not four
        assert len(nested) == 2

    def test_top_level_scalar_wrapped(self):
        rep = WriteReport()
        out = write_xml(42, report=rep)
        assert [a.code for a in rep] == ["toplevel.wrapped"]
        assert rep.warnings  # wrapping is a warning, not an error
        assert "<value>42</value>" in out

    def test_top_level_null_is_error(self):
        rep = check_xml(None)
        assert any(a.code == "null.toplevel.empty" for a in rep.errors)
        assert bool(rep) is False

    def test_temporal_in_xml_is_warning(self):
        rep = check_xml({"d": datetime.date(2024, 1, 1)}, root="r")
        assert rep.adjustments[0].code == "temporal.stringified"
        assert rep.adjustments[0].severity == "warning"

    def test_null_style_drop_in_xml(self):
        rep = check_xml({"xs": [1, None, 2]}, root="r", null_style="drop")
        assert rep.errors == []
        assert [a.code for a in rep.warnings] == ["null.item.dropped"]

    def test_strict_raises_on_temporal(self):
        with pytest.raises(WriteError):
            write_xml({"d": datetime.date(2024, 1, 1)}, root="r", strict=True)

    def test_report_str_lists_adjustments(self):
        rep = check_toml({"a": None, "xs": [1, None]})
        text = str(rep)
        assert "null object field omitted" in text
        assert "null array item dropped" in text
        assert "warning" in text
        assert "error" in text

    def test_write_error_carries_report(self):
        with pytest.raises(WriteError) as ei:
            write_xml({"d": datetime.date(2024, 1, 1)}, root="r", strict=True)
        assert ei.value.report is not None
        assert ei.value.report.adjustments

    def test_colliding_keys_after_sanitization_is_error(self):
        # "my key" and "my_key" are distinct dict keys but sanitize to the
        # same XML element name, merging into one list on read-back -- this
        # must be an error, not a soft warning, since it corrupts the data.
        rep = check_xml({"my key": 1, "my_key": 2}, root="r")
        collisions = [a for a in rep if a.code == "key.collision"]
        assert len(collisions) == 1
        assert collisions[0].severity == "error"
        assert bool(rep) is False

    def test_strict_raises_on_key_collision(self):
        with pytest.raises(WriteError):
            write_xml({"my key": 1, "my_key": 2}, root="r", strict=True)

    def test_repeated_element_from_a_single_key_is_not_a_collision(self):
        # A list value legitimately repeats its own tag -- that's the normal
        # array representation, not a collision between two different keys.
        rep = check_xml({"tags": ["a", "b"]}, root="r")
        assert [a.code for a in rep if a.code == "key.collision"] == []


# --------------------------------------- key names: permitted here, not there
class TestCrossFormatKeyCompatibility:
    """Key names that are syntactically significant in one format's grammar
    but ordinary text in the others. JSON/YAML/TOML never need to touch any
    of these. Spelled out explicitly here, in addition to being part of the
    generic sweep in test_edge_cases.py, so the "permitted in some formats,
    not others" contrast is readable as a single test rather than only
    provable by inference from the sweep's invariants.
    """

    # Most of these aren't legal XML names, so they get key.sanitized.
    KEYS_XML_MUST_SANITIZE = {
        "space": "my key",
        "empty": "",
        "unicode": "clé",
        "numeric_looking": "123",
        "digit_prefix": "123abc",            # XML names can't start with a digit
        "toml_equals": "a=b",
        "toml_brackets": "a[b]",
        "yaml_colon": "a:b",
        "shared_hash": "a#b",
    }

    # "." and "-" are legal *inside* an XML name (just not as the first
    # character), so a key that's syntactically special in TOML (dotted-key
    # nesting) can still be a legal XML name as-is -- the two formats'
    # "special character" sets don't even line up with each other.
    KEYS_XML_ACCEPTS_UNCHANGED = {
        "toml_dot": "a.b",
    }

    @pytest.mark.parametrize("key", KEYS_XML_MUST_SANITIZE.values(),
                            ids=KEYS_XML_MUST_SANITIZE.keys())
    def test_json_yaml_toml_accept_as_is_xml_sanitizes(self, key):
        data = {key: 1}
        self._assert_clean_in_json_yaml_toml(data)

        # XML: not a legal element name, so it's sanitized into one --
        # reported, and the key changes shape, but the value is never lost.
        rep = check_xml(data, root="r")
        assert [a.code for a in rep] == ["key.sanitized"]
        back = read_xml(write_xml(data, root="r"))
        assert back != data                 # the key did not survive unchanged
        assert list(back.values()) == [1]   # but the value did

    @pytest.mark.parametrize("key", KEYS_XML_ACCEPTS_UNCHANGED.values(),
                            ids=KEYS_XML_ACCEPTS_UNCHANGED.keys())
    def test_special_only_in_toml_xml_accepts_unchanged(self, key):
        data = {key: 1}
        self._assert_clean_in_json_yaml_toml(data)

        # Unlike every other case above, this key IS already a legal XML
        # name (TOML and XML don't agree on what "special" means), so XML
        # needs no adjustment either -- it round-trips exactly everywhere.
        assert check_xml(data, root="r").adjustments == []
        assert read_xml(write_xml(data, root="r")) == data

    @staticmethod
    def _assert_clean_in_json_yaml_toml(data):
        # None of these characters need any special handling in JSON, YAML,
        # or TOML -- the key round-trips exactly, with no adjustment at all.
        assert read_json(write_json(data)) == data
        assert check_json(data).adjustments == []
        assert read_yaml(write_yaml(data)) == data
        assert check_yaml(data).adjustments == []
        assert read_toml(write_toml(data)) == data
        assert check_toml(data).adjustments == []
