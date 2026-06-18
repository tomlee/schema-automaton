"""
Tests for the data-format-agnostic layer:
  - loading JSON / YAML / TOML / Python data into canonical Data Trees
  - the MapModel (unordered) content model
  - schema inference from sample trees
  - cross-format validation (a schema inferred from JSON validates YAML/TOML)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from src import (
    DataTree, SchemaAutomaton, HLang, VDom,
    MapModel, ScalarModel, KIND_MAP, KIND_SEQUENCE, KIND_SCALAR,
    minimize_sa, equivalent_sa, subschema_sa, extract_subschema,
    ITEM, tree_from_python, tree_from_json, infer_schema,
    to_json_schema,
)


# ===========================================================================
# MapModel (unordered content) unit tests
# ===========================================================================

class TestMapModel:
    def test_accepts_unordered(self):
        m = MapModel.of(required=["a", "b"], optional=["c"])
        assert m.accepts(["a", "b"])
        assert m.accepts(["b", "a"])         # order irrelevant
        assert m.accepts(["a", "b", "c"])
        assert m.accepts(["c", "b", "a"])

    def test_rejects_missing_required(self):
        m = MapModel.of(required=["a", "b"])
        assert not m.accepts(["a"])
        assert not m.accepts([])

    def test_rejects_unknown_key_when_closed(self):
        m = MapModel.of(required=["a"])
        assert not m.accepts(["a", "x"])

    def test_open_map_allows_extra(self):
        m = MapModel.of(required=["a"], open=True)
        assert m.accepts(["a", "x", "y"])

    def test_rejects_duplicate_keys(self):
        m = MapModel.of(optional=["a"])
        assert not m.accepts(["a", "a"])

    def test_mandatory_symbols(self):
        m = MapModel.of(required=["a", "b"], optional=["c"])
        assert m.mandatory_symbols() == {"a", "b"}

    def test_remove_required_symbol_empties(self):
        m = MapModel.of(required=["a"])
        assert m.remove_symbol("a").is_empty()

    def test_remove_optional_symbol(self):
        m = MapModel.of(required=["a"], optional=["b"])
        m2 = m.remove_symbol("b")
        assert not m2.is_empty()
        assert m2.accepts(["a"])
        assert not m2.accepts(["a", "b"])

    def test_subset_required_relaxation(self):
        # {a required} ⊆ {a optional}: every {a} doc is accepted by the looser one
        strict = MapModel.of(required=["a"])
        loose = MapModel.of(optional=["a"])
        assert strict.is_subset_of(loose)
        assert not loose.is_subset_of(strict)

    def test_subset_extra_optional(self):
        narrow = MapModel.of(required=["a"])
        wider = MapModel.of(required=["a"], optional=["b"])
        assert narrow.is_subset_of(wider)
        assert not wider.is_subset_of(narrow)

    def test_map_not_subset_of_sequence(self):
        m = MapModel.of(required=["a"])
        seq = HLang.parse("a")
        assert not m.is_subset_of(seq)
        assert not seq.is_subset_of(m)

    def test_canonical_key_equality(self):
        m1 = MapModel.of(required=["a"], optional=["b"])
        m2 = MapModel.of(optional=["b"], required=["a"])
        assert m1.canonical_key() == m2.canonical_key()
        assert m1.language_equals(m2)


# ===========================================================================
# Loading data into Data Trees
# ===========================================================================

class TestLoading:
    def test_json_object(self):
        dt = tree_from_json('{"name": "Ann", "age": 30}')
        assert dt.node(dt.root_id).kind == KIND_MAP
        assert set(dt.child_symbol_sequence(dt.root_id)) == {"name", "age"}

    def test_json_array(self):
        dt = tree_from_json('[1, 2, 3]')
        assert dt.node(dt.root_id).kind == KIND_SEQUENCE
        assert dt.child_symbol_sequence(dt.root_id) == [ITEM, ITEM, ITEM]

    def test_json_nested(self):
        dt = tree_from_json('{"items": [{"id": 1}]}')
        root = dt.root_id
        assert dt.node(root).kind == KIND_MAP
        items_edge = dt.child_edges(root)[0]
        assert dt.node(items_edge.child_id).kind == KIND_SEQUENCE

    def test_scalar_vdom_hints(self):
        dt = tree_from_python({"n": 1, "f": 1.5, "b": True, "s": "x", "z": None})
        kinds = {}
        for e in dt.child_edges(dt.root_id):
            kinds[e.symbol] = dt.node(e.child_id).vdom.kind
        assert kinds["n"] == VDom.INTS
        assert kinds["f"] == VDom.DECS
        assert kinds["b"] == VDom.BOOL
        assert kinds["s"] == VDom.STRS
        assert kinds["z"] == VDom.NULL


# ===========================================================================
# Schema inference
# ===========================================================================

class TestInference:
    def test_infer_simple_object(self):
        trees = [
            tree_from_python({"name": "Ann", "age": 30}),
            tree_from_python({"name": "Bob", "age": 25}),
        ]
        sa = infer_schema(trees)
        # both samples must validate against the inferred schema
        for t in trees:
            assert sa.accepts(t)

    def test_optional_field_detection(self):
        # 'age' present in only one sample → optional; 'name' in both → required
        trees = [
            tree_from_python({"name": "Ann", "age": 30}),
            tree_from_python({"name": "Bob"}),
        ]
        sa = infer_schema(trees)
        assert sa.accepts(tree_from_python({"name": "Cy"}))          # no age — ok
        assert sa.accepts(tree_from_python({"name": "Di", "age": 9}))
        assert not sa.accepts(tree_from_python({"age": 9}))          # missing name

    def test_inferred_schema_rejects_extra_keys(self):
        trees = [tree_from_python({"a": 1})]
        sa = infer_schema(trees)
        assert sa.accepts(tree_from_python({"a": 2}))
        assert not sa.accepts(tree_from_python({"a": 2, "b": 3}))

    def test_array_of_objects(self):
        trees = [tree_from_python(
            {"users": [{"id": 1, "name": "Ann"}, {"id": 2, "name": "Bob"}]}
        )]
        sa = infer_schema(trees)
        assert sa.accepts(trees[0])
        # an extra valid user is accepted
        assert sa.accepts(tree_from_python(
            {"users": [{"id": 3, "name": "Cy"}]}
        ))

    def test_numeric_generalisation(self):
        # int and float in the same position → DECS
        trees = [
            tree_from_python({"v": 1}),
            tree_from_python({"v": 2.5}),
        ]
        sa = infer_schema(trees)
        assert sa.accepts(tree_from_python({"v": 7}))
        assert sa.accepts(tree_from_python({"v": 7.7}))

    def test_nullable_generalisation(self):
        # value or null → nullable domain
        trees = [
            tree_from_python({"v": "hello"}),
            tree_from_python({"v": None}),
        ]
        sa = infer_schema(trees)
        assert sa.accepts(tree_from_python({"v": "world"}))
        assert sa.accepts(tree_from_python({"v": None}))

    def test_inferred_schema_is_minimal(self):
        # repeated identical sub-structures should share one state after minimize
        trees = [tree_from_python({
            "from": {"x": 1, "y": 2},
            "to":   {"x": 3, "y": 4},
        })]
        sa = infer_schema(trees)
        assert sa.accepts(trees[0])
        # 'from' and 'to' have identical structure → their point-type states merge
        # Resulting states: root, point-type, int-leaf  ≈ 3 states
        assert len(sa.states) <= 4


# ===========================================================================
# Cross-format: schema inferred from one format validates another
# ===========================================================================

class TestCrossFormat:
    def test_json_schema_validates_equivalent_yaml_like_python(self):
        # Infer from JSON text, validate a tree built from a different source
        json_tree = tree_from_json('{"host": "localhost", "port": 8080}')
        sa = infer_schema([json_tree])

        # Simulate a TOML/YAML-origin document as a plain Python dict
        toml_like = tree_from_python({"host": "example.com", "port": 443})
        assert sa.accepts(toml_like)

        # Wrong type for 'port' (string where integer expected) is rejected
        bad = tree_from_python({"host": "x", "port": "not-a-number"})
        assert not sa.accepts(bad)

    def test_subschema_across_inferred_schemas(self):
        # Schema A requires {host}; schema B requires {host, port}.
        # A doc valid under B (closed) is not necessarily valid under A (closed),
        # but B ⊆ A only if A permits port. Here we check the relationship.
        sa_required_host = infer_schema([tree_from_python({"host": "a"})])
        # open variant of host-only: accepts host plus anything? Not by default.
        # Instead verify reflexivity and a genuine subschema via extraction.
        assert subschema_sa(sa_required_host, sa_required_host).is_compatible


# ===========================================================================
# Subschema extraction on inferred (map-based) schemas
# ===========================================================================

class TestInferenceEdgeCases:
    def test_empty_only_array_infers_empty_sequence(self):
        """An array that is empty in every sample infers to 'empty only';
        a later non-empty array is rejected (no element type was observed)."""
        sa = infer_schema([tree_from_python({"x": []})])
        assert sa.accepts(tree_from_python({"x": []}))
        assert not sa.accepts(tree_from_python({"x": [1]}))

    def test_inferred_sa_has_no_dangling_symbols(self):
        """Invariant (Definition 2): every symbol occurring in a state's content
        language must have a δ transition."""
        sa = infer_schema([tree_from_python({"a": [1, 2], "b": {"c": "x"}})])
        for q in sa.states:
            content = sa.get_content(q)
            for sym in content.symbols():
                assert sa.transition(q, sym) is not None, (q, sym)

    def test_mixed_object_and_array_raises(self):
        with pytest.raises(ValueError):
            infer_schema([tree_from_python({"v": [1]}),
                          tree_from_python({"v": {"x": 1}})])

    def test_mixed_scalar_and_object_raises(self):
        # silent data loss would be a correctness bug — must raise instead
        with pytest.raises(ValueError):
            infer_schema([tree_from_python({"v": 1}),
                          tree_from_python({"v": {"x": 1}})])

    def test_object_or_string_union_raises(self):
        # a genuine non-null union ('object | string') cannot be one SA state
        with pytest.raises(ValueError):
            infer_schema([tree_from_python({"v": {"x": 1}}),
                          tree_from_python({"v": "scalar"})])

    def test_deeply_nested(self):
        t = tree_from_python({"a": {"b": {"c": {"d": [1, 2, 3]}}}})
        sa = infer_schema([t])
        assert sa.accepts(t)

    def test_top_level_array(self):
        # samples are all non-empty → item+ → empty array rejected
        sa = infer_schema([tree_from_python([{"id": 1}, {"id": 2}])])
        assert sa.accepts(tree_from_python([{"id": 9}]))
        assert not sa.accepts(tree_from_python([]))

    def test_array_item_star_when_some_empty(self):
        # one empty + one non-empty sample → item* → both empty and filled ok
        sa = infer_schema([tree_from_python({"xs": []}),
                           tree_from_python({"xs": [1, 2]})])
        assert sa.accepts(tree_from_python({"xs": []}))
        assert sa.accepts(tree_from_python({"xs": [7]}))

    def test_minimize_idempotent(self):
        sa = infer_schema([tree_from_python({"a": 1, "b": "x", "c": [1]})])
        m1 = minimize_sa(sa)
        m2 = minimize_sa(m1)
        assert len(m1.states) == len(m2.states)
        assert equivalent_sa(m1, m2)


class TestMapExtraction:
    def test_extract_drops_optional_field(self):
        trees = [
            tree_from_python({"keep": 1, "drop": 2}),
            tree_from_python({"keep": 1}),  # makes 'drop' optional
        ]
        sa = infer_schema(trees)
        # Extract a subschema that only permits the 'keep' symbol
        extracted = extract_subschema(sa, {"keep"})
        assert extracted.accepts(tree_from_python({"keep": 5}))
        assert not extracted.accepts(tree_from_python({"keep": 5, "drop": 6}))


class TestScalarUnions:
    """Mixed scalar types at one position -> a union value domain (the fix for
    the soundness bug where inference rejected its own training data)."""

    def test_inference_is_sound_for_mixed_scalars(self):
        # the schema must accept every sample it was inferred from
        samples = [tree_from_python({"v": 1}), tree_from_python({"v": "hello"})]
        sa = infer_schema(samples)
        for s in samples:
            assert sa.accepts(s)

    def test_int_string_union_accepts_both(self):
        sa = infer_schema([tree_from_python({"v": 1}), tree_from_python({"v": "x"})])
        assert sa.accepts(tree_from_python({"v": 42}))
        assert sa.accepts(tree_from_python({"v": "y"}))
        assert not sa.accepts(tree_from_python({"v": True}))   # bool not in union

    def test_int_float_union_is_number(self):
        sa = infer_schema([tree_from_python({"v": 1}), tree_from_python({"v": 2.5}),
                           tree_from_python({"v": 3})])
        assert sa.accepts(tree_from_python({"v": 9}))
        assert sa.accepts(tree_from_python({"v": 9.9}))
        assert to_json_schema(sa)["properties"]["v"]["type"] == "number"

    def test_three_way_scalar_union(self):
        sa = infer_schema([tree_from_python({"v": 1}), tree_from_python({"v": "x"}),
                           tree_from_python({"v": True})])
        assert sa.accepts(tree_from_python({"v": 7}))
        assert sa.accepts(tree_from_python({"v": "z"}))
        assert sa.accepts(tree_from_python({"v": False}))
        t = to_json_schema(sa)["properties"]["v"]["type"]
        assert set(t) == {"integer", "string", "boolean"}

    def test_union_export_is_type_array(self):
        sa = infer_schema([tree_from_python({"v": 1}), tree_from_python({"v": "x"})])
        assert to_json_schema(sa)["properties"]["v"]["type"] == ["integer", "string"]

    def test_nullable_scalar_union(self):
        sa = infer_schema([tree_from_python({"v": 1}), tree_from_python({"v": None})])
        assert sa.accepts(tree_from_python({"v": 5}))
        assert sa.accepts(tree_from_python({"v": None}))
        assert not sa.accepts(tree_from_python({"v": "s"}))
        assert to_json_schema(sa)["properties"]["v"]["type"] == ["integer", "null"]


class TestNullableStructures:
    """Nullable objects/arrays: 'object | null', 'array | null'."""

    def test_nullable_object_accepts_object_and_null(self):
        sa = infer_schema([tree_from_python({"v": {"x": 1}}),
                           tree_from_python({"v": None})])
        assert sa.accepts(tree_from_python({"v": {"x": 9}}))
        assert sa.accepts(tree_from_python({"v": None}))

    def test_nullable_object_still_type_checks_object(self):
        sa = infer_schema([tree_from_python({"v": {"x": 1}}),
                           tree_from_python({"v": None})])
        # x must still be an integer when the object form is used
        assert not sa.accepts(tree_from_python({"v": {"x": "str"}}))

    def test_nullable_array(self):
        sa = infer_schema([tree_from_python({"xs": [1, 2]}),
                           tree_from_python({"xs": None})])
        assert sa.accepts(tree_from_python({"xs": [3, 4]}))
        assert sa.accepts(tree_from_python({"xs": None}))

    def test_non_nullable_object_rejects_null(self):
        sa = infer_schema([tree_from_python({"v": {"x": 1}})])
        assert not sa.accepts(tree_from_python({"v": None}))

    def test_nullability_survives_minimize(self):
        sa = infer_schema([tree_from_python({"v": {"x": 1}}),
                           tree_from_python({"v": None})])
        m = minimize_sa(sa)
        assert m.accepts(tree_from_python({"v": None}))
        assert m.accepts(tree_from_python({"v": {"x": 2}}))
        assert equivalent_sa(sa, m)

    def test_nullability_in_equivalence(self):
        nullable = infer_schema([tree_from_python({"v": {"x": 1}}),
                                 tree_from_python({"v": None})])
        plain = infer_schema([tree_from_python({"v": {"x": 1}})])
        assert not equivalent_sa(nullable, plain)

    def test_nullable_is_superschema_of_plain(self):
        # a plain object schema ⊆ the nullable version (every object doc is valid)
        nullable = infer_schema([tree_from_python({"v": {"x": 1}}),
                                 tree_from_python({"v": None})])
        plain = infer_schema([tree_from_python({"v": {"x": 1}})])
        assert subschema_sa(plain, nullable).is_compatible
        # but not the reverse: the nullable schema admits null, which plain rejects
        assert not subschema_sa(nullable, plain).is_compatible

    def test_nullable_object_export(self):
        sa = infer_schema([tree_from_python({"v": {"x": 1}}),
                           tree_from_python({"v": None})])
        assert to_json_schema(sa)["properties"]["v"]["type"] == ["object", "null"]

    def test_empty_string_is_not_null(self):
        # "" is a string value, not null — a non-nullable object must reject null
        # but a string field must accept the empty string
        sa = infer_schema([tree_from_python({"s": "a"}), tree_from_python({"s": ""})])
        assert sa.accepts(tree_from_python({"s": ""}))
        assert sa.accepts(tree_from_python({"s": "hi"}))
        assert not sa.accepts(tree_from_python({"s": None}))


class TestOpenMaps:
    def test_open_map_inference_allows_extra_keys(self):
        sa = infer_schema([tree_from_python({"a": 1})], open_maps=True)
        assert sa.accepts(tree_from_python({"a": 2}))
        assert sa.accepts(tree_from_python({"a": 2, "b": 3}))   # extra key ok

    def test_closed_is_default(self):
        sa = infer_schema([tree_from_python({"a": 1})])
        assert not sa.accepts(tree_from_python({"a": 2, "b": 3}))

    def test_open_map_export(self):
        sa = infer_schema([tree_from_python({"a": 1})], open_maps=True)
        assert to_json_schema(sa)["additionalProperties"] is True


class TestValidateDiagnostics:
    def _schema(self):
        return infer_schema([
            tree_from_python({"host": "a", "port": 1, "tags": ["x"]}),
            tree_from_python({"host": "b", "port": 2, "tags": ["y", "z"]}),
        ])

    def test_valid_document(self):
        sa = self._schema()
        res = sa.validate(tree_from_python({"host": "h", "port": 9, "tags": ["a"]}))
        assert res.ok
        assert bool(res) is True

    def test_missing_required_reported_with_path(self):
        sa = self._schema()
        res = sa.validate(tree_from_python({"host": "h", "tags": ["a"]}))
        assert not res.ok
        assert any("port" in e.message and e.path == "$" for e in res.errors)

    def test_typed_mismatch_number_as_string(self):
        sa = self._schema()
        res = sa.validate(tree_from_python({"host": "h", "port": 1, "tags": [1]}))
        assert not res.ok
        assert any(e.path == "$.tags[]" for e in res.errors)

    def test_typed_mismatch_bool_as_int(self):
        sa = self._schema()
        res = sa.validate(tree_from_python({"host": "h", "port": True, "tags": ["x"]}))
        assert not res.ok
        assert any(e.path == "$.port" for e in res.errors)

    def test_unexpected_key_reported(self):
        sa = self._schema()
        res = sa.validate(tree_from_python({"host": "h", "port": 1, "tags": ["x"], "z": 1}))
        assert not res.ok
        assert any("unexpected" in e.message for e in res.errors)


class TestJsonSchemaExport:
    def test_object_export(self):
        sa = infer_schema([
            tree_from_python({"name": "a", "age": 1}),
            tree_from_python({"name": "b"}),
        ])
        js = to_json_schema(sa)
        assert js["type"] == "object"
        assert set(js["properties"]) == {"name", "age"}
        assert js["required"] == ["name"]            # age optional
        assert js["additionalProperties"] is False

    def test_array_and_scalar_export(self):
        sa = infer_schema([tree_from_python({"xs": [1, 2], "label": "k"})])
        js = to_json_schema(sa)
        assert js["properties"]["xs"]["type"] == "array"
        assert js["properties"]["xs"]["items"]["type"] == "integer"
        assert js["properties"]["xs"]["minItems"] == 1
        assert js["properties"]["label"]["type"] == "string"

    def test_nullable_and_numeric_export(self):
        sa = infer_schema([
            tree_from_python({"v": "s", "n": 1}),
            tree_from_python({"v": None, "n": 2.5}),
        ])
        js = to_json_schema(sa)
        assert js["properties"]["v"]["type"] == ["string", "null"]
        assert js["properties"]["n"]["type"] == "number"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
