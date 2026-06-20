# API reference

Everything below is importable directly from `dataspec`:

```python
from dataspec import Doc, doc, obj, parse_schema, infer, WriteError   # etc.

d = Doc.from_json('{"name": "Ann", "address": {"city": "London"}}')
schema = parse_schema("root { name: string, address: { city: string } }")
schema.validate(d).ok      # True
```

## Documents — the `Doc` API

A `Doc` is a guarded, navigable Document tree (see [Documents](document.md) for
the full guide). Build with `doc(...)` / `Doc.from_*`; everything else is methods.

| Member | Description |
|---|---|
| `doc(value=…)` | factory: empty object, or import a Python value (validated, copied) |
| `Doc.from_data(value)` | same as `doc(value)` |
| `Doc.from_json/from_yaml/from_toml/from_xml(text)` | import from a format string |
| `Doc.from_format(name, text)` | import via a registered format (incl. plugins) |
| `.kind` | `"object"` / `"array"` / `"scalar"` |
| `.parent`, `.key`, `.path`, `.value` | cursor position; scalar value |
| `.get(k)` / `.get_or(k, d)` / `.at(i)` | read a snapshot (copy for containers) |
| `.child(k)` / `.child_at(i)` | a live cursor into a sub-object/array |
| `.has(k)` / `.keys()` / `.items()` / `.len()` | inspect |
| `.add(k, v)` / `.add_object(k)` / `.add_array(k)` | create a new child |
| `.append(v)` / `.append_object()` / `.append_array()` / `.insert(i, v)` | array growth |
| `.set(k, scalar)` | modify an existing scalar leaf in place |
| `.remove(k)` / `.drop()` | delete a subtree / remove self from parent |
| `.to_json/to_yaml/to_toml/to_xml(**opts)` / `.to_format(name, **opts)` | serialize |
| `.to_data()` | a detached deep copy as plain Python |
| `len(d)`, `iter(d)`, `k in d`, `==` | container-like dunders |

Illegal values (non-string keys, unsupported types, cycles, nesting past a
depth limit) raise `DocumentError`. `set` only modifies a scalar — reshaping
is `remove` + `add`.

## Reading and writing formats

Each `read_*` takes a **string** and returns a Document. Each `write_*` takes a
Document and returns a **string**.

| Function | Notes |
|---|---|
| `read_json(text)` | — |
| `write_json(doc, *, indent=None, sort_keys=False, strict=False, report=None)` | `indent` pretty-prints |
| `check_json(doc)` | simulate the write; return a `WriteReport`, no output |
| `read_yaml(text)` | needs `pyyaml` |
| `write_yaml(doc, *, sort_keys=False, strict=False, report=None)` | needs `pyyaml` |
| `check_yaml(doc)` | needs `pyyaml` |
| `read_toml(text)` | stdlib `tomllib` |
| `write_toml(doc, *, strict=False, report=None, null_style="omit", wrap_key="value")` | needs `tomli_w` |
| `check_toml(doc, *, null_style="omit", wrap_key="value")` | needs `tomli_w` |
| `read_xml(text)` | `defusedxml` recommended |
| `write_xml(doc, *, root="root", strict=False, report=None, null_style="omit", wrap_key="value")` | `root` names the wrapper element |
| `check_xml(doc, *, root="root", null_style="omit", wrap_key="value")` | — |

All writers are **lenient by default**: an unrepresentable value is adjusted and
recorded. `report=` collects the adjustments, `strict=True` raises a `WriteError`
(with `.report`) on any of them, and `check_*` returns the report without
writing. See [Formats](formats/overview.md) for what each can represent and the
full list of adjustment codes.

**`WriteReport`** — `.adjustments` (list of `Adjustment`), `.warnings`,
`.errors`; `bool(report)` is `True` when there are no errors.
**`Adjustment`** — a `NamedTuple(path, code, message, severity)`.
**`finish_write(text, rep, *, strict=False, report=None) -> str`** — the
shared `strict`/`report` decision every built-in writer ends with; format
plugins can call it too instead of reimplementing it (see
[Writing a format plugin](plugins.md)).

## Schemas

**`parse_schema(text) -> Schema`** — parse DSL text into a schema. Undefined
type references raise `SchemaError`. `Schema.parse(text)` is the same thing.

**`to_dsl(schema) -> str`** — serialize a schema back to DSL text. Also available
as `schema.to_dsl()`.

**`infer(samples, open_objects=False) -> Schema`** — draft a schema from example
Documents. See [Inferring schemas](infer.md).

### `Schema`

| Member | Description |
|---|---|
| `Schema(root, types=None)` | construct from a root `Type` and a dict of named types |
| `Schema.parse(text)` | classmethod; parse DSL text |
| `schema.validate(doc) -> ValidationResult` | check a document |
| `schema.accepts(doc) -> bool` | shortcut for `validate(doc).ok` |
| `schema.compatible_with(other) -> bool` | every doc this accepts, `other` accepts too |
| `schema.equivalent(other) -> bool` | both accept exactly the same docs |
| `schema.normalize() -> Schema` | merge identical named types |
| `schema.to_dsl() -> str` | serialize to DSL text |
| `schema.root`, `schema.types` | the root type and named-type dict |

