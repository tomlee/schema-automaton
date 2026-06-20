# dataspec

[![tests](https://github.com/tomlee/dataspec/actions/workflows/test.yml/badge.svg)](https://github.com/tomlee/dataspec/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](#installation)
[![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)
[![status](https://img.shields.io/badge/status-alpha-orange)](#status)

**One data model for JSON, YAML, TOML, and XML.** Import any of them into a
single in-memory structure, build and edit it through a guarded API, validate it
against a schema, and write it back out to any of the others.

```python
from dataspec import Doc, obj, arr, schema, t

# Import one format; the same Document writes out to any other.
d = Doc.from_json('{"name": "Ann", "age": 30, "tags": ["x", "y"]}')
print(d.to_toml())
# name = "Ann"
# age = 30
# tags = ["x", "y"]

# Navigate and edit through the API — never malformed.
d.child("tags").append("z")
d.add("active", True)

# Describe the shape you expect, then check the Document against it.
s = schema(obj(name=t.string, age=t.integer, tags=arr(t.string), active=t.string))
print(s.validate(d))               # invalid:  at $.active: expected string, got boolean
```

## Why dataspec

If your service reads config or payloads in more than one format, you usually
end up with a different library — and a different mental model — for each one.
`json`, `PyYAML`, `tomllib`, and `ElementTree` all hand you different shapes,
and none of them validate.

dataspec gives you **one** model and **one** set of operations:

- A **`Doc`** data structure — a format-neutral "data DOM" you build, navigate,
  and edit through a guarded API, so it's always well-formed.
- **Read / write** JSON, YAML, TOML, XML over that one structure (or use the
  plain-Python `read_*` / `write_*` functions directly).
- **Validate** a Document against a schema — written as text, built in Python, or
  inferred from examples — with errors at exact paths like `$.items[0].id`.
- **Convert** between formats by importing one and emitting another.
- **Compare** two schemas to check whether a change is backward-compatible.
- **Extend** with new formats: register a `Format` plugin and it's usable everywhere.

Conversion is **lenient by default**: when a target format can't hold a value
(for example, `null` in TOML), dataspec adjusts the data to fit and *records*
what it changed — it doesn't make you handle an error for the common case. Ask
for the report when you care, or opt into a strict, lossless mode:

```python
from dataspec import doc

doc({"a": 1, "b": None}).to_toml()             # 'a = 1\n'  — null field dropped
doc({"xs": [1, None, 2]}).to_toml(strict=True) # raise WriteError if anything is lossy
```

`check_*` simulates a write and returns a report without producing output;
`strict=True` guarantees a lossless round-trip. See
[Formats](docs/formats/overview.md) for the full model.

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
from dataspec import Doc, doc, infer

d = Doc.from_json('{"id": 1, "email": "a@x.io", "roles": ["admin"]}')

print(d.to_yaml())                      # transcode JSON -> YAML
d.child("roles").append("ops")          # edit through the API

s = infer([d])                          # learn a schema from an example
print(s.to_dsl())                       # root { id: integer, email: string, roles: [string] }
print(s.validate(d))                    # valid
```

Run the full tour with `python3 examples/quickstart.py`.

## Documentation

- **[Concepts](docs/concepts.md)** — the five ideas: Document, Schema, Object,
  validation, conversion.
- **[Architecture](docs/architecture.md)** — the layers, the OO structure, the
  module map.
- **[Getting started](docs/getting-started.md)** — install and your first
  import / edit / validate / convert.
- **[Documents](docs/document.md)** — the `Doc` API: build, navigate, edit, emit.
- **[Schemas](docs/schema.md)** — the schema language *and* the Python builder.
- **[Formats](docs/formats/overview.md)** — what each format supports and the
  comparison table.
  ([JSON](docs/formats/json.md) · [YAML](docs/formats/yaml.md) ·
  [TOML](docs/formats/toml.md) · [XML](docs/formats/xml.md))
- **[Writing a format plugin](docs/plugins.md)** — what to implement to add a
  new format, with a worked example.
- **[Inferring schemas](docs/infer.md)** — learn a schema from examples.
- **[Comparing schemas](docs/operations.md)** — equivalence and
  backward-compatibility checks.
- **[API reference](docs/api.md)** — every public function and class.
- **[FAQ](docs/faq.md)** — common questions and gotchas.

## Running the tests

```bash
pip install pytest pyyaml tomli_w defusedxml
python3 -m pytest          # 224 tests
```

## Status

dataspec is **alpha** (v0.1.0a7) and under active development. The core model,
schema language, and format codecs are working and tested, but the public API may
change before a stable release. It is not yet on PyPI — install from a checkout.

Feedback and bug reports are welcome:
<https://github.com/tomlee/dataspec/issues>. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow, and
[SECURITY.md](SECURITY.md) for the trust model if you're parsing
untrusted input, and how to report a vulnerability.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Background

The schema model was inspired by Lee & Cheung,
[*"XML Schema Computations: Schema Compatibility Testing and Subschema
Extraction"*](docs/paper/Lee-Cheung-2010-XML-Schema-Computations-CIKM.pdf)
(CIKM 2010), but the library deliberately trades the paper's vocabulary for a
small, practical API.
