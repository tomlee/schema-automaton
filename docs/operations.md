# Comparing schemas

When a schema is versioned — an API payload, a config format — you need to know
whether a change is safe. dataspec answers two questions directly.

> For these operations used against one realistic, multi-format schema rather
> than the toy schemas below, see [A worked example](example.md#using-compatible_with-is-a-schema-change-backward-compatible).

## `compatible_with` — is a change backward-compatible?

`a.compatible_with(b)` is `True` when **every document that `a` accepts is also
accepted by `b`**. Read it as "`a` is at least as strict as `b`," or "data valid
under `a` stays valid under `b`."

The common use is checking that a new schema version still accepts old data.
Make `a` the old schema and `b` the new one:

```python
from dataspec import parse_schema

v1 = parse_schema("root { host: string, port: integer }")
v2 = parse_schema("root { host: string, port: integer, tls?: boolean }")

v1.compatible_with(v2)      # True  — adding an optional field is safe
v2.compatible_with(v1)      # False — a v2 doc with `tls` is invalid under v1
```

Changes that keep `old.compatible_with(new)` true include:

- adding an **optional** field;
- making a required field optional;
- **widening** a scalar (`integer` → `integer | string`, `integer` → `number`);
- **loosening** array length bounds (`{2,3}` → `{1,5}`);
- widening a map's value type (`{ [string]: integer }` → `{ [string]: number }`);
- relaxing anything to `any`.

```python
narrow = parse_schema("root { v: integer }")
wide   = parse_schema("root { v: integer | string }")
narrow.compatible_with(wide)    # True
wide.compatible_with(narrow)    # False
```

## `equivalent` — do two schemas accept the same documents?

`a.equivalent(b)` is `True` when each accepts exactly what the other does. It's
`a.compatible_with(b) and b.compatible_with(a)`, and it ignores cosmetic
differences like field order or how named types are split up:

```python
a = parse_schema("root { a: integer, b: string }")
b = parse_schema("root { b: string, a: integer }")
a.equivalent(b)             # True
```

## `normalize` — a canonical form

`schema.normalize()` returns an equivalent schema with structurally-identical
named types merged into one. It's useful before printing or comparing schemas
that were assembled from overlapping definitions:

```python
s = parse_schema("""
    type A = { x: integer }
    type B = { x: integer }
    root { a: A, b: B }
""")
n = s.normalize()           # A and B collapse to a single named type
len(n.types)                # 1
s.equivalent(n)             # True
```

## Notes

These checks are **structural**: they compare the shapes the schemas describe,
not sample data. Recursive (self-referencing) types are handled correctly. The
comparison is conservative — it reports compatible only when it can show every
document carries over.
