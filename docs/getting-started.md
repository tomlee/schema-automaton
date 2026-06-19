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

Everything in dataspec is built on two concepts.

**A Document is plain Python data.** When you read a format, you get back
ordinary `dict`, `list`, `str`, `int`, `float`, `bool`, `None`, and
`datetime` values — nothing custom. You can index it, loop over it, and pass it
to any other library. Converting between formats is literally *read one, write
another*.

**A Schema describes the shape a Document should have.** You write it in a short
text language (or build one with `infer`), then call `schema.validate(doc)`.
Validation tells you whether the data fits and, if not, exactly where it went
wrong.

See [Schemas](schema.md) for the precise definitions of *scalar*, *array*,
*object*, and the rest.

## Read a document

Each format has a `read_*` function that takes a **string** and returns a
Document:

```python
from dataspec import read_json, read_yaml, read_toml, read_xml

read_json('{"name": "Ann", "age": 30}')      # {'name': 'Ann', 'age': 30}
read_yaml("name: Ann\nage: 30\n")            # {'name': 'Ann', 'age': 30}
read_toml('name = "Ann"\nage = 30\n')        # {'name': 'Ann', 'age': 30}
read_xml("<r><name>Ann</name><age>30</age></r>")  # {'name': 'Ann', 'age': 30}
```

Reading from a file is just reading its text:

```python
from pathlib import Path
doc = read_toml(Path("config.toml").read_text())
```

## Validate it

Write a schema and check the data against it:

```python
from dataspec import parse_schema

schema = parse_schema("""
    root {
        name: string,
        age:  integer,
        tags: [string],
    }
""")

result = schema.validate({"name": "Ann", "age": 30, "tags": ["x"]})
result.ok            # True
bool(result)         # True  -- you can use the result directly in an `if`

bad = schema.validate({"name": 1, "age": "old"})
bad.ok               # False
for err in bad.errors:
    print(err.path, "-", err.message)
# $.name - expected string, got integer
# $.age  - expected integer, got string
```

`print(result)` gives a readable summary, and `schema.accepts(doc)` is a
shortcut for `schema.validate(doc).ok`.

## Convert between formats

Read one format, write another. The `write_*` functions return a string:

```python
from dataspec import read_json, write_yaml, write_toml

doc = read_json('{"name": "Ann", "tags": ["x", "y"]}')
write_yaml(doc)      # 'name: Ann\ntags:\n- x\n- y\n'
write_toml(doc)      # 'name = "Ann"\ntags = ["x", "y"]\n'
```

Not every value fits every format. TOML and XML have no `null`, for instance.
When a value can't be represented, the writer raises a `WriteError` rather than
emit something wrong:

```python
from dataspec import write_toml, WriteError

try:
    write_toml({"items": [1, None, 2]})
except WriteError as e:
    print(e)         # null at $.items[1] cannot be represented (TOML/XML have no null)
```

The exact rules for each format — and what round-trips cleanly — are in
[Formats](formats/overview.md).

## Learn a schema from examples

If you already have data, let `infer` draft a schema for you:

```python
from dataspec import infer

schema = infer([
    {"id": 1, "email": "a@x.io"},
    {"id": 2},                       # no email -> it becomes optional
])
print(schema.to_dsl())
# root { id: integer, email?: string }
```

See [Inferring schemas](infer.md) for how inference handles unions, nullability,
and arrays.

## Where to go next

- [Schemas](schema.md) — the full schema language and every type.
- [Formats](formats/overview.md) — per-format support and the comparison table.
- [Comparing schemas](operations.md) — backward-compatibility checks for
  versioned APIs and configs.
- [API reference](api.md) — every public name in one place.
