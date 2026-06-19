# dataspec

[![tests](https://img.shields.io/badge/tests-87%20passing-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](#install)

**One data model, many formats.** Read JSON, YAML, TOML, or XML into plain
Python data, validate it against a schema, and write it back out to any of them.

```python
from dataspec import read_json, write_toml, parse_schema, infer

# read one format, write another — they share one data model
data = read_json('{"name": "Ann", "age": 30, "tags": ["x", "y"]}')
print(write_toml(data))
# name = "Ann"
# age = 30
# tags = ["x", "y"]

# validate against a schema (written in a small, readable DSL)
schema = parse_schema("""
    root {
        name: string,
        age:  integer,
        tags: [string],
    }
""")
print(schema.validate(data))          # valid
print(schema.validate({"name": 1}))   # invalid:  at $.name: expected string, got integer ...

# or learn a schema from examples
print(infer([data]).to_dsl())         # root { name: string, age: integer, tags: [string] }
```

## The mental model

- A **Document** is just plain Python data — objects (`dict`), arrays (`list`),
  and scalars (`str`, `int`, `float`, `bool`, `None`, `date`/`time`/`datetime`).
- A **Schema** describes the shape a Document should have.
- You **read** a format into a Document, **validate** it, and **write** it back
  out to any format.

JSON, YAML, TOML, and a simple XML are interchangeable because they all map to
the same Document. When a Document can't be represented in a target format
(e.g. `null` in TOML), you get a **clear error instead of silent corruption**.

That's the whole thing — no node classes, no parser objects, no theory.

## What you can do

| | |
|---|---|
| `read_json` / `read_yaml` / `read_toml` / `read_xml` | format → Document |
| `write_json` / `write_yaml` / `write_toml` / `write_xml` | Document → format |
| `schema.validate(doc)` | check a Document; get path-aware errors |
| `infer(docs)` | learn a Schema from examples |
| `schema.compatible_with(other)` | version-compatibility check |
| `schema.equivalent(other)` · `schema.normalize()` · `schema.to_dsl()` | compare / canonicalise / print |

## Schema DSL

```
type Line = { sku: string, qty: integer, price: number }
root {
    id:     string,
    status: "open" | "shipped" | "cancelled",   # enum
    lines:  [Line]+,                              # one or more
    note?:  string,                               # optional field
    meta:   { tags: [string] }?,                  # nullable object
    when:   datetime,
}
```

See [docs/schema-dsl.md](docs/schema-dsl.md) for the full reference.

## Install

```bash
git clone https://github.com/tomlee/dataspec.git
cd dataspec
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate

# optional extras (only for the formats you use)
pip install pyyaml      # YAML
pip install tomli_w     # writing TOML  (reading uses stdlib tomllib on 3.11+)
pip install defusedxml  # safe XML parsing
```

Requires **Python 3.11+** (stdlib `tomllib`). The core library and JSON support
have no dependencies.

```python
from dataspec import read_json   # the package is `dataspec`
```

## Run the tests / examples

```bash
pip install pytest pyyaml tomli_w defusedxml
python -m pytest tests/        # 87 tests
python examples/quickstart.py  # a 60-second tour
```

## Documentation

Full docs in [`docs/`](docs/README.md): [Concepts](docs/concepts.md) ·
[Usage](docs/usage.md) · [Schema DSL](docs/schema-dsl.md) ·
[Formats](docs/formats.md).

## License & background

Apache-2.0 (see [LICENSE](LICENSE) / [NOTICE](NOTICE)). The schema model is
inspired by Lee & Cheung, *"XML Schema Computations"* (CIKM 2010), included under
[`docs/paper/`](docs/paper/) — but the library trades the paper's academic
vocabulary for a simple, practical API.
