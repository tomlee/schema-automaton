# JSON

The baseline format — no dependencies (uses the standard-library `json`).

```python
from omnist import read_json, write_json, Doc

d = Doc.from_json('{"name": "Ann", "tags": ["x", "y"]}')
d.to_json()                      # '{"name": "Ann", "tags": ["x", "y"]}'
```

## How it maps

- A JSON object becomes a list of edges.
- A key whose value is an array expands into **one edge per item** (a repeated
  label): `{"tags": ["x", "y"]}` → `[(tags, "x"), (tags, "y")]`.
- A nested object becomes a nested node; scalars are leaves.

## Writing back

`write_json` groups same-label edges back into a JSON array. A label seen more
than once becomes a list; a label seen exactly once stays a single value.

```python
write_json([("tag", "x"), ("tag", "y")])     # '{"tag": ["x", "y"]}'
write_json([("tag", "x")])                    # '{"tag": "x"}'
```

> **The count-1 rule.** A *single-element* array can't be told apart from a
> single value — both are one edge — so it always serializes as a bare value;
> a label seen more than once always serializes as a list. `write_json` (like
> the other writers) takes no schema, so there's currently no way to force a
> single-element array field to write as a list. See
> [model spec §9](../design/model.md#9-resolved-decisions).

## Notes

- JSON has no date type; dates written from a Document go out as ISO-8601
  strings (reported as `temporal.stringified`), and the `date` / `time` /
  `datetime` scalars accept those strings on the way back in — `date`,
  `time`, and `datetime` are mutually exclusive even for strings, so
  `"2024-01-01"` satisfies only `date`, not `datetime` (it has no time
  component to satisfy it with).
- JSON has no `NaN`/`Infinity`; writing one is reported as `float.special`, an
  error-severity adjustment. See
  [adjustment reports](../api.md#adjustment-reports-lossy-writes).
- A bare top-level array (`[1, 2, 3]`) has no labels, so it isn't a Document on
  its own — wrap it under a key.
