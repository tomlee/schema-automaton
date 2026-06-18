# Documentation

`schema-automaton` is a Python library that models the **structure** of
hierarchical data — XML, JSON, YAML, TOML — with one canonical, schema-language
independent model, and computes on those schemas (equivalence, subschema /
compatibility testing, minimization, and subschema extraction).

It is a faithful implementation of, and an extension to:

> Thomas Y. Lee & David W. Cheung,
> *"XML Schema Computations: Schema Compatibility Testing and Subschema
> Extraction"*, CIKM 2010 — [`paper/`](paper/Lee-Cheung-2010-XML-Schema-Computations-CIKM.pdf).

## Contents

| Document | What it covers |
|----------|----------------|
| [Getting Started](getting-started.md) | Install, run the test suite, run the demos |
| [Data Model Specification](data-model.md) | Formal definitions: Data Tree, Schema Automaton, Content Model, Value Domain |
| [User Guide](user-guide.md) | Task-oriented how-to with runnable examples |
| [Schema DSL](schema-dsl.md) | The textual language for authoring/printing schemas |
| [Algorithms](algorithms.md) | The schema computations (incl. conformance) and complexity |
| [Design & Limitations](design-and-limitations.md) | Why it is format-agnostic; known limits and extensions |

## At a glance

```python
from src import tree_from_json, tree_from_python, infer_schema, to_json_schema

# 1. Infer a canonical schema from sample data
schema = infer_schema([
    tree_from_json('{"host": "a", "port": 80,  "tags": ["x"]}'),
    tree_from_json('{"host": "b", "port": 443, "tags": ["y", "z"], "tls": true}'),
])

# 2. Validate documents (from any format) with path-aware diagnostics
print(schema.validate(tree_from_python({"host": "h", "port": 22, "tags": ["s"]})))
# valid

print(schema.validate(tree_from_python({"host": "h", "tags": [1]})))
# invalid:
#   at $: missing required ['port']
#   at $.tags[]: value '1' (found VDom(INTS)) not in VDom(STRS)

# 3. Inspect it as a JSON-Schema-like view
import json; print(json.dumps(to_json_schema(schema), indent=2))
```

The same engine reproduces every worked example from the paper — see
[demos/01_xml_paper_examples.py](../demos/01_xml_paper_examples.py).
