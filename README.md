# omnist

[![tests](https://github.com/tomlee/omnist/actions/workflows/test.yml/badge.svg)](https://github.com/tomlee/omnist/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](#installation)
[![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)
[![status](https://img.shields.io/badge/status-alpha-orange)](#status)

**omnist** ("omni-structure") is **one canonical data model for JSON, YAML,
TOML, XML, and its own native OML (Omnist Markup Language)** — read any of
them into a single tree, validate it against a schema, compare schema
versions, and write it back out to any of the others.

```python
from omnist import parse_schema, doc

s = parse_schema('''
    record Member { "name": string, "role": string }
    record Team   { "name": string, "members" [1,]: Member }
    root Team
''')

s.validate(doc({"name": "Platform",
                "members": [{"name": "Ann", "role": "dev"}]})).ok    # True
```

## Why omnist

If your service handles config or payloads in more than one format, you usually
get a different library — and a different mental model — for each. omnist
gives you **one** model and **one** schema language over it, grounded in a small,
self-contained formal model (inspired by Lee & Cheung, CIKM 2010):

- A **Document** is a *tree* — an ordered list of labeled edges. Arrays are
  just repeated labels, so the *same* Document represents JSON, YAML, TOML,
  XML (including its interleaved repeated elements), and OML — omnist's own
  format, the only one with zero loss in either direction.
- A **Schema** is named `record` definitions (closed named fields, each with a
  cardinality), where every field's type is always exactly one fixed scalar
  (optionally nullable) or one `Ref` to a named record — referenced by name for
  reuse and recursion. **Validate** a Document, **compare** two schemas for
  backward-compatibility, or **infer** a schema from examples.
- **Restrictive by default** — a schema guarantees structure; there are no
  structureless escape hatches, and scalar types are never composed.

The model is defined formally in
[docs/design/model.md](docs/design/model.md).

## A 60-second tour

```python
from omnist import Doc, parse_schema, infer, doc, read_json

# read one format, write another -- through one Document
Doc.from_json('{"id": 1, "tags": ["a", "b"]}').to_yaml()

# describe a shape and check data against it; errors carry exact paths
s = parse_schema('record R { "id": integer, "tags" [0,]: string }\nroot R')
print(s.validate(doc({"id": "x", "tags": ["a"]})))
#   invalid:
#     at $.id: expected integer, got string ('x')

# learn a schema from examples
print(infer([doc({"id": 1, "tags": ["a"]})]).to_dsl())
#   record Root {
#       "id": integer,
#       "tags": string,
#   }
#   root Root

# is a schema change backward-compatible? (operations are Schema methods)
v1 = parse_schema('record R { "host": string }\nroot R')
v2 = parse_schema('record R { "host": string, "port" [0,1]: integer }\nroot R')
v1.compatible_with(v2)        # True -- adding an optional field is safe

# schema-directed deserialization: upgrade leaves to match the schema
s2 = parse_schema('record R { "d": date }\nroot R')
read_json('{"d": "2024-01-01"}', schema=s2)   # [('d', datetime.date(2024, 1, 1))]
```

Run the full demo: `python3 examples/canonical_model.py`.

## Installation

Requires **Python 3.11+** (it uses the standard-library `tomllib`). The core and
JSON support have no dependencies.

```bash
git clone https://github.com/tomlee/omnist.git
cd omnist
python3 -m venv .venv && source .venv/bin/activate
pip install .                    # core + JSON
pip install pyyaml tomli_w defusedxml   # YAML / writing TOML / hardened XML
```

## Documentation

Full index: **[docs/](docs/README.md)**.

- **[User guide](docs/guide.md)** — the practical tour: documents, the DSL, the
  Python builder, validation, operations, codecs, inference.
- **[API reference](docs/api.md)** — every public name, with signatures.
- **[A real-life example](docs/example.md)** — one order schema validated against
  documents in JSON, YAML, TOML, and XML, plus a compatibility check.
- **[Formats](docs/formats/overview.md)** — how each format maps to the model and
  its caveats ([JSON](docs/formats/json.md) · [YAML](docs/formats/yaml.md) ·
  [TOML](docs/formats/toml.md) · [XML](docs/formats/xml.md)).
- **[Model spec](docs/design/model.md)** — the formal Document and Schema models,
  self-contained and plain (no paper required).

## Status

omnist is **alpha** (v0.1.2), built around a small, self-contained
formalism; the public API may still change before a stable release. Not yet
on PyPI — install from a checkout.

Feedback and bug reports welcome:
<https://github.com/tomlee/omnist/issues>. See [SECURITY.md](SECURITY.md) for
the trust model if you parse untrusted input.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Background

The model is **inspired by** Lee & Cheung,
[*"XML Schema Computations: Schema Compatibility Testing and Subschema
Extraction"*](docs/paper/Lee-Cheung-2010-XML-Schema-Computations-CIKM.pdf)
(CIKM 2010), simplified for the JSON family of formats. You don't need the
paper to use omnist — the [model spec](docs/design/model.md) is self-contained.
