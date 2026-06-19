# Schema DSL

A compact text language for writing schemas. `parse_schema(text)` turns it into
a `Schema`; `to_dsl(schema)` prints one back (so inferred schemas are readable
and round-trip).

```
type Line = { sku: string, qty: integer, price: number }
root {
    id:     string,
    status: "open" | "shipped" | "cancelled",
    lines:  [Line]+,
    note?:  string,
    when:   datetime,
}
```

## Scalars

```
string   integer   number   boolean   date   time   datetime   null
```

`integer` is whole numbers; `number` is any number (integers included).
`date` / `time` / `datetime` accept native temporal values and ISO-8601 strings
(so dates that arrive as JSON strings still validate).

## Objects

```
{ name: string, age?: integer }     # age? = optional field
{ id: integer, ... }                # ... = open (extra keys allowed)
{}                                  # empty object only
```

- `key: T` — a **required** field.
- `key?: T` — an **optional** field (may be absent).
- trailing `...` — **open** object (undeclared keys allowed).

## Arrays

```
[T]        # zero or more
[T]+       # one or more
[T]{3}     # exactly 3
[T]{2,5}   # 2 to 5
[T]{2,}    # 2 or more
[T]{,5}    # at most 5
```

## Nullable, unions, enums

```
string?              # string or null
integer | string     # a union of scalar types
"a" | "b" | "c"      # an enumeration of literal values
({ ... })?           # nullable object   (parenthesise unions before "?")
[integer]?           # nullable array
```

> **`note: string?` vs `note?: string`** — the `?` placement matters:
> `note: string?` is a **required** field whose value may be null;
> `note?: string` is an **optional** field that may be omitted.

## Named types & recursion

```
type Point = { x: number, y: number }
root { from: Point, to: Point }       # reuse

type Tree = { value: integer, kids: [Tree] }   # recursion
root Tree
```

Named types may be referenced before they are defined.

## Grammar

```ebnf
schema   = statement* ;
statement= "type" IDENT "=" type | "root" type ;
type     = union ;
union    = postfix ( "|" postfix )* ;
postfix  = atom "?"* ;                       (* "?" = nullable *)
atom     = scalar | STRING                   (* enum member *)
         | object | array | IDENT | "(" type ")" ;
scalar   = "string"|"integer"|"number"|"boolean"|"date"|"time"|"datetime"|"null" ;
object   = "{" ( field ("," field)* ("," "...")? ","? | "..." )? "}" ;
field    = (IDENT|STRING) "?"? ":" type ;
array    = "[" type "]" arity? ;
arity    = "+" | "*" | "{" INT? "," INT? "}" | "{" INT "}" ;
```

Comments start with `#` and run to end of line.
