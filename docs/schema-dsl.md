# Schema DSL

A compact, readable textual language for **authoring** the schema model by hand,
and for **printing** an inferred schema. `parse_schema(text)` turns DSL text into
a `SchemaAutomaton`; `schema_to_dsl(sa)` renders one back to text.

```python
from src import parse_schema, schema_to_dsl, conforms_to, tree_from_python

sa = parse_schema("""
    type Line = { sku: string, qty: int, price: number }
    root {
        id:     string,
        status: "open" | "shipped" | "cancelled",
        lines:  [Line]+,
        note?:  string,
    }
""")

sa.accepts(tree_from_python({"id": "PO-1", "status": "open",
                             "lines": [{"sku": "A", "qty": 2, "price": 9.99}]}))  # True
```

---

## 1. Grammar

```ebnf
program   = statement* ;
statement = "type" IDENT "=" type      (* a named, reusable / recursive type *)
          | "root" type ;              (* the document's top-level type       *)
type      = union ;
union     = postfix ( "|" postfix )* ; (* alternatives                        *)
postfix   = atom "?"* ;                (* "?" = nullable  (T | null)          *)
atom      = "string" | "int" | "number" | "bool" | "null"
          | STRING                     (* enum member, e.g. "active"          *)
          | "{" fields? "}"            (* object (unordered map)              *)
          | "[" type? "]" "+"?         (* array; "+" non-empty; "[]" empty    *)
          | "(" type ")"               (* grouping                            *)
          | IDENT ;                    (* reference to a named type           *)
fields    = ( field ( "," field )* ( "," "..." )? | "..." ) ","? ;
field     = IDENT "?"? ":" type ;      (* "?" after the name = optional field *)
```

Comments start with `#` and run to end of line. There must be exactly one
`root`.

---

## 2. Types

### Scalars

| DSL | Value domain | Accepts |
|-----|--------------|---------|
| `string` | `STRS` | any string |
| `int` | `INTS` | integers |
| `number` | `DECS` | integers and floats |
| `bool` | `BOOL` | `true` / `false` |
| `null` | — | the null value only |

### Enumerations

A union of string literals is an enumeration:

```
root "red" | "green" | "blue"
```

### Unions

A union of scalar kinds admits any of them:

```
root int | string          # integer or string
```

Unions of **unlike structural** types (`{…} | […]`, `{…} | string`) are *not*
representable by one automaton state and raise `SchemaSyntaxError`. The
exception is nullability — see below.

### Nullable — `?`

`T?` means *`T` or null*:

```
string?                    # string or null
{ name: string }?          # object or null
[int]?                     # array or null
( "a" | "b" )?             # enum or null   (parenthesise unions before ?)
```

### Objects

Unordered maps with unique keys:

```
{ name: string, age?: int }
```

* `name: string` — a **required** field.
* `age?: int` — an **optional** field (the `?` is after the *name*).
* A trailing `...` makes the object **open** (extra, undeclared keys allowed,
  with unconstrained values): `{ id: int, ... }`.
* `{}` is the empty (closed) object; `{ ... }` is any object.

> **`note: string?` vs `note?: string`** — placement of `?` matters:
> `note: string?` is a **required** field whose value may be null;
> `note?: string` is an **optional** field that may be omitted entirely.

### Arrays

```
[string]     # zero or more strings   (item*)
[int]+       # one or more integers   (item+)
[]           # the empty array only
```

### Named types, reuse, and recursion

```
type Point = { x: number, y: number }
root { from: Point, to: Point }      # Point reused

type Tree = { value: int, kids: [Tree] }   # recursion
root Tree
```

Named types may be referenced before they are defined (forward references), and
a type may reference itself (recursion).

---

## 3. Checking conformance

`conforms_to(sa, tree)` is the conformance algorithm (the paper's Definition 3).
It returns a `ConformanceResult` with:

* `.ok` — whether the tree conforms (also truthy/falsy directly),
* `.binding` — the **binding map** `Bind : N → Q`, mapping each conforming
  d-node id to the state that accepts it,
* `.errors` — `(path, message)` pairs for every violation.

```python
from src import conforms_to, tree_from_python

r = conforms_to(sa, tree_from_python({"id": "PO-2", "status": "pending",
                                       "lines": []}))
print(r)
# does not conform:
#   at $.status: value 'pending' (found VDom(STRS)) not in VDom({cancelled, open, shipped})
#   at $.lines: array must be non-empty (expected at least one item)
```

`sa.accepts(tree)` is the boolean shorthand; `sa.validate(tree)` returns the same
diagnostics without the binding map. All three agree on the verdict.

---

## 4. Round-tripping

`schema_to_dsl(sa)` renders any Schema Automaton back to DSL text. Shared and
recursive structural types are emitted as named `type` declarations; everything
else is inlined. The round-trip preserves the language:

```python
text = schema_to_dsl(sa)
assert equivalent_sa(sa, parse_schema(text))
```

This also lets you **print an inferred schema** as readable DSL:

```python
from src import infer_schema, tree_from_json, schema_to_dsl

schema = infer_schema([tree_from_json('{"host":"a","port":80,"tls":true}'),
                       tree_from_json('{"host":"b","port":443}')])
print(schema_to_dsl(schema))
# root { host: string, port: int, tls?: bool }
```

---

## 5. Scope

The DSL targets the data-format-agnostic model (objects, arrays, scalars,
unions, nullable, enums, named types, recursion, open objects) — i.e. everything
JSON / YAML / TOML schemas need, and everything `infer_schema` produces.
Arbitrary *ordered* XML element-sequence content models (regex over element
names, e.g. `Desc Price`) are expressible through the Python API
(`HLang.parse`) but are intentionally outside the DSL surface. See
[Design & Limitations](design-and-limitations.md).
