# Getting started

This page gets you from zero to reading, validating, and converting data.

## Install

dataspec needs **Python 3.11 or newer** (it relies on the standard-library
`tomllib`). The core library and JSON support have no dependencies. Install an
extra only for each format you use:

| Format | Needs | Install |
|--------|-------|---------|
| JSON   | nothing (stdlib) | — |
| YAML   | PyYAML | `pip install pyyaml` |
| TOML (read) | nothing (stdlib `tomllib`) | — |
| TOML (write) | tomli_w | `pip install tomli_w` |
| XML    | defusedxml (recommended) | `pip install defusedxml` |

If an extra is missing, the matching function raises a clear `ImportError`
telling you what to install — nothing else breaks.

The package isn't published to PyPI yet, so install it from a checkout:

```bash
git clone https://github.com/tomlee/dataspec.git
cd dataspec
python3 -m venv .venv && source .venv/bin/activate
pip install .                          # core + JSON
pip install pyyaml tomli_w defusedxml  # all format extras (optional)
```

## The two ideas you need

Everything in dataspec is built on two concepts (see [Concepts](concepts.md) for
the full picture).

**A Document is a tree of data, held by a `Doc`.** Objects, arrays, and scalars —
format-neutral. You import data into a `Doc` (from a format string or a Python
value) and then build, navigate, and edit it through a guarded API, so it stays
well-formed. The same `Doc` writes out to any format.

**A Schema describes the shape a Document should have.** Write it as text, build
it in Python, or infer it from examples, then call `schema.validate(doc)`.
Validation tells you whether the data fits and, if not, exactly where it went
wrong.

## Import a document

Use `Doc.from_*` to import from a format string, or `doc(...)` to import a Python
value:

```python
from dataspec import Doc, doc

Doc.from_json('{"name": "Ann", "age": 30}')
Doc.from_yaml("name: Ann\nage: 30\n")
Doc.from_toml('name = "Ann"\nage = 30\n')
Doc.from_xml("<r><name>Ann</name><age>30</age></r>")
# {'r': {'name': 'Ann', 'age': 30}} -- XML's document element name (here "r")
# is a real top-level key, since an XML document always has exactly one.

doc({"name": "Ann", "age": 30})              # from an in-memory structure
```

Reading from a file is just reading its text:

```python
from pathlib import Path
d = Doc.from_toml(Path("config.toml").read_text())
```

## Navigate and edit

You move one level at a time and edit through the API (full details in
[Documents](document.md)):

```python
d = Doc.from_json('{"name": "Ann", "address": {"city": "London"}, "tags": ["x"]}')

d.get("name")                       # "Ann"
d.child("address").get("city")      # "London"   (navigate, then read)
d.child("address").set("city", "NY")  # modify a scalar leaf
d.child("tags").append("y")         # grow an array
d.add("active", True)               # add a new field
```

## Validate it

Write a schema and check a `Doc` against it. Validation is **Doc-only** — import
your data into a `Doc` first:

```python
from dataspec import parse_schema, doc

schema = parse_schema("""
    root {
        name: string,
        age:  integer,
        tags: [string],
    }
""")

result = schema.validate(doc({"name": "Ann", "age": 30, "tags": ["x"]}))
result.ok            # True
bool(result)         # True  -- you can use the result directly in an `if`

bad = schema.validate(doc({"name": 1, "age": "old"}))
bad.ok               # False
for err in bad.errors:
    print(err.path, "-", err.message)
# $.name - expected string, got integer
# $.age - expected integer, got string
# $ - missing required field 'tags'
```

`print(result)` gives a readable summary, and `schema.accepts(d)` is a shortcut
for `schema.validate(d).ok`.

## Convert between formats

Import one format, emit another — the `Doc.to_*` methods return a string:

```python
d = Doc.from_json('{"name": "Ann", "tags": ["x", "y"]}')
d.to_yaml()      # 'name: Ann\ntags:\n- x\n- y\n'
d.to_toml()      # 'name = "Ann"\ntags = [\n    "x",\n    "y",\n]\n'
```

Not every value fits every format — TOML and XML have no `null`, for instance.
By default conversion is **lenient**: the writer adjusts the data to fit and
records what it changed, so you don't have to handle an error for the common
case. Ask for the report, or pass `strict=True` to be told instead:

```python
from dataspec import doc, WriteError

doc({"items": [1, None, 2]}).to_toml()        # 'items = [\n    1,\n    2,\n]\n'  (null dropped)

try:
    doc({"items": [1, None, 2]}).to_toml(strict=True)
except WriteError as e:
    print(e)         # error: $.items[1]: null array item dropped (shifts positions)
```

The exact rules for each format — and what round-trips cleanly — are in
[Formats](formats/overview.md).

## Learn a schema from examples

If you already have data, let `infer` draft a schema for you:

```python
from dataspec import infer, doc

schema = infer([
    doc({"id": 1, "email": "a@x.io"}),
    doc({"id": 2}),                  # no email -> it becomes optional
])
print(schema.to_dsl())
# root { id: integer, email?: string }
```

See [Inferring schemas](infer.md) for how inference handles unions, nullability,
and arrays.

## Where to go next

- [Concepts](concepts.md) and [Architecture](architecture.md) — the mental model
  and how the layers fit together.
- [Documents](document.md) — the full `Doc` API: build, navigate, edit, emit.
- [Schemas](schema.md) — the schema language *and* the Python builder.
- [A worked example](example.md) — one realistic schema, documents in every
  format, and the schema operations used together.
- [Formats](formats/overview.md) — per-format support and the comparison table.
- [Comparing schemas](operations.md) — backward-compatibility checks for
  versioned APIs and configs.
- [API reference](api.md) — every public name in one place.
