# Concepts

The whole mental model in one paragraph:

> You work with **Documents** — plain Python data: objects, arrays, and scalars,
> just like JSON. A **Schema** describes the shape a Document should have. You
> **read** a format into a Document, **validate** it against a Schema, and
> **write** it back out to any format. JSON, YAML, TOML, and a simple XML are
> interchangeable because they all map to the same Document — and if a Document
> can't be represented in a target format, you get a clear error instead of
> silent corruption.

That's it. No special node types, no parser objects, no theory.

## Document

A **Document** is ordinary Python data:

| In a Document | Python |
|---|---|
| object | `dict` (string keys) |
| array | `list` |
| string | `str` |
| integer | `int` |
| number | `int` or `float` |
| boolean | `bool` |
| null | `None` |
| date / time / datetime | `datetime.date` / `.time` / `.datetime` |

`read_json("...")` gives you a `dict`/`list`/scalar. You can build one by hand,
or get one from any reader. There is nothing to learn.

## Schema

A **Schema** describes the allowed shape. It is built from three kinds of
**types** that mirror the data:

- **object** — named fields, each *required* or *optional*; *open* or *closed*.
- **array** — an item type plus a count (e.g. 0+, 1+, exactly 3, 2–5).
- **scalar** — `string`, `integer`, `number`, `boolean`, `date`, `time`,
  `datetime`; optionally **nullable**, an **enum**, or a **union** (`integer | string`).

You usually write schemas in the [DSL](schema-dsl.md):

```
root {
    name:   string,
    age?:   integer,            # optional field
    tags:   [string]{1,},       # one or more strings
    role:   "admin" | "user",   # enum
    note:   string?,            # nullable value
}
```

…or **infer** one from example Documents.

Named types make schemas reusable and recursive:

```
type Tree = { value: integer, kids: [Tree] }
root Tree
```

## The four things you do

| You want to… | Call |
|---|---|
| read a format into a Document | `read_json` / `read_yaml` / `read_toml` / `read_xml` |
| write a Document to a format | `write_json` / `write_yaml` / `write_toml` / `write_xml` |
| check a Document against a Schema | `schema.validate(doc)` → ok + path-aware errors |
| learn a Schema from examples | `infer(docs)` |

And on a Schema you can also: `to_dsl()`, `equivalent(other)`,
`compatible_with(other)` (for versioning), and `normalize()`.

## Why one model for four formats

JSON, YAML, TOML, and (data-)XML are all ways to *write down a tree of objects,
arrays, and scalars*. They differ only at the edges — TOML and XML have no
`null`; XML has no native types. So the Document is the shared core, each format
is a codec over it, and the differences are handled explicitly (see
[Formats](formats.md)): a conversion either preserves your data or fails with a
clear message — it never silently mangles it.

That principle — **lossless, or a clear error** — is what makes transcoding
between formats trustworthy.
