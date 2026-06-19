"""Validation of Documents against Schemas."""
import datetime
import pytest

from dataspec import parse_schema, SchemaError


def valid(dsl, data):
    return parse_schema(dsl).validate(data)


class TestScalars:
    def test_string(self):
        assert valid("root string", "hi").ok
        assert not valid("root string", 1).ok

    def test_integer_vs_number(self):
        assert valid("root integer", 5).ok
        assert not valid("root integer", 5.5).ok
        assert valid("root number", 5).ok        # integer is a number
        assert valid("root number", 5.5).ok

    def test_boolean_is_not_integer(self):
        assert valid("root boolean", True).ok
        assert not valid("root integer", True).ok  # bool is not int here
        assert not valid("root boolean", 1).ok

    def test_nullable(self):
        assert valid("root string?", None).ok
        assert valid("root string?", "x").ok
        assert not valid("root string", None).ok

    def test_enum(self):
        s = "root \"a\" | \"b\""
        assert valid(s, "a").ok
        assert not valid(s, "c").ok

    def test_scalar_union(self):
        s = "root integer | string"
        assert valid(s, 1).ok
        assert valid(s, "x").ok
        assert not valid(s, True).ok

    def test_temporal_objects(self):
        assert valid("root date", datetime.date(2024, 1, 1)).ok
        assert valid("root datetime", datetime.datetime(2024, 1, 1, 12, 0)).ok
        assert valid("root time", datetime.time(12, 0)).ok
        # a datetime is not a (plain) date
        assert not valid("root date", datetime.datetime(2024, 1, 1)).ok

    def test_temporal_iso_strings(self):
        # JSON has no date type, so dates arrive as ISO strings — accept those too
        assert valid("root date", "2024-01-01").ok
        assert valid("root datetime", "2024-01-01T12:00:00").ok
        assert not valid("root date", "not-a-date").ok


class TestObjects:
    def test_required_optional(self):
        s = "root { name: string, age?: integer }"
        assert valid(s, {"name": "A"}).ok
        assert valid(s, {"name": "A", "age": 3}).ok
        assert not valid(s, {"age": 3}).ok

    def test_closed_rejects_extra(self):
        assert not valid("root { a: integer }", {"a": 1, "b": 2}).ok

    def test_open_allows_extra(self):
        assert valid("root { a: integer, ... }", {"a": 1, "b": 2}).ok

    def test_nullable_object(self):
        s = "root { user: { name: string }? }"
        assert valid(s, {"user": {"name": "A"}}).ok
        assert valid(s, {"user": None}).ok
        assert not valid(s, {"user": {"name": 1}}).ok

    def test_wrong_type(self):
        assert not valid("root { a: integer }", [1, 2]).ok

    def test_paths_in_errors(self):
        r = valid("root { items: [{ id: integer }] }", {"items": [{"id": "x"}]})
        assert any(p == "$.items[0].id" for p, _ in r.errors)


class TestArrays:
    def test_zero_or_more(self):
        assert valid("root [integer]", []).ok
        assert valid("root [integer]", [1, 2, 3]).ok
        assert not valid("root [integer]", ["x"]).ok

    def test_non_empty(self):
        assert not valid("root [integer]+", []).ok
        assert valid("root [integer]+", [1]).ok

    def test_exact_and_range(self):
        assert valid("root [integer]{2}", [1, 2]).ok
        assert not valid("root [integer]{2}", [1]).ok
        assert valid("root [integer]{1,3}", [1, 2]).ok
        assert not valid("root [integer]{1,3}", [1, 2, 3, 4]).ok

    def test_min_only_max_only(self):
        assert valid("root [integer]{2,}", [1, 2, 3]).ok
        assert not valid("root [integer]{2,}", [1]).ok
        assert valid("root [integer]{,2}", [1]).ok
        assert not valid("root [integer]{,2}", [1, 2, 3]).ok

    def test_nullable_array(self):
        assert valid("root [integer]?", None).ok
        assert valid("root [integer]?", [1]).ok


class TestNamedAndRecursive:
    def test_named_reuse(self):
        s = """
            type Point = { x: number, y: number }
            root { a: Point, b: Point }
        """
        assert valid(s, {"a": {"x": 1, "y": 2}, "b": {"x": 3, "y": 4}}).ok

    def test_recursion(self):
        s = "type Tree = { value: integer, kids: [Tree] }\nroot Tree"
        assert valid(s, {"value": 1, "kids": [{"value": 2, "kids": []}]}).ok
        assert not valid(s, {"value": 1, "kids": [{"value": "x", "kids": []}]}).ok

    def test_forward_reference(self):
        assert valid("root { a: Later }\ntype Later = integer", {"a": 5}).ok


class TestDslErrors:
    def test_no_root(self):
        with pytest.raises(SchemaError):
            parse_schema("type T = integer")

    def test_structural_union_rejected(self):
        with pytest.raises(SchemaError):
            parse_schema("root { a: integer } | { b: integer }")

    def test_duplicate_type(self):
        with pytest.raises(SchemaError):
            parse_schema("type T = integer\ntype T = string\nroot T")

    def test_unknown_reference_on_validate(self):
        with pytest.raises(SchemaError):
            parse_schema("root { a: Missing }").validate({"a": 1})
