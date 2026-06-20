# JSON

JSON is the baseline format. It maps almost exactly onto the Document model, has
no external dependencies, and uses Python's standard `json` module under the
hood.

```python
from dataspec import read_json, write_json

read_json('{"name": "Ann", "tags": ["x", "y"]}')
# {'name': 'Ann', 'tags': ['x', 'y']}

write_json({"name": "Ann", "n": 1}, indent=2)
# {
#   "name": "Ann",
#   "n": 1
# }
```

## What's supported

- Objects, arrays, strings, integers, numbers, booleans, and `null` — the full
  Document model.
- Any value can be at the top level: an object, an array, or a bare scalar.
- `write_json` options: `indent` (pretty-print) and `sort_keys`.
- Malformed JSON raises `ParseError` on read.

## Limitations

- **No date types.** JSON has no notion of a date. On write, `date`, `time`, and
  `datetime` values are converted to ISO-8601 strings (reported as a
  `temporal.stringified` warning). On read they come back as strings — schemas
  with `date` / `time` / `datetime` accept those strings, so validation still
  works.
- **`NaN` / `Infinity`.** These aren't valid JSON; they're written as-is and
  reported as a `float.special` **error** (use `check_json`/`strict=True` to
  catch them).
- **Non-string keys** are coerced to strings (a `key.coerced` warning), matching
  the standard library. If two different keys coerce to the *same* string
  (`1` and `"1"`, say), one silently overwrites the other — that's a
  `key.collision` **error**, not just a warning.
- **Comments aren't allowed** by JSON at all.
- **Integers beyond JavaScript's safe-integer range** (`±2**53`,
  `Number.MAX_SAFE_INTEGER`) round-trip exactly through dataspec's own
  `read_json`/`write_json` (Python ints are arbitrary precision), but a
  JS-based JSON parser — a browser, Node.js — represents every number as an
  IEEE-754 double and would silently lose precision. Reported as
  `integer.precision_risk` (`warning`); `strict=True` rejects it. The same
  class of interop risk as TOML's signed-64-bit integer check.

## Round-trip behaviour

JSON preserves scalar types exactly: integers stay integers, floats stay floats,
and numeric-looking strings stay strings.

```python
d = read_json(write_json({"i": 1, "f": 1.0, "b": True, "s": "1"}))
# d == {'i': 1, 'f': 1.0, 'b': True, 's': '1'}  (types intact)
```

A date written to JSON and read back becomes a string, which is the one expected
asymmetry:

```python
import datetime
write_json({"d": datetime.date(2024, 1, 1)})   # '{"d": "2024-01-01"}'
```
