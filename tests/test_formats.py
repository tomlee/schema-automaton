"""Format codecs: round-trip, cross-format transcode, and profile limits."""
import datetime
import json

import pytest

from dataspec import (
    read_json, write_json, read_yaml, write_yaml,
    read_toml, write_toml, read_xml, write_xml,
    WriteError, ParseError,
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


# ---------------------------------------------------------------- TOML
class TestToml:
    def test_round_trip(self):
        assert tomllib.loads(write_toml(SAMPLE)) == SAMPLE

    def test_read(self):
        assert read_toml('a = 1\n[b]\nc = "x"\n') == {"a": 1, "b": {"c": "x"}}

    def test_datetime_native(self):
        d = {"created": datetime.datetime(2024, 1, 1, 12, 0)}
        assert tomllib.loads(write_toml(d)) == d

    def test_omits_null_field(self):
        # null Option C: a null object-field is omitted
        assert tomllib.loads(write_toml({"a": 1, "b": None})) == {"a": 1}

    def test_strict_rejects_null_field(self):
        with pytest.raises(WriteError):
            write_toml({"a": 1, "b": None}, strict=True)

    def test_rejects_null_in_array(self):
        with pytest.raises(WriteError):
            write_toml({"xs": [1, None, 2]})

    def test_rejects_top_level_non_object(self):
        with pytest.raises(WriteError):
            write_toml([1, 2, 3])


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

    def test_omits_null_field(self):
        assert "<b>" not in write_xml({"a": 1, "b": None}, root="r")

    def test_rejects_null_in_array(self):
        with pytest.raises(WriteError):
            write_xml({"xs": [1, None]}, root="r")

    def test_rejects_top_level_array(self):
        with pytest.raises(WriteError):
            write_xml([1, 2, 3])


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
        # null Option C across formats: a null field drops out of TOML
        out = write_toml(read_json('{"a": 1, "b": null}'))
        assert tomllib.loads(out) == {"a": 1}
