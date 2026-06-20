# Formats

dataspec treats JSON, YAML, TOML, and XML as four ways to write down the **same**
Document. Each format has:

- a `read_*(text)` function that parses a string into a Document, and
- a `write_*(doc)` function that serializes a Document back to a string.

```python
from dataspec import read_json, write_toml
write_toml(read_json('{"name": "Ann"}'))     # 'name = "Ann"\n'
```

Or go through a [`Doc`](../document.md), which dispatches to the same codecs:

```python
from dataspec import Doc
Doc.from_json('{"name": "Ann"}').to_toml()   # 'name = "Ann"\n'
```

Because they share one model, converting is just *read one, write another*. The
only thing you have to know is what each format can and can't represent. The
`Doc.to_*` methods take the same options (`strict`, `report`, `null_style`,
`wrap_key`, `root`) as the `write_*` functions below.

## How incompatibilities are handled

JSON, YAML, TOML, and XML don't all represent the same things the same way —
TOML has no `null`, XML element text is untyped, a literal `.` means
something different in TOML than in an XML name, and so on. Every such
incompatibility falls into exactly one of three buckets; there's no fourth
"just silently corrupts the value with no trace" case (and where one was
found, it was treated as a bug and fixed — see [SECURITY.md](../../SECURITY.md)
for that history):

1. **Input that's outright illegal raises.** Malformed text (`read_*`),
   nesting past the depth limit, an unsupported Python type going into a
   `Doc` — these raise `ParseError`/`DocumentError`/`SchemaError` immediately.
   Nothing is written or returned; there's no document to inspect.
