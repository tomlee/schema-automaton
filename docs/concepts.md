# Concepts

dataspec has a small vocabulary — five ideas, covered below: **Document**,
**Schema**, the structure/domain split (**Object**), **Validation**, and
**Conversion**. Learn these and the rest of the API falls into place.

## Document

A **Document** is a tree of data: objects (keyed), arrays (ordered), and scalar
values (`string`, `integer`, `number`, `boolean`, `null`, and the temporal types
`date` / `time` / `datetime`). It is *format-neutral* — the same Document can be
read from or written to JSON, YAML, TOML, or XML.

You work with a Document through **`Doc`**, a guarded data structure (think of it
as a "DOM" for plain data). `Doc` is the only supported way to build and change a
Document, which is what keeps it well-formed:

```python
from dataspec import Doc, doc

d = Doc.from_json('{"name": "Ann", "address": {"city": "London"}}')   # import from a format
d = doc({"name": "Ann", "address": {"city": "London"}})               # import a Python value
d.child("address").set("city", "Dublin")                         # edit through the API
d.to_toml()                                                         # emit to any format
```

See [Documents](document.md) for the full API.

## Schema

A **Schema** describes the shape a Document should have: which fields exist,
whether they're required, what types they hold. A schema is built from **types**
that mirror the data — `ObjectType`, `ArrayType`, `ScalarType`, `AnyType`,
`RefType`. You can write a schema three ways, all producing the same object tree:

```python
from dataspec import parse_schema, obj, schema, infer, t, doc

parse_schema("root { name: string, address: { city: string } }")    # 1. the DSL (text)
schema(obj(name=t.string, address=obj(city=t.string)))               # 2. the Python builder
infer([doc({"name": "Ann", "address": {"city": "London"}})])             # 3. inferred from samples
```

See [Schemas](schema.md).

## Object (and the structure/domain split)

The word **object** appears in both worlds, and they are deliberately *different*
things:

- a **document object** is one concrete keyed value — a node in a `Doc`;
- an **`ObjectType`** is a *schema* description of a whole family of objects
  (which keys, required or optional, what value types).

This reflects a core principle: **a Document node carries structure, never a
type domain.** A leaf holds a value (`30`), not a declared type (`integer`).
Domains live entirely in the Schema and are applied with `validate`. So you never
annotate a Document with types while building it; you describe types separately in
a Schema and check the two against each other.

(If you know XML: this is the same separation as a **DOM tree** vs an **XSD**.)

## Validation

**Validation** checks a Document against a Schema and returns a
`ValidationResult` with the verdict and path-aware errors. It operates on a
Document — not on raw format text — so you import first, then validate:

```python
d = Doc.from_json(payload)
result = schema.validate(d)            # validation is Doc-only
if not result.ok:
    for err in result.errors:
        print(err.path, err.message)   # e.g. "$.address.city expected string, got integer"
```

## Conversion

**Conversion** is just *read one format, write another* over the shared
Document. It is **lenient by default**: when a target format can't hold a value
(TOML/XML have no `null`; JSON has no dates), dataspec adjusts the data to fit
and records what changed in a report, rather than failing. Ask for the report,
or opt into a strict lossless mode:

```python
d = doc({"name": "Ann", "address": {"city": "London"}, "born": None})
d.to_toml()                       # lenient: adjust + succeed (the null is omitted)
d.to_toml(strict=True)            # raise WriteError if anything is lossy
```

See [Formats](formats/overview.md) for what each format can represent and how
adjustments are reported.

---

Next: the [Architecture](architecture.md) shows how these pieces are layered, or
jump into the [Getting started](getting-started.md) guide.
