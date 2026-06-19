"""The Doc data structure: import guard, navigation, mutation, serialization."""
import datetime

import pytest

from dataspec import DetachedNode, Doc, DocumentError, doc


# ---------------------------------------------------------------- import guard
class TestImport:
    def test_empty_is_object(self):
        d = doc()
        assert d.kind == "object" and d.keys() == []

    def test_import_nested(self):
        d = doc({"a": 1, "b": {"c": [1, 2]}})
        assert d.kind == "object"
        assert d.child("b").child("c").at(1) == 2

    def test_scalar_root(self):
        assert doc(5).kind == "scalar" and doc(5).value == 5
        assert doc("hi").value == "hi"
        assert doc(None).value is None

    def test_array_root(self):
        d = doc([1, 2, 3])
        assert d.kind == "array" and d.len() == 3 and d.at(0) == 1

    def test_tuple_becomes_list(self):
        d = doc({"t": (1, 2, 3)})
        assert d.get("t") == [1, 2, 3]
        assert d.child("t").kind == "array"

    def test_temporal_scalars_allowed(self):
        d = doc({"d": datetime.date(2024, 1, 1),
                 "t": datetime.time(9, 0),
                 "dt": datetime.datetime(2024, 1, 1, 9, 0)})
        assert d.get("d") == datetime.date(2024, 1, 1)

    def test_reject_non_string_key(self):
        with pytest.raises(DocumentError):
            doc({1: "x"})

    def test_reject_unsupported_type(self):
        with pytest.raises(DocumentError):
            doc({"s": {1, 2, 3}})            # a set
        with pytest.raises(DocumentError):
            doc({"f": lambda: 1})            # a function

    def test_error_carries_path(self):
        with pytest.raises(DocumentError) as ei:
            doc({"a": {"b": [1, {2, 3}]}})
        assert "a.b[1]" in str(ei.value)

    def test_reject_cycle(self):
        a = {}
        a["self"] = a
        with pytest.raises(DocumentError):
            doc(a)

    def test_reject_excessive_nesting(self):
        # Deeply/adversarially nested input must raise a clean DocumentError,
        # not crash the process with an uncatchable RecursionError.
        deep = {}
        cur = deep
        for _ in range(10_000):
            cur["x"] = {}
            cur = cur["x"]
        with pytest.raises(DocumentError, match="maximum depth"):
            doc(deep)

    def test_copy_in_severs_reference(self):
        src = {"xs": [1, 2]}
        d = doc(src)
        src["xs"].append(99)                 # mutate the original
        assert d.get("xs") == [1, 2]          # the Doc is unaffected


# ---------------------------------------------------------------- navigation
class TestNavigation:
    def setup_method(self):
        self.d = doc({"name": "Ann", "address": {"city": "HK"}, "tags": ["x", "y"]})

    def test_get_scalar_and_container(self):
        assert self.d.get("name") == "Ann"
        assert self.d.get("address") == {"city": "HK"}    # snapshot

    def test_get_snapshot_is_detached(self):
        snap = self.d.get("address")
        snap["city"] = "NY"
        assert self.d.child("address").get("city") == "HK"

    def test_get_missing_raises(self):
        with pytest.raises(DocumentError):
            self.d.get("nope")

    def test_get_or_default(self):
        assert self.d.get_or("nope", 0) == 0

    def test_child_returns_live_cursor(self):
        self.d.child("address").set("city", "NY")
        assert self.d.child("address").get("city") == "NY"

    def test_child_on_scalar_errors(self):
        with pytest.raises(DocumentError):
            self.d.child("name")

    def test_has_keys_items(self):
        assert self.d.has("name") and not self.d.has("x")
        assert set(self.d.keys()) == {"name", "address", "tags"}
        assert dict(self.d.items())["name"] == "Ann"

    def test_path(self):
        assert self.d.child("address").path == "$.address"
        nested = doc({"items": [{"id": 1}]})
        assert nested.child("items").child_at(0).path == "$.items[0]"


# ---------------------------------------------------------------- object writes
class TestObjectWrites:
    def test_add_and_remove(self):
        d = doc()
        d.add("a", 1).add("b", [1, 2])
        assert d.keys() == ["a", "b"]
        d.remove("a")
        assert d.keys() == ["b"]

    def test_add_duplicate_errors(self):
        d = doc({"a": 1})
        with pytest.raises(DocumentError):
            d.add("a", 2)

    def test_add_object_returns_cursor(self):
        d = doc()
        child = d.add_object("o")
        child.add("x", 1)
        assert d.child("o").get("x") == 1

    def test_add_array_returns_cursor(self):
        d = doc()
        d.add_array("xs").append(1).append(2)
        assert d.get("xs") == [1, 2]

    def test_set_modifies_scalar(self):
        d = doc({"a": 1})
        d.set("a", 2)
        assert d.get("a") == 2

    def test_set_missing_key_errors(self):
        with pytest.raises(DocumentError):
            doc({"a": 1}).set("b", 2)

    def test_set_over_subtree_errors(self):
        with pytest.raises(DocumentError):
            doc({"a": {"x": 1}}).set("a", 5)

    def test_set_container_value_errors(self):
        with pytest.raises(DocumentError):
            doc({"a": 1}).set("a", {"x": 1})

    def test_add_legalizes_value(self):
        with pytest.raises(DocumentError):
            doc().add("a", {1, 2})           # set is not a Document value


