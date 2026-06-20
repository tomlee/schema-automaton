# TOML

TOML is designed for configuration files. It has first-class dates and is
strict about structure: the top level is always a table (an object). Reading
uses the standard-library `tomllib` (Python 3.11+); writing needs
`pip install tomli_w`.

```python
from dataspec import read_toml, write_toml

read_toml('name = "Ann"\n[address]\ncity = "London"\n')
# {'name': 'Ann', 'address': {'city': 'London'}}

print(write_toml({"name": "Ann", "tags": ["x", "y"]}))
# name = "Ann"
# tags = [
#     "x",
#     "y",
# ]
```

## What's supported

- Objects (tables), arrays, strings, integers, numbers, and booleans.
- **Native date types.** `date`, `time`, and `datetime` values round-trip as
  real temporal values, not strings — TOML's standout feature.

```python
import datetime, tomllib
out = write_toml({"created": datetime.datetime(2024, 1, 1, 12, 0)})
tomllib.loads(out)["created"]       # datetime.datetime(2024, 1, 1, 12, 0)
```

## Limitations

Conversion is lenient by default: each limitation below is *adjusted and
reported* rather than raised. Pass `report=` to see the adjustments, call
`check_toml(doc)` to inspect without writing, or pass `strict=True` to turn any
adjustment into a `WriteError`.

- **No `null`.** A `null` object field is **omitted** (`warning`); a `null` array
  item is **dropped** (`error` — it shifts positions); a top-level `null` becomes
  an empty document (`error`). `null_style="drop"` demotes the array case to a
  warning.

  ```python
  import tomllib
  from dataspec import write_toml, check_toml
  tomllib.loads(write_toml({"a": 1, "b": None}))   # {'a': 1}  -- b dropped
  tomllib.loads(write_toml({"xs": [1, None, 2]}))  # {'xs': [1, 2]}
  check_toml({"xs": [1, None, 2]}).errors          # [Adjustment(..., 'null.item.dropped', ...)]
  write_toml({"xs": [1, None, 2]}, strict=True)    # WriteError
  ```

- **The top level must be an object.** A bare array or scalar is wrapped under a
  key (`wrap_key`, default `"value"`):

  ```python
  write_toml([1, 2, 3])                       # 'value = [\n    1,\n    2,\n    3,\n]\n'
  write_toml([1, 2, 3], wrap_key="items")     # 'items = [\n    1,\n    2,\n    3,\n]\n'
  write_toml([1, 2, 3], strict=True)          # WriteError -- top-level array wrapped
  ```

- **Comments aren't preserved.** TOML allows comments, but they aren't part of
  the data model.

- **Integers are signed 64-bit** per the TOML spec. A Python `int` outside that
  range is written anyway — `tomli_w`/`tomllib` don't enforce the limit, so
  dataspec's own round-trip survives — but it's reported (`warning`) since a
  spec-compliant parser in another language may reject it:

  ```python
  from dataspec import check_toml, write_toml
  check_toml({"x": 2**63}).warnings   # [Adjustment(..., 'integer.out_of_range', ...)]
  write_toml({"x": 2**63}, strict=True)   # WriteError
  ```

## Round-trip behaviour

For any Document that TOML can represent, data and types are preserved exactly,
including dates. The lossy cases — dropped nulls, top-level wrapping, and
out-of-range integers — are exactly the adjustments the report lists, so
`check_toml(doc)` (or `write_toml(doc, strict=True)`) tells you up front
whether a given Document round-trips perfectly (and, for the integer case,
portably).
