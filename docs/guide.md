# dataspec — user guide

dataspec gives you **one canonical data model** for JSON, YAML, TOML, and XML,
and a **schema language** to validate and compare shapes over it. The model is
defined formally in [the model spec](design/model.md); this guide is the
practical tour; the [API reference](api.md) lists every name with signatures.

- [The two ideas](#the-two-ideas)
- [Documents](#documents)
- [Schemas — the DSL](#schemas--the-dsl)
- [Schemas — the Python builder](#schemas--the-python-builder)
- [Validation](#validation)
- [Operations](#operations)
- [Reading & writing formats](#reading--writing-formats)
- [Inferring a schema](#inferring-a-schema)
- [A real-life example](#a-real-life-example)

## The two ideas

- A **Document** is a *tree*: a node is either a scalar value or an
  **ordered list of labeled edges**. "Many" is a label that repeats — an array
  of members is the label `member` appearing several times, *not* a field
  pointing to an array. This is what lets the same Document represent JSON,
  YAML, TOML, and XML (including XML's interleaved repeated elements).
- A **Schema** is built from two kinds of named definition: a **`record`**
  (a closed set of named fields, each with a cardinality), and a **`union`** (a
  value domain — kinds, literals, and/or null). Fields reference definitions by
  name (`Ref`), which is how reuse and recursion work.

```python
from dataspec import parse_schema, doc

s = parse_schema('''
    record User { "name": string, "age" [0,1]: integer }
    root User
''')
s.validate(doc({"name": "Ann"})).ok          # True
```

## Documents

`doc(value)` builds a Document from plain Python. A dict becomes an edge list; a
key whose value is a list expands into one edge per item (a repeated label).

```python
from dataspec import doc

d = doc({"name": "Ann", "tag": ["x", "y"]})
d.labels()                 # ['name', 'tag']
d.count("tag")             # 2  -- 'tag' is a repeated label (an array)
d.get_one("name").value    # 'Ann'
[t.value for t in d.get("tag")]   # ['x', 'y']
d.to_data()                # [('name', 'Ann'), ('tag', 'x'), ('tag', 'y')]
d.to_grouped()             # {'name': 'Ann', 'tag': ['x', 'y']}   (JSON-shaped)
```

Edit through the guarded API (a repeated `add` is how an array grows):

```python
d.add("tag", "z")          # append an edge
d.set("name", "Bob")       # replace the single 'name'
d.remove("tag")            # drop every 'tag' edge
d.child("name")            # a cursor to the single child
```

## Schemas — the DSL

A schema is `record` / `union` definitions plus a `root`.

```
record Address { "street": string, "city": string }

record User {
    "name":          string,        # required (default cardinality [1,1])
    "nickname" [0,1]: string,        # optional
    "emails" [1,]:    string,        # one or more (an array)
    "address":       Address,        # Ref to a named record
    "status":        "active" | "suspended",   # an inline enum
}
root User
```

Rules, all from [the model spec](design/model.md):

- **Field labels are always quoted** (they're data strings, and may contain
  spaces: `"home address"`). Unquoted identifiers are *schema names* — a kind
  keyword (`string`, `integer`, …) or a `Ref` to a definition.
- **Cardinality `[min,max]`** is the only multiplicity knob: `[1,1]` required
  (the default — omit the brackets), `[0,1]` optional, `[0,]` zero-or-more,
  `[1,]` one-or-more, `[2,5]` bounded. **There is no separate array type** — an
  array is a field with `max > 1`.
- A field's type is a `Ref` (an unquoted name) or an inline **union**:
  `integer | string`, `"a" | "b"` (enum), `string?` (adds null), `integer |
  "unknown"` (a kind plus a literal). `?` adds null to a *value* domain only —
  a record that may be absent is `[0,1]`, never `Ref?`.
- **Records are closed**: an unexpected label is an error.

Named unions, and round-tripping back to text:

```python
from dataspec import parse_schema, to_dsl

s = parse_schema('union License { "auto", "manual", null }\n'
                 'record Car { "license": License }\nroot Car')
to_dsl(s)                  # prints the schema back as DSL
```

## Schemas — the Python builder

The same schema in Python. Scalar kinds live under the `t` namespace.

```python
from dataspec import schema, record, union, field, ref, t

address = record(field("street", union(t.string)),
                 field("city",   union(t.string)))
user = record(
    field("name",    union(t.string)),
    field("emails",  union(t.string), min=1, max=None),   # [1,]
    field("address", ref("Address")),
    field("status",  union("active", "suspended")),       # enum
)
s = schema(ref("User"), User=user, Address=address)
```

`union(...)` takes kind atoms (`t.string`) and/or literal values, plus
`null=True`; `field(label, type, min=1, max=1)`; `record(*fields)`;
`schema(root_ref, **named_definitions)`.

## Validation

`schema.validate(doc)` returns a `ValidationResult` with `.ok` and `.errors`
(each an `Error(path, message)`); validation **ignores edge order**.

```python
r = parse_schema('record R { "items" [1,]: integer }\nroot R').validate(
        doc({"items": []}))
r.ok                       # False
print(r)
# invalid:
#   at $: field 'items' occurs 0 time(s), expected at least 1
```

## Operations

Comparison operations are **methods on `Schema`**:

```python
v1 = parse_schema('record R { "host": string }\nroot R')
v2 = parse_schema('record R { "host": string, "port" [0,1]: integer }\nroot R')

v1.compatible_with(v2)     # True  -- every v1 doc is valid under v2
v2.compatible_with(v1)     # False
v1.equivalent(v2)          # False
s.normalize()              # merge structurally identical named definitions
```

`a.compatible_with(b)` means *every document `a` accepts is also accepted by
`b`* — the backward-compatibility check for a schema change.

## Reading & writing formats

`read_*` parse a format into a Document node; `Doc.from_*` wrap it; `Doc.to_*`
write back. All four formats read into the *same* Document.

```python
from dataspec import Doc

Doc.from_json('{"name": "Ann", "tags": ["x", "y"]}').to_toml()
Doc.from_yaml("name: Ann\n").to_json()
```

XML is single-rooted — its document element is the one top-level edge — and
preserves interleaving on read; writing requires a single top-level edge.

## Inferring a schema

`infer(samples)` drafts a schema from example Documents:

```python
from dataspec import infer, doc

s = infer([doc({"id": 1, "tags": ["a"]}), doc({"id": 2, "tags": ["b", "c"]})])
print(s.to_dsl())
# record Root {
#     "id": integer,
#     "tags" [0,]: string,
# }
# root Root
```

## A real-life example

An order schema combining named records, an enum, a required array, an optional
field, and recursion-free reuse — built once, validated across formats.

```python
from dataspec import parse_schema, Doc

ORDER = '''
record Address  { "street": string, "city": string }
record LineItem { "sku": string, "qty": integer, "price": number }
record Order {
    "id":       string,
    "status":   "pending" | "shipped" | "cancelled",
    "total":    number,
    "address":  Address,
    "items" [1,]: LineItem,        # at least one line item
    "coupon" [0,1]: string,         # optional
}
root Order
'''
s = parse_schema(ORDER)

good = Doc.from_json('''
{"id":"A1","status":"shipped","total":29.97,
 "address":{"street":"1 Main St","city":"London"},
 "items":[{"sku":"W","qty":3,"price":9.99}]}
''')
s.validate(good).ok        # True

bad = Doc.from_json('''
{"id":"A2","status":"lost","total":10,
 "address":{"street":"x","city":"y"},"items":[]}
''')
print(s.validate(bad))
# invalid:
#   at $.status: 'lost' is not in union{'cancelled', 'pending', 'shipped'}
#   at $: field 'items' occurs 0 time(s), expected at least 1
```

For a fuller version — the same order validated against documents in **all four
formats**, plus a compatibility check — see [a real-life example](example.md).
[`examples/canonical_model.py`](../examples/canonical_model.py) is a runnable
end-to-end version; [the model spec](design/model.md) has the formal
definitions; and [Formats](formats/overview.md) covers each format's mapping
and caveats.