# ---------------------------------------------------------------- array writes
class TestArrayWrites:
    def test_append_insert_remove(self):
        d = doc([1, 2, 3])
        d.append(4).insert(0, 0)
        assert d.to_data() == [0, 1, 2, 3, 4]
        d.remove(0)
        assert d.to_data() == [1, 2, 3, 4]

    def test_append_object_and_array(self):
        d = doc([])
        d.append_object().add("x", 1)
        d.append_array().append(9)
        assert d.to_data() == [{"x": 1}, [9]]

    def test_at_and_child_at(self):
        d = doc([{"x": 1}, "scalar"])
        assert d.child_at(0).get("x") == 1
        assert d.at(1) == "scalar"
        with pytest.raises(DocumentError):
            d.child_at(1)                    # scalar element

    def test_negative_and_out_of_range_index(self):
        d = doc([1, 2, 3])
        assert d.at(-1) == 3
        with pytest.raises(DocumentError):
            d.at(9)

    def test_set_array_element(self):
        d = doc([1, 2, 3])
        d.set(1, 20)
        assert d.to_data() == [1, 20, 3]


# ---------------------------------------------------------------- drop / cursors
class TestCursors:
    def test_drop_self(self):
        d = doc({"a": {"x": 1}, "b": 2})
        d.child("a").drop()
        assert d.keys() == ["b"]

    def test_drop_root_errors(self):
        with pytest.raises(DocumentError):
            doc({"a": 1}).drop()

    def test_parent_and_key(self):
        d = doc({"a": {"x": 1}})
        child = d.child("a")
        assert child.parent is d and child.key == "a"

    def test_detached_cursor_after_remove(self):
        d = doc({"a": {"x": 1}, "b": 2})
        a = d.child("a")
        d.remove("a")
        with pytest.raises(DetachedNode):
            a.get("x")
        with pytest.raises(DetachedNode):
            a.set("x", 9)

    def test_detached_after_parent_replaced(self):
        d = doc({"a": {"x": 1}})
        a = d.child("a")
        d.remove("a")
        d.add("a", {"x": 2})            # a different object at the same key
        with pytest.raises(DetachedNode):
            a.get("x")

    def test_detached_via_ancestor_removal(self):
        d = doc({"a": {"b": {"x": 1}}})
        deep = d.child("a").child("b")
        d.remove("a")                   # remove an ancestor
        with pytest.raises(DetachedNode):
            deep.get("x")

    def test_array_element_cursor_detaches_on_earlier_removal(self):
        d = doc({"xs": [{"id": 0}, {"id": 1}]})
        second = d.child("xs").child_at(1)
        d.child("xs").remove(0)         # shifts indices
        with pytest.raises(DetachedNode):
            second.get("id")


# ---------------------------------------------------------------- serialization
class TestSerialization:
    def test_to_data_is_deep_copy(self):
        d = doc({"xs": [1, 2]})
        data = d.to_data()
        data["xs"].append(3)
        assert d.get("xs") == [1, 2]

    def test_round_trip_json(self):
        d = Doc.from_json('{"a": 1, "b": ["x"]}')
        assert d.to_data() == {"a": 1, "b": ["x"]}

    def test_from_format_and_to_format(self):
        d = Doc.from_format("json", '{"a": 1}')
        assert d.to_format("json") == '{"a": 1}'

    def test_to_toml_yaml_xml(self):
        d = doc({"a": 1, "b": "x"})
        assert "a = 1" in d.to_toml()
        assert "a: 1" in d.to_yaml()
        assert "<a>1</a>" in d.to_xml(root="r")

    def test_to_format_passes_options(self):
        # null is dropped writing TOML; option threads through
        d = doc({"a": 1, "b": None})
        assert "b" not in d.to_toml()


# ---------------------------------------------------------------- dunders
class TestDunders:
    def test_eq_against_doc_and_plain(self):
        assert doc({"a": 1}) == doc({"a": 1})
        assert doc({"a": 1}) == {"a": 1}
        assert doc([1, 2]) != [1, 3]

    def test_len_and_iter_object(self):
        d = doc({"a": 1, "b": 2})
        assert len(d) == 2
        assert sorted(iter(d)) == ["a", "b"]

    def test_len_and_iter_array(self):
        d = doc([1, 2, 3])
        assert len(d) == 3
        assert list(iter(d)) == [1, 2, 3]

    def test_contains(self):
        assert "a" in doc({"a": 1})
        assert 2 in doc([1, 2, 3])

    def test_scalar_len_errors(self):
        with pytest.raises(DocumentError):
            len(doc(5))

    def test_repr(self):
        assert "object" in repr(doc({"a": 1}))
