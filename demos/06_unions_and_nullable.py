"""Demo 6 — Scalar unions and nullable objects/arrays in inference.

Real-world JSON is messy: a field may be an integer in one record and a string
in another, or an object that is sometimes null. This demo shows how inference
captures those cases soundly (the inferred schema always accepts its own
samples), and where it still refuses (a genuine object-or-scalar union).
"""
import json

from _bootstrap import header
from src import tree_from_python, infer_schema, to_json_schema


def main() -> None:
    header("Scalar union: a field that is integer OR string")
    samples = [
        tree_from_python({"id": 1, "ref": 100}),
        tree_from_python({"id": 2, "ref": "ABC-200"}),
    ]
    sa = infer_schema(samples)
    print("ref type:", to_json_schema(sa)["properties"]["ref"]["type"])
    print("accepts every training sample:", all(sa.accepts(s) for s in samples))
    print("accepts {ref: 7}     :", sa.accepts(tree_from_python({"id": 9, "ref": 7})))
    print("accepts {ref: 'X'}   :", sa.accepts(tree_from_python({"id": 9, "ref": "X"})))
    print("rejects {ref: true}  :", not sa.accepts(tree_from_python({"id": 9, "ref": True})))

    header("Numeric widening: integer + float  ->  number")
    sa = infer_schema([tree_from_python({"v": 1}), tree_from_python({"v": 2.5})])
    print("v type:", to_json_schema(sa)["properties"]["v"]["type"], "(both ints and floats accepted)")

    header("Nullable object: a field that is an object OR null")
    samples = [
        tree_from_python({"user": {"name": "Ann", "age": 30}}),
        tree_from_python({"user": None}),
    ]
    sa = infer_schema(samples)
    print(json.dumps(to_json_schema(sa)["properties"]["user"], indent=2))
    print("accepts object form:", sa.accepts(tree_from_python({"user": {"name": "B", "age": 1}})))
    print("accepts null form  :", sa.accepts(tree_from_python({"user": None})))
    print("still type-checks inside object (age must be int):",
          not sa.accepts(tree_from_python({"user": {"name": "B", "age": "x"}})))

    header("Nullable array")
    sa = infer_schema([tree_from_python({"tags": ["a", "b"]}),
                       tree_from_python({"tags": None})])
    print("tags type:", to_json_schema(sa)["properties"]["tags"]["type"])

    header("Open-map inference: tolerate undeclared keys")
    sa = infer_schema([tree_from_python({"a": 1})], open_maps=True)
    print("additionalProperties:", to_json_schema(sa)["additionalProperties"])
    print("accepts {a:1, surprise:99}:", sa.accepts(tree_from_python({"a": 1, "surprise": 99})))

    header("Still refused: a genuine object | scalar union")
    try:
        infer_schema([tree_from_python({"v": {"x": 1}}), tree_from_python({"v": "scalar"})])
        print("(unexpectedly inferred)")
    except ValueError as exc:
        print("ValueError:", str(exc).split(".")[0] + ".")
        print("(A single automaton state can't be both an object and a string;")
        print(" 'object | null' is supported, but 'object | string' is not.)")


if __name__ == "__main__":
    main()
