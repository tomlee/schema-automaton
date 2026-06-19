# dataspec

[![tests](https://img.shields.io/badge/tests-108%20passing-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](#installation)
[![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)

**One data model for JSON, YAML, TOML, and XML.** Read any of them into plain
Python data, validate it against a schema, and write it back out to any of the
others — or get a clear error when a value can't be represented.

```python
from dataspec import read_json, write_toml, parse_schema

# Read one format, write another — they share one in-memory model.
data = read_json('{"name": "Ann", "age": 30, "tags": ["x", "y"]}')
print(write_toml(data))
# name = "Ann"
# age = 30
# tags = ["x", "y"]

# Describe the shape you expect, then check data against it.
schema = parse_schema("""
    root {
        name: string,
        age:  integer,
        tags: [string],
    }
""")
print(schema.validate(data))            # valid
print(schema.validate({"name": 1}))     # invalid:  at $.name: expected string, got integer ...
```

## Why dataspec

If your service reads config or payloads in more than one format, you usually
end up with a different library — and a different mental model — for each one.
`json`, `PyYAML`, `tomllib`, and `ElementTree` all hand you different shapes,
and none of them validate.

dataspec gives you **one** model and **one** set of operations:

- **Read** JSON / YAML / TOML / XML into ordinary Python `dict`s, `list`s, and
  scalars — no custom node objects to learn.
- **Validate** that data against a schema written in a small, readable language,
  and get back errors with exact paths like `$.items[0].id`.
- **Convert** between formats by reading one and writing another.
- **Infer** a schema from real examples, then refine it.
- **Compare** two schemas to check whether a change is backward-compatible.

The conversion guarantee is simple: **lossless, or a clear error.** When a
document can't be represented in a target format (for example, `null` in TOML),
you get a `WriteError` instead of silently corrupted output.

## Installation

Requires **Python 3.11+** (it uses the standard-library `tomllib`). The core
library and JSON support have no dependencies.

```bash
git clone https://github.com/tomlee/dataspec.git
cd dataspec
python3 -m venv .venv && source .venv/bin/activate
pip install .                    # core + JSON
```

Pull in extras only for the formats you actually use:

```bash
pip install pyyaml      # YAML
pip install tomli_w     # writing TOML  (reading uses the stdlib on 3.11+)
pip install defusedxml  # hardened XML parsing
```

> The package isn't on PyPI yet, so install it from a checkout as shown above.

## A 60-second tour

```python
from dataspec import read_json, write_yaml, parse_schema, infer

doc = read_json('{"id": 1, "email": "a@x.io", "roles": ["admin"]}')

print(write_yaml(doc))                  # transcode JSON -> YAML

schema = infer([doc])                   # learn a schema from an example
print(schema.to_dsl())                  # root { id: integer, email: string, roles: [string] }
print(schema.validate(doc))             # valid
```

Run the full tour with `python3 examples/quickstart.py`.

## Documentation

- **[Getting started](docs/getting-started.md)** — install, the core ideas, your
  first read / validate / convert.
- **[Schemas](docs/schema.md)** — the schema language, every type, with examples.
- **[Formats](docs/formats/overview.md)** — what each format supports, its
  limits, and a side-by-side comparison table.
  ([JSON](docs/formats/json.md) · [YAML](docs/formats/yaml.md) ·
  [TOML](docs/formats/toml.md) · [XML](docs/formats/xml.md))
- **[Inferring schemas](docs/infer.md)** — learn a schema from examples.
- **[Comparing schemas](docs/operations.md)** — equivalence and
  backward-compatibility checks.
- **[API reference](docs/api.md)** — every public function and class.
- **[FAQ](docs/faq.md)** — common questions and gotchas.

## Running the tests

```bash
pip install pytest pyyaml tomli_w defusedxml
python3 -m pytest          # 108 tests
```

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). The schema model was
inspired by Lee & Cheung, *"XML Schema Computations"* (CIKM 2010), but the
library deliberately trades the paper's vocabulary for a small, practical API.
