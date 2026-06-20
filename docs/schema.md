# Schemas

A **schema** describes the shape a Document is allowed to have. You write one in
a small text language, parse it with `parse_schema`, and call `validate` on a
[`Doc`](document.md):

```python
from dataspec import parse_schema, doc

schema = parse_schema("root { name: string, address: { city: string } }")
schema.validate(doc({"name": "Ann", "address": {"city": "London"}})).ok    # True
```

Validation isn't just a yes/no — a mismatch tells you exactly where and why:

```python
result = schema.validate(doc({"name": "Ann", "address": {"city": 42}}))
result.ok                       # False
result.errors[0].path           # '$.address.city'
result.errors[0].message        # 'expected string, got integer'
```

> Validation is **Doc-only** — wrap your data with `doc(...)` (or read it with
> `Doc.from_json(...)`) first. The examples below assume `doc` is imported.

You can also build the same schema in Python instead of as text — see
[The Python builder](#the-python-builder). This page defines every concept and
every type, with examples; for a complete, realistic schema combining them
all at once, with real documents and operations, see
[A worked example](example.md).

### DSL or builder?

Both produce the identical `Schema` object — pick whichever fits the moment:

- **DSL text** reads like the data it describes, is easy to save to a file or
  show a teammate, and is what `to_dsl()` prints back (handy for an inferred
  schema). Prefer it for schemas you write by hand.
- **The builder** is plain Python — composable, IDE/type-checker-friendly, and
  the natural choice when a schema is generated, assembled from reusable
  pieces, or built up conditionally in code.

### Quick reference

| Concept | DSL | Builder |
|---|---|---|
| scalar | `string`, `integer`, `number`, `boolean`, `date`, `time`, `datetime` | `t.string`, `t.integer`, … |
| anything | `any` | `t.any` |
| nullable | `T?` | `nullable(T)` |
| union | `integer \| string` | `ScalarType({INTEGER, STRING})` |
| enum | `"a" \| "b"` | `enum("a", "b")` |
| kind + enum | `integer \| "unknown"` | `ScalarType({INTEGER}, enum={"unknown"})` |
| array | `[T]`, `[T]+`, `[T]{2,5}` | `arr(T)`, `arr(T, min=1)`, `arr(T, 2, 5)` |
| object (closed) | `{ a: T }` | `obj(a=T)` |
| optional field | `a?: T` | `obj(a=optional(T))` |
| open object | `{ a: T, ... }` | `ObjectType({...}, rest=AnyType())` |
| map | `{ [string]: T }` | `mapping(T)` |
| named type | `type Name = T` ... `Name` | `schema(root, Name=T)` ... `ref("Name")` |

See [The schema text](#the-schema-text) and [The Python builder](#the-python-builder)
below for the full explanation of each.

## Concepts

A schema is built from the same three kinds of values as a Document — scalar,
array, object — plus nullability and named types layered on top. See
[Concepts](concepts.md#document) for the full definitions; in short:

- a **scalar** type matches one indivisible value (text, number, boolean, date/time);
- an **array** type matches a homogeneous, ordered list;
- an **object** type matches a set of named fields (or, as a **map**, arbitrary
  keys sharing one value type — see [Maps](#maps));
- any type can be made **nullable** with `?`;
- a **named type** is defined once and reused by name, which is how recursive
  shapes like trees are described.

## The schema text

A schema is one `root` declaration plus any number of named types:

```
type Address = { street: string, city: string }

root {
    name:    string,
    address: Address,
}
```

- `root T` declares the type of the whole document. Exactly one is required.
- `type Name = T` defines a named type. Order doesn't matter — you can refer to
  a type before it's defined.
- `#` starts a comment that runs to the end of the line.

## Scalar types

| Keyword | Matches |
|---------|---------|
| `string` | text |
| `integer` | whole numbers (not booleans) |
| `number` | integers or floats (not booleans) |
| `boolean` | `true` / `false` |
| `date` | a calendar date |
| `time` | a time of day |
| `datetime` | a date and time |

```python
parse_schema("root string").validate(doc("hi")).ok       # True
parse_schema("root integer").validate(doc(5)).ok          # True
parse_schema("root integer").validate(doc(5.5)).ok        # False (not whole)
```

A few deliberate rules:

- **`integer` is a `number`, but not vice versa.** `5` satisfies both;
  `5.5` satisfies only `number`.
- **Booleans are never numbers.** In Python `True == 1`, but a schema treats
  `boolean` and `integer`/`number` as distinct so you don't accidentally accept
  `true` where you wanted a count.
- **Dates may arrive as text.** JSON and XML have no date type, so a date is
  usually a string like `"2024-01-01"`. The `date`, `time`, and `datetime` types
  accept both real `datetime` objects and ISO-8601 strings, so the same schema
  validates data whether it came from TOML (native dates) or JSON (ISO strings).

## Enums and unions

A **union** lists alternatives with `|`. For scalars this widens what's allowed:

```
root integer | string        # an integer OR a string
```

An **enum** is a union of specific string values — the data must be exactly one
of them:

```
root "open" | "shipped" | "cancelled"
```

A kind and an enum can be unioned together — the data must be either, not just
the enum values:

```
root integer | "unknown"     # any integer, or specifically the string "unknown"
```

```python
s = parse_schema('root integer | "unknown"')
s.validate(doc(7)).ok               # True — matches the integer kind
s.validate(doc("unknown")).ok       # True — matches the literal
s.validate(doc("other")).ok         # False — neither
```

> Unions are for scalars and enums. You can't union two different *structures*
> (say, two different object shapes) — see [Limitations](#limitations).

## Nullable types

Add `?` to allow `null` as well. It works on any type:

```
root string?                      # a string or null
root { user: { name: string }? }  # the user object may be null
root [integer]?                   # the whole array may be null
```

`string?` and `string | null` mean the same thing.

## Arrays

`[T]` is an array whose every item has type `T`. You can also constrain the
length:

| Syntax | Meaning |
|--------|---------|
| `[T]` | zero or more |
| `[T]+` | one or more |
| `[T]{n}` | exactly `n` |
| `[T]{m,n}` | between `m` and `n` |
| `[T]{m,}` | at least `m` |
| `[T]{,n}` | at most `n` |

```
root {
    tags:   [string],          # any number of strings
    scores: [number]+,         # at least one
    coords: [number]{2},       # exactly two (e.g. [lon, lat])
}
```

Arrays are **homogeneous**: all items share one type. To allow mixed scalars,
use a union as the item type — `[integer | string]`.

## Objects

An object lists its fields. A field is **required** by default; add `?` to the
*name* to make it optional:

```
root {
    name:  string,      # required
    age?:  integer,     # optional
}
```

By default an object is **closed** — unexpected keys are an error. End the field
list with `...` to make it **open**, allowing extra keys with any value:

```
root { id: string, ... }     # id is checked; any other keys are allowed
```

```python
s = parse_schema("root { a: integer }")
s.validate(doc({"a": 1, "b": 2})).ok          # False — 'b' is unexpected

s = parse_schema("root { a: integer, ... }")
s.validate(doc({"a": 1, "b": 2})).ok          # True
```

## Maps

Often an object is used as a **map**: the keys aren't known ahead of time, but
every value has the same type — like `{"2024-01": 5, "2024-02": 8}`. Write that
with an index signature, `[string]: T`:

```
root { [string]: integer }          # any string keys -> integer values
```

```python
s = parse_schema("root { [string]: integer }")
s.validate(doc({"jan": 1, "feb": 2})).ok      # True
s.validate(doc({"jan": "x"})).ok              # False — values must be integers
```

You can combine known fields with a map for the rest:

```
root {
    version: integer,           # a known field
    [string]: number,           # every other key maps to a number
}
```

The value type can be anything, including objects and arrays:

```
root { [string]: { lat: number, lon: number } }    # a map of points
```

## The `any` type

`any` matches any Document at all, including `null`. Use it for a field whose
contents you don't want to constrain:

```
root { id: string, payload: any }
```

Use it sparingly — `any` turns off checking for that position. (An open object,
`{ ... }`, is just an object whose extra values are `any`.)

## Named and recursive types

Define a type once and reuse it; a type may refer to itself, which is how you
describe trees:

```
type Tree = {
    value: integer,
    kids:  [Tree],
}
root Tree
```

```python
s = parse_schema("type Tree = { value: integer, kids: [Tree] }\nroot Tree")
s.validate(doc({"value": 1, "kids": [{"value": 2, "kids": []}]})).ok   # True
```

A reference to an undefined type is caught when you parse the schema:

```python
parse_schema("root { a: Missing }")      # raises SchemaError: unknown type 'Missing'
```

For a complete, realistic schema combining several of the above at once —
two named types, an enum, a required array with a minimum length, an
optional field, and a map — built both as DSL text and via the builder, with
documents from every format (some accepted, some rejected) and the
`compatible_with`/`normalize` operations used against it, see
[A worked example](example.md).

## Validation results

`validate` returns a `ValidationResult`:

- `result.ok` — `True` if the document fits.
- `bool(result)` — same as `.ok`, so `if result:` works.
- `result.errors` — a list of failures. Each is an `Error` with `.path` (a
  location like `$.items[0].id`) and `.message`. It also unpacks as
  `(path, message)`.
- `print(result)` — a readable multi-line summary.

```python
r = parse_schema("root { items: [{ id: integer }] }").validate(doc({"items": [{"id": "x"}]}))
r.errors[0].path        # '$.items[0].id'
r.errors[0].message     # 'expected integer, got string'
```

## Round-tripping a schema to text

`schema.to_dsl()` (or `to_dsl(schema)`) prints a schema back as DSL text — handy
for showing an inferred schema or saving one to a file. Parsing that text gives
back an equivalent schema.

## The Python builder

You don't have to use the text language. The builder constructs the *same* schema
object tree from Python expressions — handy when a schema is generated or
composed, where string concatenation would be awkward, and friendlier to IDEs and
type checkers.

The scalar **type atoms** live under the `t` namespace — `t.string`, `t.date`,
`t.any`, etc. — so they never shadow Python's `any` or the stdlib `datetime` /
`date` / `time` modules. The builder *functions* (`obj`, `arr`, …) are top-level.

```python
from dataspec import schema, obj, arr, mapping, enum, optional, nullable, ref, t

s = schema(obj(
    name    = t.string,
    age     = optional(t.integer),             # an optional field
    status  = enum("open", "shipped"),         # a fixed set of values
    tags    = arr(t.string),                    # an array
    deleted = nullable(t.boolean),              # also accepts null
    scores  = mapping(t.integer),               # a map { [string]: integer }
))
```

The vocabulary (where `T` stands for any type):

| Builder | Produces | DSL equivalent |
|---|---|---|
| `t.string`, `t.integer`, `t.number`, `t.boolean`, `t.date`, `t.time`, `t.datetime` | a scalar type | the same keywords |
| `t.any` | matches anything | `any` |
| `obj(**fields)` | a closed object | `{ ... }` |
| `optional(T)` | marks a field not-required | `name?: T` |
| `nullable(T)` | a type that also accepts null | `T?` |
| `arr(item, min=, max=)` | an array (optionally bounded) | `[item]{min,max}` |
| `mapping(T)` | a map of string keys to `T` | `{ [string]: T }` |
| `enum(*values)` | a fixed set of literals | `"a" \| "b"` |
| `ref(name)` | a named-type reference | `Name` |
| `schema(root, **named)` | assembles a `Schema` | `root … type Name = …` |

A few constructs have no dedicated builder function and need the `Type`
classes directly (`from dataspec.schema import ScalarType, ObjectType,
AnyType, INTEGER, STRING`):

- **A scalar union** — `ScalarType({INTEGER, STRING})` (same as `integer | string`).
- **A kind unioned with an enum** — `ScalarType({INTEGER}, enum={"unknown"})`
  (same as `integer | "unknown"`).
- **An open object with named fields** — `obj()` alone only builds a *closed*
  object, so for `{ a: T, ... }` build the closed form first and swap in an
  `AnyType` rest: `ObjectType(obj(a=T).fields, rest=AnyType())`.

Named types and recursion work by passing named types to `schema(...)` and
referring to them with `ref`:

```python
node = obj(value=t.integer, kids=arr(ref("Node")))
s = schema(ref("Node"), Node=node)             # type Node = { value, kids: [Node] }
```

The builder produces ordinary `ObjectType` / `ScalarType` / … objects, which you
can also navigate with uniform getters: `obj_type.field("name")`,
`obj_type.children()`, `array_type.item`, `object_type.rest`. See the
[API reference](api.md#schema-builder).

## Limitations

- **No structural unions.** You can union scalars (`integer | string`) and enum
  values, but not two different object or array shapes. If you need
  "either this object or that one," model it as one open or `any`-valued object,
  or validate the variants separately.
- **Arrays are homogeneous.** There's no fixed-length, mixed-type tuple such as
  `[string, integer, boolean]`. Use a union item type for mixed scalars, or an
  object with named fields when each position has a distinct meaning.
- **Map keys are always strings.** That matches JSON/YAML/TOML/XML, where object
  keys are strings.
- **DSL text nesting is capped at 100 levels.** A schema that deeply nested
  (`[[[...string...]]]` or similar) would risk an uncatchable
  `RecursionError` in the parser; past the limit, `parse_schema` raises a
  clean `SchemaError` instead. Ordinary schemas are nowhere near this —
  it exists for malformed or adversarial input, not as a practical
  authoring constraint.

## See also

- [Inferring schemas](infer.md) — draft a schema from example Documents instead
  of writing one by hand.
- [API reference](api.md#schemas) — the full `Schema`, `ValidationResult`, and
  type-class reference.
