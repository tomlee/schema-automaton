# Documentation

**dataspec** — one data model, many formats. Read JSON / YAML / TOML / XML into
plain Python data, validate it against a schema, and write it back out to any of
them.

## Start here

- **[Concepts](concepts.md)** — the whole mental model (Document + Schema) in one page.
- **[Usage](usage.md)** — task-oriented recipes with runnable examples.
- **[Schema DSL](schema-dsl.md)** — the text language for writing schemas.
- **[Formats](formats.md)** — what each format can represent; the lossless-or-error rule.

## At a glance

```python
from dataspec import read_json, write_toml, parse_schema, infer

data   = read_json('{"name": "Ann", "tags": ["x", "y"]}')
toml   = write_toml(data)                       # transcode JSON -> TOML

schema = parse_schema("root { name: string, tags: [string] }")
schema.validate(data).ok                        # True

schema2 = infer([data])                         # learn a schema from samples
```

## Background

The schema model is inspired by the formal Data Tree / Schema Automaton models
in Lee & Cheung, *"XML Schema Computations"* (CIKM 2010), included under
[`paper/`](paper/Lee-Cheung-2010-XML-Schema-Computations-CIKM.pdf). The library
deliberately trades the paper's academic vocabulary for a simple, practical
mental model: plain Python data, plain-language schemas, and ordinary functions.
