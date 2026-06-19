"""infer, equivalent, compatible_with, normalize."""
import pytest

from dataspec import parse_schema, infer, read_json


# ------------------------------------------------------------- infer
class TestInfer:
    def test_accepts_all_samples(self):
        samples = [
            {"name": "Ann", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        s = infer(samples)
        for sample in samples:
            assert s.validate(sample).ok

    def test_optional_field(self):
        s = infer([{"name": "Ann", "age": 30}, {"name": "Bob"}])
        assert s.validate({"name": "Cy"}).ok          # age optional
        assert not s.validate({"age": 1}).ok          # name required

    def test_scalar_union_is_sound(self):
        # the classic soundness check: schema must accept its own samples
        samples = [{"v": 1}, {"v": "x"}]
        s = infer(samples)
        for sample in samples:
            assert s.validate(sample).ok

    def test_int_float_widens_to_number(self):
        s = infer([{"v": 1}, {"v": 2.5}])
        assert s.validate({"v": 7}).ok
        assert s.validate({"v": 7.7}).ok

    def test_nullable(self):
        s = infer([{"v": "a"}, {"v": None}])
        assert s.validate({"v": "b"}).ok
        assert s.validate({"v": None}).ok
        assert not s.validate({"v": 1}).ok

    def test_array_generalises_on_length(self):
        # inference is permissive on length: any count of the inferred item type
        s = infer([{"xs": [1, 2]}, {"xs": [1, 2, 3, 4]}])
        assert s.validate({"xs": [1, 2, 3]}).ok
        assert s.validate({"xs": [9]}).ok
        assert s.validate({"xs": []}).ok               # empty allowed too
        assert not s.validate({"xs": ["nope"]}).ok     # but item type is enforced

    def test_only_empty_arrays_infer_empty_only(self):
        s = infer([{"xs": []}])
        assert s.validate({"xs": []}).ok
        assert not s.validate({"xs": [1]}).ok          # no element type was seen

    def test_mixed_structure_raises(self):
        with pytest.raises(Exception):
            infer([{"v": 1}, {"v": {"x": 1}}])

    def test_round_trip_through_json(self):
        s = infer([read_json('{"id": 1, "tags": ["a"]}')])
        assert s.validate(read_json('{"id": 9, "tags": ["b", "c"]}')).ok


# ------------------------------------------------------ equivalent / compatible
class TestComparison:
    def test_equivalent_self(self):
        s = parse_schema("root { a: integer, b: string }")
        assert s.equivalent(s)

    def test_equivalent_reordered_fields(self):
        a = parse_schema("root { a: integer, b: string }")
        b = parse_schema("root { b: string, a: integer }")
        assert a.equivalent(b)

    def test_not_equivalent(self):
        a = parse_schema("root { a: integer }")
        b = parse_schema("root { a: string }")
        assert not a.equivalent(b)

    def test_compatible_optional_relaxation(self):
        # making a field optional is backward compatible
        strict = parse_schema("root { a: integer, b: integer }")
        loose = parse_schema("root { a: integer, b?: integer }")
        assert strict.compatible_with(loose)
        assert not loose.compatible_with(strict)

    def test_compatible_added_optional_field(self):
        v1 = parse_schema("root { a: integer }")
        v2 = parse_schema("root { a: integer, b?: integer }")
        assert v1.compatible_with(v2)        # every v1 doc is valid under v2

    def test_compatible_widened_scalar(self):
        narrow = parse_schema("root { v: integer }")
        wide = parse_schema("root { v: integer | string }")
        assert narrow.compatible_with(wide)
        assert not wide.compatible_with(narrow)

    def test_compatible_array_bounds(self):
        a = parse_schema("root [integer]{2,3}")
        b = parse_schema("root [integer]{1,5}")
        assert a.compatible_with(b)
        assert not b.compatible_with(a)


# ----------------------------------------------------------- normalize
class TestNormalize:
    def test_merges_identical_named_types(self):
        s = parse_schema("""
            type A = { x: integer }
            type B = { x: integer }
            root { a: A, b: B }
        """)
        n = s.normalize()
        assert len(n.types) == 1
        assert s.equivalent(n)

    def test_normalize_preserves_language(self):
        s = parse_schema("type P = { x: number, y: number }\nroot { p: P, q: P }")
        assert s.equivalent(s.normalize())
