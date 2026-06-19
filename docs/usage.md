# Usage

Task-oriented recipes. Every snippet is runnable; a combined tour is in
[`examples/quickstart.py`](../examples/quickstart.py).

```python
from dataspec import (
    read_json, read_yaml, read_toml, read_xml,
    write_json, write_yaml, write_toml, write_xml,
    parse_schema, infer, to_dsl,
)
```

## Read data from any format

```python
data = read_json('{"name": "Ann", "tags": ["x", "y"]}')
data = read_yaml("name: Ann\ntags: [x, y]\n")
data = read_toml('name = "Ann"\ntags = ["x", "y"]\n')
data = read_xml("<r><name>Ann</name><tags>x</tags><tags>y</tags></r>")
```

All four give you the same Python data: `{"name": "Ann", "tags": ["x", "y"]}`.

## Convert between formats (transcode)

```python
toml_text = write_toml(read_json(json_text))   # JSON -> TOML
json_text = write_json(read_yaml(yaml_text))    # YAML -> JSON
```

Type fidelity is preserved where the formats allow it — `30` stays a number,
`"30"` stays a string. See [Formats](formats.md) for the cross-format rules
(null handling, what each format can represent).

## Validate against a schema

```python
schema = parse_schema("""
    root {
        name: string,
        age?: integer,
        tags: [string],
    }
""")

schema.validate({"name": "Ann", "tags": ["x"]})         # valid
result = schema.validate({"name": 1, "extra": True})
result.ok            # False
print(result)
# invalid:
#   at $.name: expected string, got integer
#   at $: missing required field 'tags'
#   at $.extra: unexpected field
```

`schema.validate(doc)` returns a `ValidationResult` (`.ok` and `.errors`, a list
of `(path, message)`). `schema.accepts(doc)` is the boolean shorthand.

## Infer a schema from examples

```python
schema = infer([
    {"id": 1, "email": "a@x.io", "roles": ["admin"]},
    {"id": 2, "roles": []},                 # no email -> email becomes optional
])
print(to_dsl(schema))
# root { id: integer, email?: string, roles: [string] }
```

Inference is **sound**: the schema always accepts every sample it learned from.
Mixed scalar types become a union (`integer | string`); a value-or-`null`
becomes nullable; arrays generalise their length. Pass `infer(samples,
open_objects=True)` to allow extra keys.

## Check version compatibility

A new schema version is backward compatible when every old document still
validates:

```python
v1 = parse_schema("root { host: string, port: integer }")
v2 = parse_schema("root { host: string, port: integer, tls?: boolean }")

v1.compatible_with(v2)   # True  — adding an optional field is safe
v2.compatible_with(v1)   # False — v2 docs with 'tls' aren't valid under v1
```

`a.compatible_with(b)` means *every document `a` accepts is also accepted by
`b`*. `a.equivalent(b)` means they accept exactly the same documents.

## Build a schema in code (optional)

Most of the time the DSL or `infer` is enough, but the types are public:

```python
from dataspec import Schema, ObjectType, ArrayType, ScalarType, Field, STRING, INTEGER

schema = Schema(ObjectType({
    "name": Field(ScalarType({STRING}), required=True),
    "age":  Field(ScalarType({INTEGER}), required=False),
}))
```

## Round-trip and recursion

```python
# round-trip
data == read_json(write_json(data))

# recursive schema
tree = parse_schema("type Tree = { value: integer, kids: [Tree] }\nroot Tree")
tree.validate({"value": 1, "kids": [{"value": 2, "kids": []}]})   # valid
```
