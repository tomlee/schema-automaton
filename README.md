# dataspec

[![tests](https://github.com/tomlee/dataspec/actions/workflows/test.yml/badge.svg)](https://github.com/tomlee/dataspec/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](#installation)
[![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)
[![status](https://img.shields.io/badge/status-alpha-orange)](#status)

**One canonical data model for JSON, YAML, TOML, and XML** — read any of them
into a single Data Tree, validate it against a schema, compare schema versions,
and write it back out to any of the others.

```python
from dataspec import parse_schema, doc

s = parse_schema('''
    record Member { "name": string, "role": "dev" | "pm" }
    record Team   { "name": string, "members" [1,]: Member }
    root Team
''')

s.validate(doc({"name": "Platform",
                "members": [{"name": "Ann", "role": "dev"}]})).ok    # True
```

## Why dataspec

If your service handles config or payloads in more than one format, you usually
get a different library — and a different mental model — for each. dataspec
gives you **one** model and **one** schema language over it, grounded in a formal
data model (Lee & Cheung's Data Tree / Schema Automaton):

- A **Document** is a *Data Tree* — an ordered list of labeled edges. Arrays are
  just repeated labels, so the *same* Document represents JSON, YAML, TOML, and
  XML, including XML's interleaved repeated elements.
- A **Schema** is `record` (closed named fields, each with a cardinality) and
  `union` (a value domain) definitions, referenced by name for reuse and
  recursion. **Validate** a Document, **compare** two schemas for
  backward-compatibility, or **infer** a schema from examples.
- **Restrictive by default** — a schema guarantees structure; there are no
  structureless escape hatches.

The model is defined formally in
[docs/design/model.md](docs/design/model.md).

## A 60-second tour

```python
from dataspec import Doc, parse_schema, infer, doc

# read one format, write another -- through one Document
Doc.from_json('{"id": 1, "tags": ["a", "b"]}').to_yaml()

# describe a shape and check data against it; errors carry exact paths
s = parse_schema('record R { "id": integer, "tags" [0,]: string }\nroot R')
print(s.validate(doc({"id": "x", "tags": ["a"]})))
#   invalid:
#     at $.id: 'x' is not in union{integer}

# learn a schema from examples
print(infer([doc({"id": 1, "tags": ["a"]})]).to_dsl())

# is a schema change backward-compatible? (operations are Schema methods)
v1 = parse_schema('record R { "host": string }\nroot R')
v2 = parse_schema('record R { "host": string, "port" [0,1]: integer }\nroot R')
v1.compatible_with(v2)        # True -- adding an optional field is safe
```

Run the full demo: `python3 examples/canonical_model.py`.

## Installation

Requires **Python 3.11+** (it uses the standard-library `tomllib`). The core and
JSON support have no dependencies.

```bash
git clone https://github.com/tomlee/dataspec.git
cd dataspec
python3 -m venv .venv && source .venv/bin/activate
pip install .                    # core + JSON
pip install pyyaml tomli_w defusedxml   # YAML / writing TOML / hardened XML
```

## Documentation

- **[User guide](docs/guide.md)** — the practical tour: documents, the DSL, the
  Python builder, validation, operations, codecs, inference, a real-life example.
- **[Model spec](docs/design/model.md)** — the formal Document and Schema models
  and their grounding in the Schema Automaton.

## Status

dataspec is **alpha** (v0.1.1a1). The model was redesigned around the formal
Data Tree / Schema Automaton; the public API may still change before a stable
release. Not yet on PyPI — install from a checkout.

Feedback and bug reports welcome:
<https://github.com/tomlee/dataspec/issues>. See [SECURITY.md](SECURITY.md) for
the trust model if you parse untrusted input.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Background

The model follows Lee & Cheung,
[*"XML Schema Computations: Schema Compatibility Testing and Subschema
Extraction"*](docs/paper/Lee-Cheung-2010-XML-Schema-Computations-CIKM.pdf)
(CIKM 2010) — adopting its Data Tree and Schema Automaton, simplified for the
JSON family of formats.
