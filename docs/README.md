# omnist documentation

Start here, in roughly this order:

| Doc | What it covers |
|---|---|
| **[User guide](guide.md)** | The practical tour — documents, the schema DSL and Python builder, validation, the schema operations, codecs, inference. Read this first. |
| **[A real-life example](example.md)** | One order schema validated against the *same* Document read from JSON, YAML, TOML, and XML, plus a backward-compatibility check. |
| **[API reference](api.md)** | Every public name: `Doc`, `Schema`, the builders, codecs, validation results, and exceptions, with signatures. |
| **[Formats](formats/overview.md)** | How each format maps to the model and its caveats — [OML](formats/oml.md) · [JSON](formats/json.md) · [YAML](formats/yaml.md) · [TOML](formats/toml.md) · [XML](formats/xml.md). |
| **[Model spec](design/model.md)** | The formal definitions of the Document and Schema models — self-contained, no paper required. |

## The model in one minute

- A **Document** is a *tree*: a node is either a scalar value or an **ordered
  list of labeled edges**. An array is just a label that repeats — so the same
  Document represents JSON, YAML, TOML, XML, and OML (omnist's own format).
- A **Schema** is named **`record`** definitions (closed named fields, each
  with a cardinality `[min,max]`), where each field's type is always exactly
  one fixed scalar (optionally nullable) or one `Ref` to a named record —
  referenced by name for reuse and recursion.
- **Validate** a Document against a schema, **compare** two schemas for
  backward-compatibility (`compatible_with`), or **infer** a schema from
  examples.
- Readers accept an optional `schema=` to upgrade leaves (ISO strings to real
  `date`/`time`/`datetime`, numeric types) to match the schema, when the
  conversion is value-exact.

```python
from omnist import parse_schema, doc

s = parse_schema('''
    record Member { "name": string, "role": string }
    record Team   { "name": string, "members" [1,]: Member }
    root Team
''')
s.validate(doc({"name": "X", "members": [{"name": "Ann", "role": "dev"}]})).ok   # True
```
