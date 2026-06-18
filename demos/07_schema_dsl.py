"""Demo 7 — The textual Schema DSL and the conformance algorithm.

Authoring a schema as readable text, parsing it into a Schema Automaton,
checking document conformance (with the binding map), and round-tripping the
schema back to text.
"""
from _bootstrap import header
from src import (
    parse_schema, schema_to_dsl, conforms_to, to_json_schema,
    tree_from_python, equivalent_sa, infer_schema,
)
import json

SCHEMA = """
# A purchase order, written in the Schema DSL.
type Money = number
type Line  = { sku: string, qty: int, price: Money }

root {
    id:      string,
    status:  "open" | "shipped" | "cancelled",   # enumeration
    lines:   [Line]+,                              # one or more line items
    note?:   string,                               # optional field
    meta:    { tags: [string], owner: string }?,   # required, but may be null
}
"""


def main() -> None:
    header("Parse a schema from DSL text")
    sa = parse_schema(SCHEMA)
    print(f"Parsed into a Schema Automaton with {len(sa.states)} states.")

    header("Conformance check (Definition 3 — builds the binding map)")
    good = tree_from_python({
        "id": "PO-1", "status": "open",
        "lines": [{"sku": "A", "qty": 2, "price": 9.99}],
        "meta": None,
    })
    r = conforms_to(sa, good)
    print("conforms:", r.ok)
    print(f"binding map covers all {len(r.binding)} d-nodes "
          f"(each bound to the state that accepts it)")

    header("Non-conformance is reported with paths")
    bad = tree_from_python({
        "id": "PO-2", "status": "pending",          # not in the enum
        "lines": [],                                  # violates [Line]+
        "meta": {"tags": [1], "owner": "me"},        # tag must be a string
    })
    print(conforms_to(sa, bad))

    header("Required-nullable vs optional fields")
    print("'meta: {...}?'  -> required field, value may be null")
    print("  accepts meta=null :", sa.accepts(tree_from_python(
        {"id": "x", "status": "open", "lines": [{"sku": "s", "qty": 1, "price": 1}],
         "meta": None})))
    print("  rejects missing meta:", not sa.accepts(tree_from_python(
        {"id": "x", "status": "open", "lines": [{"sku": "s", "qty": 1, "price": 1}]})))
    print("'note?: string' -> optional field, may be omitted entirely")

    header("Schema -> JSON-Schema view")
    print(json.dumps(to_json_schema(sa)["properties"]["status"], indent=2))

    header("Round-trip: serialize the schema back to DSL")
    text = schema_to_dsl(sa)
    print(text)
    print("parse(serialize(sa)) is equivalent to sa:",
          equivalent_sa(sa, parse_schema(text)))

    header("Recursion is supported")
    tree = parse_schema("type Tree = { value: int, kids: [Tree] }\nroot Tree")
    doc = tree_from_python({"value": 1, "kids": [{"value": 2, "kids": []}]})
    print("recursive schema accepts a nested tree:", tree.accepts(doc))

    header("Inferred schemas can be printed as DSL")
    inferred = infer_schema([
        tree_from_python({"host": "a", "port": 80, "tls": True}),
        tree_from_python({"host": "b", "port": 443}),
    ])
    print(schema_to_dsl(inferred))


if __name__ == "__main__":
    main()
