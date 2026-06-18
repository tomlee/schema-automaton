"""
Tests for the textual Schema DSL (parse_schema / schema_to_dsl) and the
conformance algorithm (conforms_to).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import random
import pytest

from src import (
    parse_schema, schema_to_dsl, SchemaSyntaxError,
    tree_from_python, equivalent_sa, conforms_to, to_json_schema,
    VDom,
)


# ===========================================================================
# Parsing: scalars, objects, arrays, unions, nullable, enums
# ===========================================================================

class TestParseScalars:
    def test_scalar_root(self):
        sa = parse_schema("root int")
        assert sa.accepts(tree_from_python(5))
        assert not sa.accepts(tree_from_python("x"))

    def test_number_accepts_int_and_float(self):
        sa = parse_schema("root number")
        assert sa.accepts(tree_from_python(3))
        assert sa.accepts(tree_from_python(3.5))

    def test_bool_and_string(self):
        assert parse_schema("root bool").accepts(tree_from_python(True))
        assert parse_schema("root string").accepts(tree_from_python("hi"))

    def test_scalar_union(self):
        sa = parse_schema("root int | string")
        assert sa.accepts(tree_from_python(1))
        assert sa.accepts(tree_from_python("a"))
        assert not sa.accepts(tree_from_python(True))

    def test_nullable_scalar(self):
        sa = parse_schema("root string?")
        assert sa.accepts(tree_from_python("a"))
        assert sa.accepts(tree_from_python(None))
        assert not sa.accepts(tree_from_python(1))

    def test_enum(self):
        sa = parse_schema('root "red" | "green" | "blue"')
        assert sa.accepts(tree_from_python("red"))
        assert not sa.accepts(tree_from_python("purple"))

    def test_nullable_enum(self):
        sa = parse_schema('root ("a" | "b")?')
        assert sa.accepts(tree_from_python("a"))
        assert sa.accepts(tree_from_python(None))


class TestParseObjects:
    def test_required_and_optional_fields(self):
        sa = parse_schema("root { name: string, age?: int }")
        assert sa.accepts(tree_from_python({"name": "A"}))
        assert sa.accepts(tree_from_python({"name": "A", "age": 3}))
        assert not sa.accepts(tree_from_python({"age": 3}))          # name required

    def test_nullable_required_field_vs_optional(self):
        # 'note: string?' is a REQUIRED field with a nullable value;
        # 'note?: string' is an OPTIONAL field.
        req_nullable = parse_schema("root { note: string? }")
        assert req_nullable.accepts(tree_from_python({"note": None}))
        assert not req_nullable.accepts(tree_from_python({}))        # must be present

        optional = parse_schema("root { note?: string }")
        assert optional.accepts(tree_from_python({}))                # may be absent

    def test_closed_vs_open(self):
        closed = parse_schema("root { a: int }")
        assert not closed.accepts(tree_from_python({"a": 1, "b": 2}))
        opened = parse_schema("root { a: int, ... }")
        assert opened.accepts(tree_from_python({"a": 1, "b": 2}))

    def test_empty_object(self):
        sa = parse_schema("root {}")
        assert sa.accepts(tree_from_python({}))
        assert not sa.accepts(tree_from_python({"a": 1}))

    def test_nullable_object(self):
        sa = parse_schema("root { user: { name: string }? }")
        assert sa.accepts(tree_from_python({"user": {"name": "A"}}))
        assert sa.accepts(tree_from_python({"user": None}))
        assert not sa.accepts(tree_from_python({"user": {"name": 1}}))


class TestParseArrays:
    def test_array_zero_or_more(self):
        sa = parse_schema("root [int]")
        assert sa.accepts(tree_from_python([]))
        assert sa.accepts(tree_from_python([1, 2, 3]))
        assert not sa.accepts(tree_from_python(["x"]))

    def test_array_non_empty(self):
        sa = parse_schema("root [int]+")
        assert not sa.accepts(tree_from_python([]))
        assert sa.accepts(tree_from_python([1]))

    def test_empty_array_only(self):
        sa = parse_schema("root []")
        assert sa.accepts(tree_from_python([]))
        assert not sa.accepts(tree_from_python([1]))

    def test_nullable_array(self):
        sa = parse_schema("root [int]?")
        assert sa.accepts(tree_from_python([1, 2]))
        assert sa.accepts(tree_from_python(None))


class TestNamedTypesAndRecursion:
    def test_named_type_reuse(self):
        sa = parse_schema("""
            type Point = { x: number, y: number }
            root { a: Point, b: Point }
        """)
        assert sa.accepts(tree_from_python({"a": {"x": 1, "y": 2}, "b": {"x": 3, "y": 4}}))

    def test_recursion(self):
        sa = parse_schema("type Tree = { value: int, kids: [Tree] }\nroot Tree")
        t = tree_from_python({"value": 1, "kids": [
            {"value": 2, "kids": []},
            {"value": 3, "kids": [{"value": 4, "kids": []}]},
        ]})
        assert sa.accepts(t)

    def test_forward_reference(self):
        sa = parse_schema("root { a: Later }\ntype Later = int")
        assert sa.accepts(tree_from_python({"a": 5}))

    def test_root_is_named_type(self):
        sa = parse_schema("type T = { n: int }\nroot T")
        assert sa.accepts(tree_from_python({"n": 1}))


class TestParseErrors:
    def test_no_root(self):
        with pytest.raises(SchemaSyntaxError):
            parse_schema("type T = int")

    def test_undefined_reference(self):
        with pytest.raises(SchemaSyntaxError):
            parse_schema("root { a: Missing }")

    def test_structural_union_rejected(self):
        with pytest.raises(SchemaSyntaxError):
            parse_schema("root { a: int } | { b: int }")

    def test_unterminated_string(self):
        with pytest.raises(SchemaSyntaxError):
            parse_schema('root "abc')

    def test_unexpected_token(self):
        with pytest.raises(SchemaSyntaxError):
            parse_schema("root :")

    def test_duplicate_type(self):
        with pytest.raises(SchemaSyntaxError):
            parse_schema("type T = int\ntype T = string\nroot T")


# ===========================================================================
# Round-trip: parse(serialize(sa)) is equivalent to sa
# ===========================================================================

class TestRoundTrip:
    CASES = [
        "root int",
        "root string?",
        "root int | string",
        'root "a" | "b" | "c"',
        "root { name: string, age?: int }",
        "root { a: int, ... }",
        "root [string]",
        "root [int]+",
        "root { user: { name: string }? }",
        "root { tags: [string], scores: [number]+ }",
        "type Point = { x: number, y: number }\nroot { a: Point, b: Point }",
        "type Tree = { value: int, kids: [Tree] }\nroot Tree",
        "root { id: string, status: \"open\" | \"closed\", note: string? }",
    ]

    @pytest.mark.parametrize("text", CASES)
    def test_round_trip_equivalent(self, text):
        sa = parse_schema(text)
        dsl = schema_to_dsl(sa)
        sa2 = parse_schema(dsl)
        assert equivalent_sa(sa, sa2), f"\noriginal:\n{text}\nserialized:\n{dsl}"

    def test_serialize_inferred_schema(self):
        from src import infer_schema
        sa = infer_schema([
            tree_from_python({"id": 1, "tags": ["a"], "meta": {"k": "v"}}),
            tree_from_python({"id": 2, "tags": [], "meta": None}),
        ])
        dsl = schema_to_dsl(sa)
        assert equivalent_sa(sa, parse_schema(dsl))


# ===========================================================================
# Conformance algorithm
# ===========================================================================

class TestConformance:
    def _schema(self):
        return parse_schema("""
            type Line = { sku: string, qty: int }
            root { id: string, lines: [Line]+ }
        """)

    def test_conforms_true(self):
        sa = self._schema()
        t = tree_from_python({"id": "A", "lines": [{"sku": "x", "qty": 1}]})
        r = conforms_to(sa, t)
        assert r.ok and bool(r) is True
        assert str(r) == "conforms"

    def test_binding_covers_all_nodes(self):
        sa = self._schema()
        t = tree_from_python({"id": "A", "lines": [{"sku": "x", "qty": 1}]})
        r = conforms_to(sa, t)
        assert set(r.binding) == {n.node_id for n in t.nodes()}

    def test_nonconformance_reports_paths(self):
        sa = self._schema()
        t = tree_from_python({"id": 7, "lines": [{"sku": "x", "qty": "two"}]})
        r = conforms_to(sa, t)
        assert not r.ok
        paths = {p for p, _ in r.errors}
        assert "$.id" in paths
        assert "$.lines[].qty" in paths

    def test_missing_required_field(self):
        sa = self._schema()
        r = conforms_to(sa, tree_from_python({"lines": [{"sku": "x", "qty": 1}]}))
        assert not r.ok
        assert any("missing required" in m for _, m in r.errors)

    def test_agrees_with_accepts_random(self):
        sa = parse_schema("""
            type Item = { name: string, value: int | string, opt?: bool }
            root { items: [Item], count: int, label: string? }
        """)
        rng = random.Random(0)
        for _ in range(200):
            doc = {
                "items": [{"name": "n", "value": rng.choice([1, "x"]),
                           **({"opt": True} if rng.random() < 0.5 else {})}
                          for _ in range(rng.randint(0, 3))],
                "count": rng.choice([1, "bad"]),
                **({"label": rng.choice(["L", None])} if rng.random() < 0.7 else {}),
            }
            t = tree_from_python(doc)
            assert conforms_to(sa, t).ok == sa.accepts(t)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
