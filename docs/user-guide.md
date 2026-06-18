# User Guide

Task-oriented recipes. Every snippet runs against the library as imported from
the repository root (`from src import ...`). Runnable, narrated versions of these
live under [`demos/`](../demos).

- [1. Load data into a Data Tree](#1-load-data-into-a-data-tree)
- [2. Infer a schema from samples](#2-infer-a-schema-from-samples)
- [3. Validate documents](#3-validate-documents)
- [4. Inspect a schema as JSON Schema](#4-inspect-a-schema-as-json-schema)
- [5. Build a schema by hand](#5-build-a-schema-by-hand)
- [6. Compare schemas: equivalence & subschema](#6-compare-schemas-equivalence--subschema)
- [7. Check version backward-compatibility](#7-check-version-backward-compatibility)
- [8. Extract a trimmed subschema](#8-extract-a-trimmed-subschema)
- [9. Minimize a schema](#9-minimize-a-schema)
- [10. Cross-format validation](#10-cross-format-validation)

---

## 1. Load data into a Data Tree

```python
from src import tree_from_json, tree_from_yaml, tree_from_toml, tree_from_python

t1 = tree_from_json('{"name": "Ann", "tags": ["a", "b"]}')
t2 = tree_from_python({"name": "Ann", "tags": ["a", "b"]})   # already-parsed data
t3 = tree_from_yaml("name: Ann\ntags: [a, b]\n")             # needs PyYAML
t4 = tree_from_toml('name = "Ann"\ntags = ["a", "b"]\n')     # needs Python 3.11+
```

All four produce the same canonical Data Tree shape, so anything downstream
(inference, validation, comparison) is format-independent.

---

## 2. Infer a schema from samples

`infer_schema` derives the **canonical minimal** Schema Automaton from one or
more sample trees.

```python
from src import tree_from_python, infer_schema

schema = infer_schema([
    tree_from_python({"id": 1, "name": "Ann", "email": "ann@x.io"}),
    tree_from_python({"id": 2, "name": "Bob"}),   # no email
])
```

Inference rules:

* **Object fields** are *required* iff present in **every** sample, else
  *optional*. Here `id`/`name` are required, `email` is optional.
* **Array item type** is generalised over all observed elements; the array is
  `item+` if every sample array was non-empty, `item*` if any was empty. An
  array seen only empty infers to *empty-only* (no element type was observed).
* **Scalar domains** are generalised with `VDom.union`:
  * `int` + `float` → `number` (`DECS`);
  * `int` + `string` → a **union** domain admitting both
    (`"type": ["integer", "string"]`);
  * any type + `null` → a **nullable** scalar domain.
* **Nullable objects / arrays** — if a field is an object (or array) in some
  samples and `null` in others, the state is marked structurally nullable
  (`"type": ["object", "null"]`); the non-null form keeps its full structure.

Soundness guarantee: an inferred schema **always accepts every sample it was
inferred from**.

```python
# open objects: tolerate undeclared keys (additionalProperties: true)
schema = infer_schema(samples, open_maps=True)
```

> Inference produces **closed** objects by default. It raises `ValueError` only
> for a *genuine non-null* structural union (object in one sample, array or a
> non-null scalar in another) — see
> [Design & Limitations](design-and-limitations.md).

---

## 3. Validate documents

Two entry points: a fast boolean, and a diagnostic report.

```python
good = tree_from_python({"id": 9, "name": "Cy"})
schema.accepts(good)          # -> True

bad = tree_from_python({"id": "nine", "extra": 1})
result = schema.validate(bad)
result.ok                      # -> False
print(result)
# invalid:
#   at $: missing required ['name']
#   at $: unexpected ['extra']
#   at $.id: value 'nine' (found VDom(STRS)) not in VDom(INTS)

for err in result.errors:
    print(err.path, "→", err.message)
```

Validation is **type-aware** for loaded data: a JSON number is rejected where a
string is expected, with the offending JSON-path location (`$.tags[]`).

---

## 4. Inspect a schema as JSON Schema

```python
import json
from src import to_json_schema

print(json.dumps(to_json_schema(schema), indent=2))
# {
#   "type": "object",
#   "properties": {
#     "email": {"type": "string"},
#     "id":    {"type": "integer"},
#     "name":  {"type": "string"}
#   },
#   "required": ["id", "name"],
#   "additionalProperties": false
# }
```

This is a readable *view* for inspection/documentation, not a full JSON Schema
serializer. Recursive schemas emit `{"$ref": "#recursive"}` placeholders.

---

## 5. Build a schema by hand

Useful for XML-style ordered content or precise control.

```python
from src import SchemaAutomaton, ScalarModel, MapModel, VDom

sa = SchemaAutomaton("root")
# unordered object: street & city required, postalCode optional
sa.add_state("root", MapModel.of(required=["street", "city"],
                                 optional=["postalCode"]), VDom.null())
sa.add_state("str", ScalarModel(), VDom.strs())          # scalar leaf
for key in ("street", "city", "postalCode"):
    sa.add_transition("root", key, "str")

sa.accepts(tree_from_python({"street": "1 Main", "city": "Toronto"}))  # True
```

> **Scalar leaves: use `ScalarModel()`.** Data loaded with `tree_from_*` tags
> scalar nodes with `kind=SCALAR`, so a scalar-typed state must use
> `ScalarModel()` (kind `SCALAR`). The XML idiom `HLang.epsilon_lang()` has kind
> `SEQUENCE` (an *empty element*) — correct for hand-built XML trees whose nodes
> have no `kind`, but it will fail the structural-kind check against
> `kind=SCALAR` loaded data. See [Data Model §2](data-model.md#2-schema-automaton).

For ordered (XML-style) content use `HLang.parse`:

```python
from src import HLang
# a <Line> element must contain exactly <Desc> then <Price>
sa.add_state("line", HLang.parse("Desc Price"), VDom.null())
```

---

## 6. Compare schemas: equivalence & subschema

```python
from src import equivalent_sa, subschema_sa

equivalent_sa(schema_a, schema_b)        # -> bool   (L(A) == L(B))

report = subschema_sa(schema_a, schema_b)  # is L(A) ⊆ L(B) ?
report.is_compatible                      # -> bool
print(report)                             # human-readable incompatibilities
report.content_issues                     # [(state_a, state_b), ...]
report.vdom_issues
report.transition_issues
```

`subschema_sa(A, B)` answers *"is every instance of A also an instance of B?"* —
i.e. *"is B compatible with A?"*.

---

## 7. Check version backward-compatibility

A new schema version is backward compatible iff every old document still
validates — i.e. **old ⊆ new**.

```python
from src import subschema_sa

report = subschema_sa(old_schema, new_schema)
if report.is_compatible:
    print("Backward compatible: all v-old documents are valid under v-new.")
else:
    print("Breaking change!")
    print(report)
```

See [demos/04_schema_versioning.py](../demos/04_schema_versioning.py): adding an
*optional* field stays compatible; making a field *required* breaks it, and the
report names the offending state.

---

## 8. Extract a trimmed subschema

Given a large schema and the set of symbols an application actually uses, produce
a smaller schema accepting only instances confined to those symbols.

```python
from src import extract_subschema, ITEM

# keep only these object keys; include ITEM so array elements survive
trimmed = extract_subschema(full_schema, {"service", "port", "features", ITEM})
```

Notes:

* Dropping an **optional** key simply removes it.
* Dropping a key that is **mandatory at a node** removes that node, propagating
  upward; if the initial state mandatorily needs a dropped key, no valid
  subschema exists and `extract_subschema` raises `ValueError`.
* The result is automatically made useful and minimized, and is guaranteed to be
  a subschema of the input (`subschema_sa(trimmed, full).is_compatible == True`).

---

## 9. Minimize a schema

```python
from src import minimize_sa

minimal = minimize_sa(schema)   # fewest states; unique canonical form
len(minimal.states)
```

Minimization removes useless states (inaccessible or on cycles of mandatory
transitions) and merges equivalent states. The minimal SA is unique up to
isomorphism (paper Theorem 4), which is what makes `equivalent_sa` exact.

---

## 10. Cross-format validation

Because all formats share one canonical model, a schema inferred from one format
validates equivalent data from another:

```python
from src import tree_from_json, tree_from_yaml, tree_from_toml, infer_schema

schema = infer_schema([tree_from_json(s) for s in json_samples])

schema.validate(tree_from_yaml(yaml_doc)).ok    # True for conforming YAML
schema.validate(tree_from_toml(toml_doc)).ok    # True for conforming TOML
```

See [demos/03_cross_format.py](../demos/03_cross_format.py).