### `ValidationResult`

| Member | Description |
|---|---|
| `result.ok` | `True` if valid |
| `bool(result)` | same as `.ok` |
| `result.errors` | list of `Error` |
| `str(result)` | readable multi-line summary |

### `Error`

A `NamedTuple` with `.path` (e.g. `$.items[0].id`) and `.message`. It also
unpacks as `(path, message)`.

## Schema builder

The ergonomic way to build a schema in Python (see
[Schemas](schema.md#the-python-builder)). All importable from `dataspec`.

| Name | Builds |
|---|---|
| `t.string`, `t.integer`, `t.number`, `t.boolean`, `t.date`, `t.time`, `t.datetime` | scalar type atoms (namespaced under `t`) |
| `t.any` | `AnyType()` |
| `obj(**fields)` | a closed object; values are a type or `optional(type)` |
| `optional(T)` | marks a field not-required (inside `obj`) |
| `nullable(T)` | a copy of `T` that also accepts null |
| `arr(item, min=0, max=None)` | an array type |
| `mapping(value_type)` | a map `{[string]: T}` |
| `enum(*values)` | a scalar restricted to literal values |
| `ref(name)` | a named-type reference |
| `schema(root, **named_types) -> Schema` | assemble (and check refs) |

The type atoms are namespaced under `t` so they don't shadow Python's `any` or
the stdlib `datetime` / `date` / `time`.

```python
from dataspec import schema, obj, optional, doc, t

s = schema(obj(name=t.string, address=optional(obj(city=t.string))))
s.validate(doc({"name": "Ann", "address": {"city": "London"}})).ok        # True
```

## Schema types

The lower-level classes the builder and DSL produce. All are subclasses of
`Type`, and any type accepts `nullable=True`.

| Class | Constructor | Describes |
|---|---|---|
| `ScalarType` | `ScalarType(kinds, nullable=False, enum=None)` | a scalar; `kinds` is a set of kind constants |
| `ArrayType` | `ArrayType(item, min=0, max=None, nullable=False)` | an array of `item` |
| `ObjectType` | `ObjectType(fields, rest=None, nullable=False)` | an object; `fields` maps names to `Field` |
| `Field` | `Field(type, required)` | one object field |
| `AnyType` | `AnyType()` | matches anything, including null |
| `RefType` | `RefType(name, nullable=False)` | a reference to a named type |

`ObjectType.rest` controls extra keys: `None` = closed, `AnyType()` = open,
any other type = a map of that value type. `ObjectType.of(required=..., optional=...,
rest=...)` is a convenience builder.

The scalar **kind constants** are `STRING`, `INTEGER`, `NUMBER`, `BOOLEAN`,
`DATE`, `TIME`, `DATETIME`.

`ObjectType` and `ArrayType` also have uniform child getters: `obj.field(name)`,
`obj.children()`, `obj.field_names()`, `arr.children()`, plus the `obj.rest` /
`arr.item` attributes.

```python
from dataspec import Schema, ObjectType, ScalarType, Field, STRING, doc

s = Schema(ObjectType({
    "name":    Field(ScalarType({STRING}), required=True),
    "address": Field(ObjectType({"city": Field(ScalarType({STRING}), required=True)}), required=False),
}))
s.validate(doc({"name": "Ann"})).ok        # True
```

## Format registry

Formats are pluggable (see [Formats](formats/overview.md#extending-with-a-new-format)).

| Name | Description |
|---|---|
| `Format(name, read, write, check, extensions=(), requires=())` | a format plugin |
| `register_format(fmt)` | add/replace a format |
| `get_format(name) -> Format` | look up (raises `KeyError` if unknown) |
| `formats() -> list[str]` | names of registered formats |

## Exceptions

All inherit from `DataspecError`, so you can catch everything with one `except`.

| Exception | Raised when |
|---|---|
| `DataspecError` | base class |
| `SchemaError` | a schema is invalid (bad DSL, unknown type reference) |
| `ParseError` | a document can't be read (outside a format's supported profile) |
| `WriteError` | a document can't be represented in a target format (`strict=True`); carries `.report` |
| `DocumentError` | a value isn't a legal Document, or a `Doc` operation is invalid |
| `DetachedNode` | a `Doc` cursor was used after its node was removed (subclass of `DocumentError`) |

One warning, not an exception — parsing still succeeds:

| Warning | Raised when |
|---|---|
| `UnsafeXMLWarning` | `read_xml` fell back to the standard library's XML parser because `defusedxml` isn't installed; that parser has no protection against entity-expansion/XXE attacks on untrusted input |

## See also

- [Concepts](concepts.md) — the five ideas this API implements.
- [Documents](document.md) — the `Doc` API, explained with examples.
- [Schemas](schema.md) — the schema language and Python builder, explained with examples.
