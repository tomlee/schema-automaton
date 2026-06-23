# Schema-directed deserialization

Every reader (`read_json` / `read_yaml` / `read_toml` / `read_xml` / `read_oml`,
and the matching `Doc.from_*`) produces a [node](glossary.md) from raw text.
**Without a `schema=`**, every leaf is exactly whatever the format's own
native parser produced — nothing is upgraded. **With `schema=`**, the reader
additionally converts each leaf to match the schema's declared
[`Scalar`](glossary.md) kind, wherever the conversion is **value-exact**.
This page covers that conversion: what changes, what doesn't, and why it's
safe to do without guessing.

## The core distinction, demonstrated

The same JSON text, read with and without a schema, can hand back a Document
where the same field holds a *different Python type*. That's the whole
point of the feature:

```python
from omnist import parse_schema, read_json

text = '{"d": "2024-01-01", "n": 3}'

# No schema: leaves are exactly what JSON's own parser produces.
no_schema = read_json(text)
print(no_schema)                  # [('d', '2024-01-01'), ('n', 3)]
print(type(dict(no_schema)["d"]))  # <class 'str'>

# With schema: leaves are additionally upgraded to match the declared Scalar.
s = parse_schema('record R { "d": date, "n": number }\nroot R')
with_schema = read_json(text, schema=s)
print(with_schema)                  # [('d', datetime.date(2024, 1, 1)), ('n', 3.0)]
print(type(dict(with_schema)["d"]))  # <class 'datetime.date'>
```

Without `schema=`, the JSON string `"2024-01-01"` is a plain `str` — JSON has
no `date` type, so its parser can't produce anything else. With `schema=`,
the same string is upgraded to a real `datetime.date` because the schema
says the field `d` is a `date` and the string is a value-exact ISO-8601 date.
Likewise the JSON integer `3` becomes the Python `float` `3.0`, because the
schema says `n` is a `number`.

## What "no schema" already looks like, per format

The JSON "before" picture above — a leaf is just whatever the format's
native parser hands back — is not the same starting point for every format.
Some formats' own parsers already produce native Python temporal types for
some scalars, with no schema involved at all:

| Format | A date leaf with **no** `schema=` |
|---|---|
| JSON | `str` (e.g. `"2024-01-01"`) — JSON has no date type |
| YAML | `datetime.date` already — PyYAML's own loader recognizes unquoted ISO dates |
| TOML | `datetime.date` already — `tomllib`/TOML's grammar has a native date literal |
| XML | `str` (e.g. `"2024-01-01"`) — XML has no date type |
| OML | `str` if written as a quoted string; OML has no separate date literal either, so a `date` leaf only becomes a real `datetime.date` once `schema=` upgrades it |

This means that for YAML and TOML, reading a date field *without* a schema
can already give you a `datetime.date` — passing `schema=` in that case is a
no-op for that field (the value's already value-exact for the declared
scalar). For JSON, XML, and OML, the upgrade from `str` to `datetime.date`
only happens once a schema is supplied. Verified directly:

```python
from omnist import parse_schema, read_json, read_yaml, read_toml, read_xml

s = parse_schema('record D { "d": date }\nroot D')

type(dict(read_json('{"d": "2024-01-01"}'))["d"])                  # str
type(dict(read_json('{"d": "2024-01-01"}', schema=s))["d"])        # datetime.date

type(dict(read_yaml('d: 2024-01-01'))["d"])                        # datetime.date  (already!)
type(dict(read_yaml('d: 2024-01-01', schema=s))["d"])               # datetime.date

type(dict(read_toml('d = 2024-01-01'))["d"])                       # datetime.date  (already!)
type(dict(read_toml('d = 2024-01-01', schema=s))["d"])              # datetime.date

type(dict(read_xml('<d>2024-01-01</d>'))["d"])                     # str
type(dict(read_xml('<d>2024-01-01</d>', schema=s))["d"])            # datetime.date
```

## Why the conversion is unambiguous by construction

A schema's [field](glossary.md) declares exactly one [`Scalar`](glossary.md)
(or one `Ref`) — never a union, never an enum of candidate types. So when
deserialization looks at a raw leaf value and a field's declared scalar,
there's never a choice between *candidate representations* to disambiguate
between — only one question: **does this value exactly fit the one scalar
declared, or not.** That's why the conversion can run automatically with no
configuration and no heuristics.

Shape problems — a missing or unexpected field, the wrong cardinality, a
record where a scalar is expected — are left to `Schema.validate`, not
raised by deserialization. `materialize`/`schema=` only ever converts a leaf
it can already identify as belonging to a known field's scalar; it passes
mismatched shapes through unchanged for validation to flag.

