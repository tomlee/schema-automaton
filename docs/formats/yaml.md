# YAML

The JSON-compatible core of YAML. Needs `pip install pyyaml`.

```python
from dataspec import read_yaml, Doc

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
