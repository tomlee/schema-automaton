# Architecture

dataspec is built in layers. Each layer is usable on its own, and higher layers
are thin conveniences over lower ones — there is one source of truth for data
(plain Python) and one for schemas (the type tree).

## Layers

```
            ┌───────────────────────────────────────────────┐
   object   │  Doc  (data DOM)        Schema builder (obj…) │   high-level,
   layer    │  build / navigate / edit / validate / emit    │   ergonomic
            └───────────────┬───────────────────┬───────────┘
                            │                   │
            ┌───────────────┴───────────────────┴───────────┐
   core     │  Document (plain Python)     Schema (types)   │   the two
   model    │                              validate / infer │   source models
            └───────────────┬───────────────────────────────┘
                            │
            ┌───────────────┴───────────────────────────────┐
   codec    │  Format registry:  json · yaml · toml · xml   │   pluggable
   layer    │  read_* / write_* / check_*  (plain Python)   │   serialization
            └───────────────────────────────────────────────┘
```

- **Codec layer** — the functional `read_*` / `write_*` / `check_*` functions
  operate on plain Python and do the actual parsing and serialization. They are
  registered as `Format` plugins (see below).
- **Core model** — a **Document** is plain Python data; a **Schema** is a tree of
  type objects. `Schema.validate` checks a Document against a Schema; `infer`
  builds a Schema from sample Documents.
- **Object layer** — `Doc` wraps a Document and is the guarded, navigable
  structure you usually program against. The schema **builder** (`obj`, `arr`, …)
  constructs Schemas in Python. Both are sugar: a `Doc` holds plain Python; the
  builder produces ordinary type objects.

You can stay purely functional or work entirely in the object layer — they meet
in the middle and produce the same output:

```python
from dataspec import write_toml, read_json, Doc

s = '{"name": "Ann", "address": {"city": "London"}}'

write_toml(read_json(s))          # purely functional
Doc.from_json(s).to_toml()        # the object layer — same result
```

## The OO structure

### Document side

| Class / fn | Role |
|---|---|
| `Doc` | a node (object, array, or scalar) in a Document tree; a live cursor |
| `doc(value)` | factory: import a Python value into a `Doc` |
| `Doc.from_json` / `from_format` … | factory: import from a format string |
| `DocumentError` | raised when a value isn't a legal Document, or an op is invalid |

A `Doc` is a **cursor**: `child("k")` returns a live `Doc` into that subtree, so
edits propagate. **Leaves are not nodes** — reading a scalar (`get`, `at`) returns
the plain immutable value. The tree is *guarded*: every value put in is validated
against the Document model and copied in, so it can never become malformed.

### Schema side

| Class / fn | Role |
|---|---|
| `Schema` | a root `Type` plus named types; `validate` / `compatible_with` / `normalize` / `to_dsl` |
| `Type` → `ObjectType`, `ArrayType`, `ScalarType`, `AnyType`, `RefType` | the type tree |
| `Field` | a named entry in an `ObjectType` (a type + required flag) |
| `obj`, `arr`, `mapping`, `enum`, `optional`, `nullable`, `ref`, `schema`, `t` | the Python builder (`t` holds the scalar type atoms) |
| `parse_schema` / `to_dsl` | DSL text ⇄ `Schema` |
| `infer` | sample Documents → `Schema` |

The schema tree is **immutable**: build it (via builder, DSL, or inference), read
it (via `field` / `children` / attributes), but don't edit it in place. Types
describe *domains*; they are never attached to Document nodes.

### Format side

| Class / fn | Role |
|---|---|
| `Format` | a plugin: `name`, `extensions`, `read` / `write` / `check` callables |
| `register_format(fmt)` | add a format to the registry |
| `get_format(name)` / `formats()` | look up / list registered formats |

The four built-ins (`json`, `yaml`, `toml`, `xml`) register themselves when
`dataspec` is imported. `Doc.to_format` / `Doc.from_format` dispatch through the
registry, so a newly registered format is immediately usable. See
[Formats](formats/overview.md#extending-with-a-new-format).

## Module map

| Module | Contents |
|---|---|
| `dataspec.document` | `Doc`, `doc`, the import guard |
| `dataspec.schema` | `Schema`, the `Type` tree, `validate`, comparison ops |
| `dataspec.builder` | the Python schema builder + scalar singletons |
| `dataspec.dsl` | `parse_schema`, `to_dsl` |
| `dataspec.infer` | `infer` |
| `dataspec.formats` | the codecs + built-in `Format` registration |
| `dataspec.registry` | the `Format` plugin registry |
| `dataspec.report` | `WriteReport`, `Adjustment` (conversion adjustments) |
| `dataspec.errors` | the exception hierarchy |

## Invariants worth knowing

1. **Structure vs. domain.** Document nodes hold structure and values; types
   (domains) live only in Schemas. We never store a type on a Document node.
2. **Plain Python is canonical.** A `Doc` is a guarded view over a plain-Python
   tree; `to_data()` always returns it. Schemas are plain type objects.
3. **The guard is the gate.** All Document mutation goes through `Doc`, which
   validates and copies in — so a `Doc` is always a well-formed Document.
4. **One model, many doors.** DSL, builder, and inference all yield the same
   `Schema` object tree; `read_*`, literals, and `from_format` all yield the same
   Document.

## See also

- [Concepts](concepts.md) — the five ideas this architecture implements.
- [Documents](document.md) — the `Doc` API, explained with examples.
- [Schemas](schema.md) — the schema language and Python builder, explained with examples.