## When a conversion isn't value-exact: `ParseError`

If a leaf's raw value doesn't exactly fit the declared scalar, deserialization
raises `ParseError` rather than guessing or silently leaving the value
unconverted:

```python
from omnist import parse_schema, read_json, ParseError

s = parse_schema('record R { "n": integer }\nroot R')
read_json('{"n": "abc"}', schema=s)
# ParseError: $.n: 'abc' cannot be read as integer (not a value-exact conversion)
```

`1.5` into `integer` fails the same way (`1.5` has a fractional part, so it's
not a value-exact `int`), while `4.0` into `integer` succeeds (`4.0` is
value-exact as `4`).

## Conversion rules

The table below is the full, per-kind mapping of what validation accepts
(checks a value already in the document, never converts) versus what
deserialization additionally converts (and rejects) for each `Scalar` kind.

| Scalar kind | Canonical Python type | What validation accepts | What deserialization additionally converts | What deserialization rejects |
|---|---|---|---|---|
| `string` | `str` | any `str` | nothing (no other type converts to `str`) | every non-`str` value |
| `integer` | `int` | any `int` that isn't a `bool` | a `float` with no fractional part (`x.is_integer()`), e.g. `4.0 → 4` | `bool` (even though `bool` is an `int` subclass in Python); a `float` with a fractional part (`4.5`); any `str` |
| `number` | `float` | an `int` or a `float`, neither a `bool` | an `int` is **always** upgraded to `float` (`3 → 3.0`) — see note below | `bool`; any `str` |
| `boolean` | `bool` | any `bool` | nothing (no string `"true"`/`"false"` parsing) | every non-`bool` value |
| `date` | `datetime.date` | a real `date` that is **not** a `datetime` (see note below); or an ISO-8601 date string (`"2024-01-01"`) | the ISO-8601 date string, to a real `date` | a real `datetime` value (even though `datetime` is a `date` subclass); a string that isn't a valid bare ISO date |
| `time` | `datetime.time` | a real `time`; or an ISO-8601 time string (`"12:00:00"`) | the ISO-8601 time string, to a real `time` | a string that isn't a valid ISO time |
| `datetime` | `datetime.datetime` | a real `datetime`; or a full ISO-8601 timestamp string that is **not** also a bare date string | the timestamp string, to a real `datetime` | a bare ISO date string (`"2024-01-01"` alone never satisfies `datetime`, only `date`); a string that isn't a valid full timestamp |

Notes:

- **`bool` never satisfies `integer` or `number`.** Python's `bool` is an
  `int` subclass, so `isinstance(True, int)` is `True` — but a schema's
  `integer`/`number` scalar explicitly excludes it. `true`/`false` only ever
  satisfy `boolean`.
- **`number` always deserializes to `float`, even from an integer literal.**
  A JSON/YAML/TOML value `3` read against a `"v": number` field materializes
  as the Python `float` `3.0`, not the `int` `3` — `number` means "the
  `float` representation," and `integer` (`int`) is the one scalar kind that
  is a subset of it.
- **`datetime` is a subclass of `date` in Python**, and
  `datetime.fromisoformat` will happily parse a bare date string into a
  `datetime` at midnight — both are explicitly excluded so `date` and
  `datetime` stay mutually exclusive for *both* the real-object form and the
  string form. A bare date string only ever satisfies `date`; a real
  `datetime.datetime(2024, 1, 1)` (even at midnight) only ever satisfies
  `datetime`, never `date`.
- **Shape mismatches are validation's job, not deserialization's.** If a
  value's *structure* doesn't match what's expected at all (a record where a
  scalar is expected, or vice versa) or a field is missing/unexpected,
  `materialize` passes the node through unchanged for `Schema.validate` to
  flag — it only ever converts a value it can identify as belonging to a
  known field's scalar.

See [model spec §10](design/model.md#10-scalar-and-python-type) for the
formal definition this table is derived from.

## `materialize`: upgrading an already-parsed node

`schema=` on a reader is sugar for parsing, then calling `materialize`
directly. Use `materialize` when you already have a node — from a reader
called without `schema=`, from `doc()`, or built by hand — and want the same
upgrade applied after the fact:

| | |
|---|---|
| `materialize(node, schema) -> node` | apply the schema-directed upgrade to an already-parsed node |

```python
from omnist import materialize, parse_schema, read_json

s = parse_schema('record R { "d": date }\nroot R')
node = read_json('{"d": "2024-01-01"}')          # no schema yet: 'd' is a str
materialize(node, s)                              # [('d', datetime.date(2024, 1, 1))]
```

See [the API reference](api.md#schema-directed-deserialization) for the bare
function signatures.
