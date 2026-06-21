# API reference

Everything importable from `import dataspec`. Types: a **Document** is held by a
`Doc`; a **Schema** is a `root` reference plus named definitions (`Record` /
`Union`). See the [user guide](guide.md) for narrative and the
[model spec](design/model.md) for the formal definitions.

```python
import dataspec
dataspec.__version__        # "0.1.1a3"
```

---

## Documents

### `doc(value) -> Doc`
Build a `Doc` from a plain Python value. A `dict` becomes an edge list; a key
whose value is a `list` expands into one edge per item (a repeated label). A
scalar becomes a leaf. A bare list, an array-of-arrays, a non-string key, a
cycle, or nesting past the depth limit raises `DocumentError`.

### `class Doc`
A guarded handle on a Document node — either a **leaf** (a scalar value) or an
**internal node** (an ordered list of `(label, child)` edges).

**Construction**

| | |
|---|---|
| `Doc.of(value)` | same as `doc(value)` |
| `Doc.from_json(text)` / `from_yaml` / `from_toml` / `from_xml` | read a format string |
| `Doc.from_format(name, text)` | read by format name (`"json"`, …) |

**Shape & navigation**

| | |
|---|---|
| `.is_leaf` *(property)* | `True` for a scalar leaf |
| `.value` *(property)* | the scalar of a leaf (raises on an internal node) |
| `.edges() -> list[(str, Doc)]` | the ordered `(label, child)` edges |
| `.labels() -> list[str]` | distinct labels, in first-seen order |
| `.get(label) -> list[Doc]` | all children under `label` (a list — labels may repeat) |
| `.get_one(label) -> Doc` | the single child under `label` (raises unless exactly one) |
| `.count(label) -> int` | how many edges carry `label` |
| `.child(label) -> Doc` | a cursor to the single child (editable if it's a node) |

**Editing** (mutates the edge list; returns `self` for chaining)

| | |
|---|---|
| `.add(label, value)` | append an edge — a repeated label is how an array grows |
| `.set(label, value)` | replace the single child under `label`, or add it |
| `.remove(label)` | drop every edge under `label` |

**Export**

| | |
|---|---|
| `.to_data()` | the canonical Python form — a scalar, or a list of `(label, …)` tuples |
| `.to_grouped()` | a JSON-shaped projection: same-label edges grouped into a list |
| `.to_json(**opts)` / `.to_yaml()` / `.to_toml()` / `.to_xml()` | serialize to a format |
| `.to_format(name, **opts)` | serialize by format name |
| `.check_json()` / `.check_yaml()` / `.check_toml()` / `.check_xml() -> WriteReport` | simulate the matching `to_*`, no output |
| `.check_format(name) -> WriteReport` | simulate `to_format(name)`, no output (needs the format's `check`) |
| `.validate(schema) -> ValidationResult` | shorthand for `schema.validate(self)` |

`Doc` also supports `==` (compares the underlying data, against a `Doc` or a
plain value).

---

## Schemas

### `parse_schema(text) -> Schema`
Parse DSL text (`record` / `union` / `root`) into a `Schema`. Raises
`SchemaError` on malformed text or an undefined reference. See the
[DSL section of the guide](guide.md#schemas--the-dsl).

### `to_dsl(schema) -> str`
Serialize a `Schema` back to DSL text. `parse_schema(to_dsl(s))` is equivalent
to `s`.

### `infer(samples, root_name="Root") -> Schema`
Draft a schema from example Documents (`Doc`s or plain values). Cardinality
follows observed counts (present in every sample → required; sometimes absent →
optional; seen more than once → array); scalar children become unions; object
children become nested named records.

### The Python builder

| Function | Builds |
|---|---|
| `record(*fields) -> Record` | a closed record from `Field`s |
| `field(label, type, min=1, max=1) -> Field` | one field; `max=None` is unbounded |
| `union(*members, null=False) -> Union` | a value domain from kind atoms (`t.string`) and/or literal values |
| `ref(name) -> Ref` | a reference to a named definition |
| `schema(root, **env) -> Schema` | assemble a `Schema` (`root` is a `Ref` or a name string) |
| `t` | the scalar-kind namespace: `t.string`, `t.integer`, `t.number`, `t.boolean`, `t.date`, `t.time`, `t.datetime` |

```python
from dataspec import schema, record, union, field, ref, t
s = schema(ref("User"),
           User=record(field("name", union(t.string)),
                       field("tags", union(t.string), min=0, max=None)))
```

### `class Schema`
`Schema(root: Ref, env: dict[str, Definition] = None)` — a root reference plus
named definitions. Raises `SchemaError` if a reference is undefined or the root
doesn't resolve to a record.

| Method | |
|---|---|
| `.validate(doc) -> ValidationResult` | check a `Doc` against this schema |
| `.accepts(doc) -> bool` | `validate(doc).ok` |
| `.compatible_with(other) -> bool` | every document this accepts, `other` also accepts (backward-compat) |
| `.equivalent(other) -> bool` | both accept exactly the same documents |
| `.normalize() -> Schema` | merge structurally-identical named definitions |
| `.to_dsl() -> str` | serialize back to DSL |
| `.root`, `.env` | the root `Ref` and the name→definition map |
| `.resolve(t) -> Definition` | follow a `Ref` chain to a `Record` or `Union` |

### Definition & type classes

These are produced by the DSL and builder; you can also construct them directly.

- **`Record(fields: list[Field])`** — a closed record. `.fields`;
  `.field(label) -> Field | None`.
- **`Field(label, type, min=1, max=1)`** — one labeled edge rule. `.label`,
  `.type` (a `Ref` or `Union`), `.min`, `.max` (`None` = unbounded).
- **`Union(kinds=(), literals=(), null=False)`** — a value domain. `kinds` is a
  set of kind atoms (`STRING`, …), `literals` a set of values, `null` a bool.
- **`Ref(name)`** — a reference to a definition in the schema's `env`.
- Kind atoms: `STRING`, `INTEGER`, `NUMBER`, `BOOLEAN`, `DATE`, `TIME`,
  `DATETIME` (also under `t.*`).

---

## Validation results

### `class ValidationResult`
Returned by `Schema.validate`.

| | |
|---|---|
| `.ok` *(property)* | `True` if the document conforms |
| `bool(result)` | same as `.ok` |
| `.errors -> list[Error]` | every failure |
| `str(result)` | a readable multi-line summary |

### `class Error`
A named tuple `Error(path, message)` — unpacks as `(path, message)` and exposes
`.path` (e.g. `"$.order.items"`) and `.message`.

```python
r = s.validate(doc({"id": "x"}))
if not r.ok:
    for e in r.errors:
        print(e.path, e.message)
```

---

## Reading & writing formats

Low-level codecs over the canonical node form (a scalar, or a list of
`(label, node)` edges). Most code uses `Doc.from_*` / `Doc.to_*` instead.

| | |
|---|---|
| `read_json(text)` / `read_yaml` / `read_toml` / `read_xml` | parse → a node |
| `write_json(node, *, strict=False, report=None, indent=None)` | a node → JSON (groups same-label edges) |
| `write_yaml(node, *, strict=False, report=None)` | a node → YAML |
| `write_toml(node, *, strict=False, report=None)` | a node → TOML |
| `write_xml(node, *, strict=False, report=None)` | a node → XML |
| `check_json(node)` / `check_yaml` / `check_toml` / `check_xml` | simulate a write; return a `WriteReport`, no output |

`read_yaml`/`write_yaml` need `pyyaml`; `write_toml` needs `tomli_w`; `read_xml`
recommends `defusedxml` (else an `UnsafeXMLWarning`). See
[Formats](formats/overview.md) for per-format mapping and caveats.

### Adjustment reports (lossy writes)

Writing to a format that can't hold every value (TOML has no `null`; JSON/XML
have no date type) is **lenient by default**: the writer adjusts the value and
records it. `Doc.to_*` and `write_*` accept the same two options:

| | |
|---|---|
| `strict=True` | raise `WriteError` (carrying the report) if anything was adjusted |
| `report=a_WriteReport` | collect the adjustments into it, without raising |

```python
from dataspec import doc, WriteReport, WriteError

d = doc({"a": 1, "b": None})
d.to_toml()                          # 'a = 1\n' -- 'b' dropped, silently

rep = WriteReport()
d.to_toml(report=rep)
[(a.code, a.severity) for a in rep]  # [('null.omitted', 'warning')]

d.to_toml(strict=True)               # raises WriteError
```

### `class WriteReport`
Every adjustment a writer made. `.warnings` / `.errors` (lists of
`Adjustment`); `bool(report)` is `True` when there are no `"error"`-severity
entries (warnings are fine) — `if check_toml(node): ...` reads as "safe to
write." Iterable; `str(report)` is a readable multi-line summary.

### `class Adjustment`
A named tuple `Adjustment(path, code, message, severity)` — `severity` is
`"warning"` or `"error"`. Stable codes: `null.omitted` (TOML/XML), `temporal.stringified`
(JSON/YAML/XML), `float.special` (JSON `NaN`/`Infinity`), `key.sanitized` (XML).

---

## Format registry

Formats are plugins. The four built-ins register themselves on import.

| | |
|---|---|
| `register_format(Format(name, read, write, check=None))` | add a format, usable via `Doc.from_format` / `Doc.to_format` / `Doc.check_format` |
| `get_format(name) -> Format` | look one up by name (raises `DataspecError` if unknown) |
| `formats() -> list[str]` | every registered name, sorted |

```python
from dataspec import Format, register_format, Doc

register_format(Format(
    name="lines",
    read=lambda text: [("n", int(x)) for x in text.split()],
    write=lambda node, **opts: " ".join(str(v) for _, v in node),
))
Doc.from_format("lines", "1 2 3").to_format("lines")    # '1 2 3'
```

### `class Format`
A named tuple `Format(name, read, write, check=None)` — `read(text) -> node`,
`write(node, **opts) -> str`, and an optional `check(node) -> WriteReport` for
simulating a write without producing output. The four built-ins all provide
`check`; a plugin that omits it can still be used with `from_format`/
`to_format`, but `Doc.check_format` raises `DocumentError` for it.

---

## Exceptions & warnings

| | Raised when |
|---|---|
| `DataspecError` | base class for all dataspec errors |
| `SchemaError` | invalid schema text or structure (bad DSL, undefined `Ref`, bad cardinality) |
| `ParseError` | a document couldn't be read from its format |
| `DocumentError` | a value isn't a legal Document, or an invalid `Doc` operation |
| `WriteError` | a Document can't be represented in the target format (e.g. multi-rooted XML) |
| `DetachedNode` | (`DocumentError` subclass) a cursor used after its node was removed |
| `UnsafeXMLWarning` | `read_xml` fell back to the stdlib parser because `defusedxml` is missing |

---

## See also

- [User guide](guide.md) — narrative tour with examples.
- [A real-life example](example.md) — one schema across all four formats.
- [Formats](formats/overview.md) — per-format mapping and caveats.
- [Model spec](design/model.md) — the formal Document and Schema definitions.
