# YAML

The JSON-compatible core of YAML. Needs `pip install pyyaml`.

```python
from omnist import read_yaml, Doc

d = Doc(read_yaml("""
name: Ann
tags: [x, y]
"""))
d.to_json()                      # '{"name": "Ann", "tags": ["x", "y"]}'
```

## How it maps

Identical to [JSON](json.md): a mapping becomes a list of edges, a key whose
value is a sequence expands into a repeated label, scalars are leaves. A YAML
document and the equivalent JSON document read into the **same** Document.

## Notes

- Only YAML's JSON-compatible core is supported (string keys, standard scalars,
  mappings and sequences). Tags, anchors-as-merge, and non-string keys are
  outside the profile.
- YAML carries dates and datetimes natively; a standalone time-of-day is read
  as written.
- Sequences of mappings (`- {…}`) are the idiomatic way to write an array of
  records, and map to a repeated label — see
  [the real-life example](../example.md).
- A label or string value containing U+0085 (NEL, "next line") is written
  double-quoted rather than plain/single-quoted, since YAML's line-break
  normalization would otherwise turn it into a plain space on read. This is
  reported as the `string.line-break-char` adjustment code (a warning, since
  it round-trips correctly — it's surfaced only so callers know the output
  style was forced for that value).