2. **A value that's legal but can't be represented losslessly is *adjusted
   and reported*.** This is the [adjustment-report](#adjustment-reports)
   mechanism below — every code in the table is a value that changes shape
   on write, with a `WriteReport` entry to prove it happened. Lenient by
   default; `report=`/`check_*` show you the list; `strict=True` turns any
   of them into a `WriteError` instead.
3. **A handful of things are silently normalized on *read*, with no report
   mechanism at all**, because they were never part of the Document model to
   begin with — there's nothing for a `WriteReport` to describe, since
   nothing was written. Specifically: **comments** (TOML/YAML/XML allow them;
   the parser discards them before dataspec's code runs) and **XML namespace
   prefixes** (`<n:a>` reads as `a`). If you need to know whether a comment
   was present, you have to check the raw text yourself before calling
   `read_*` — there's no flag or report for it.

In practice, (3) is a short, fixed list (documented per format below); when in
doubt about a *specific* value, `check_*`/`report=` (bucket 2) will tell you,
and anything not covered by either 2 or 3 falls through to bucket 1.

## Conversion is lenient by default

When a target format can't hold a value (TOML/XML have no `null`; JSON has no
dates), dataspec **adjusts** the data to make it fit and writes successfully — it
doesn't make you handle an error for the common case:

```python
from dataspec import write_toml
write_toml({"x": None})         # '' -- 'x' is dropped (TOML has no null)
write_toml([1, 2, 3])           # wrapped under the key "value"
```

Every adjustment is **recorded** so nothing is lost silently. You choose how much
you want to know:

```python
from dataspec import write_toml, check_toml, WriteReport, WriteError

# 1. just convert — adjustments are made silently
write_toml(doc)

# 2. convert and inspect what changed
rep = WriteReport()
write_toml(doc, report=rep)
for adj in rep:
    print(adj.severity, adj.path, adj.message)

# 3. inspect *without* writing anything
rep = check_toml(doc)
if not rep:                       # has error-level adjustments
    print("would lose data:", rep)

# 4. refuse anything lossy — guarantees a perfect round-trip
write_toml(doc, strict=True)      # raises WriteError if not lossless
```

Each adjustment has a **severity**: `"warning"` for conventional, recoverable
changes (a `null` field omitted, a date written as a string) and `"error"` for
changes likely to surprise or corrupt meaning (a `null` array item dropped, which
shifts positions). `bool(report)` is `True` when there are no error-level
adjustments. `strict=True` ignores severity and raises on *anything* that can't
round-trip — and the resulting `WriteError` carries the full report on
`.report`. See [Adjustment reports](#adjustment-reports) below.

## How `null` is handled

JSON and YAML have `null`. TOML and XML don't. When writing to a format without
`null`, dataspec:

- **omits** a `null` **object field** (a `warning` — absence reads back close to
  null);
- **drops** a `null` **array item** (an `error` — it shifts later positions);
- writes a top-level `null` as an **empty document** (an `error`).

`null_style="drop"` (the default is `"omit"`) demotes the dropped-array-item case
from `error` to `warning`, for when you've decided dropping is fine. Either way,
`strict=True` turns any of these into a `WriteError`.

## Adjustment reports

`check_json` / `check_yaml` / `check_toml` / `check_xml` simulate a write and
return a `WriteReport` without producing output — a pre-flight check. The same
report is available from any writer via `report=`. A report is a list of
`Adjustment(path, code, message, severity)` with `.warnings`, `.errors`, and a
truthiness of "no errors". The stable `code` values:

| code | severity | meaning |
|---|---|---|
| `null.field.omitted` | warning | `null` object field dropped (TOML/XML) |
| `null.item.dropped` | error\* | `null` array item dropped (TOML/XML) |
| `null.toplevel.empty` | error | top-level `null` became an empty doc (TOML/XML) |
| `toplevel.wrapped` | warning | top-level array/scalar wrapped under `wrap_key` (TOML/XML) |
| `temporal.stringified` | warning | date/time written as a string (JSON/XML/YAML-time/TOML-offset-time) |
| `float.special` | error | `NaN`/`Infinity` written to JSON |
| `key.coerced` | warning | non-string object key coerced to a string (JSON) |
| `key.sanitized` | warning | object key rewritten to a legal XML element name |
| `key.collision` | error | two distinct keys coerced/sanitized to the same key, one overwriting the other (JSON/XML) |
| `array.nested.ambiguous` | error | nested array wrapped in `<item>` elements (XML) |
| `string.ambiguous` | warning | a string that looks like a number/bool/null written to XML; reads back as that type, not as a string |
| `string.line_ending_normalized` | warning | a string containing `\r` written to XML; the XML spec normalizes it to `\n` on read |
| `container.empty.ambiguous` | warning | an empty object/array written to XML; reads back as an empty string, not as an empty object/array |
| `string.illegal_xml_char` | error | string contains a character with no legal XML representation at all; removed |
| `integer.out_of_range` | warning | integer outside TOML's signed 64-bit range; round-trips here, but may not in another TOML implementation |
| `integer.precision_risk` | warning | integer outside JavaScript's safe-integer range (`±2**53`); round-trips here, but may lose precision in a JS-based JSON parser (JSON) |

\* `warning` under `null_style="drop"`.

## Comparison table

How each format represents the building blocks of a Document.
Legend: ✅ full support · ⚠️ works with a caveat · ❌ not supported.

| Capability | JSON | YAML | TOML | XML |
|---|:---:|:---:|:---:|:---:|
| Object / map | ✅ | ✅ | ✅ | ⚠️ |
| Array / list | ✅ | ✅ | ✅ | ⚠️ |
| String | ✅ | ✅ | ✅ | ⚠️ |
| Integer | ✅ | ✅ | ⚠️ | ⚠️ |
| Number (float) | ✅ | ✅ | ✅ | ⚠️ |
| Boolean | ✅ | ✅ | ✅ | ⚠️ |
| `null` | ✅ | ✅ | ❌ | ❌ |
| Date / time / datetime | ⚠️ | ⚠️ | ✅ | ⚠️ |
| Top-level array | ✅ | ✅ | ⚠️ | ⚠️ |
| Top-level scalar | ✅ | ✅ | ⚠️ | ⚠️ |
| Nested arrays (array of arrays) | ✅ | ✅ | ✅ | ⚠️ |
| Comments in the format | ❌ | ✅ | ✅ | ✅ |
| Exact scalar type after round-trip | ✅ | ✅ | ✅ | ⚠️ |

Notes on the caveats:

- **Top-level arrays/scalars** aren't native to TOML/XML, so they're wrapped
  under a key (`wrap_key`, default `"value"`) and the wrap is reported. **Nested
  arrays in XML** have no element name, so each level is wrapped in synthetic
  `<item>` elements (reported as an `error`, since it isn't cleanly reversible).
- **XML arrays** are repeated elements and must be a named field. **XML scalars**
  are untyped text, so types are recovered on read with best-effort guessing
  (`"30"` → `30`, `"true"` → `True`), which means a string that looks like a
  number, boolean, or `null` comes back as that type, not as a string — this
  is reported (`string.ambiguous`), and `strict=True` rejects it.
- **Empty objects and empty arrays have no representation in XML.** A self-
  closing element (`<x/>`) is the only way to write "nothing here," so an
  empty object, an empty array, and an empty string are indistinguishable on
  read — all three come back as `""`. Writing an empty object/array is
  reported (`container.empty.ambiguous`) rather than silently losing the
  distinction.
- **A handful of code points (most C0 controls, surrogates) have no legal
  representation in XML 1.0 at all**, not even a character reference. A
  string containing one is stripped of those characters before writing,
  reported as `string.illegal_xml_char` — the only `error`-severity string
  adjustment, since the alternative is writing output that doesn't parse as
  XML at all.
- **TOML integers are signed 64-bit** per the spec; dataspec's own
  read/write round-trips a larger Python `int` fine (reported as
  `integer.out_of_range`), but another TOML implementation may reject it.
- **Dates** have no representation in JSON or XML, so they travel as ISO-8601
  strings; schemas accept those. TOML has native date types. YAML reads/writes
  dates and datetimes natively but not standalone times.
- **Comments** are allowed by three of the formats but are never part of the
  data model, so they are not preserved across a read/write.

## XML profile

XML is far more expressive than data needs to be, so dataspec supports a
restricted **data-XML** profile: elements only, used purely to hold tree-shaped
data. Attributes, mixed content, namespaces, and CDATA constructs are **not**
part of the model. See [XML](xml.md) for the details and the rationale.

## Extending with a new format

Formats are plugins. Each is a `Format` with a name, file extensions, and three
codec callables over plain Python — `read(text) -> Document`,
`write(data, *, strict=False, report=None, **opts) -> str`, and
`check(data, **opts) -> WriteReport`. Register one and it's usable everywhere,
including `Doc.from_format` / `Doc.to_format`:

```python
from dataspec import Format, register_format, WriteReport, Doc

register_format(Format(
    name="lines", extensions=(".lines",),
    read=lambda text: [int(x) for x in text.split()],
    write=lambda data, **o: " ".join(map(str, data)),
    check=lambda data, **o: WriteReport(),
))

Doc.from_format("lines", "1 2 3").to_data()      # [1, 2, 3]
```

The four built-ins (`json`, `yaml`, `toml`, `xml`) register themselves on import;
`formats()` lists what's available. See the
[API reference](../api.md#format-registry), and
[Writing a format plugin](../plugins.md) for the full guide — the adjustment-
report contract, a worked example with `strict`/`check`, and a testing
checklist.

## Per-format pages

- **[JSON](json.md)** — the baseline; no dependencies.
- **[YAML](yaml.md)** — the JSON-compatible core of YAML.
- **[TOML](toml.md)** — native dates, no `null`, top-level object required.
- **[XML](xml.md)** — the data-XML profile, and how it maps to objects/arrays.
