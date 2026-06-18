# Design & Limitations

## Why a Content Model abstraction?

The paper models the permissible children of a node with a *horizontal language*
(HLang) — a regular language over the **ordered** sequence of child-edge
symbols. That is exactly right for XML, where element order is significant. But
the other popular data formats are not all ordered:

| Format construct | Order significant? | Unique labels? |
|------------------|--------------------|----------------|
| XML element sequence | yes | no |
| JSON array / YAML sequence | yes | n/a (positional) |
| JSON object / TOML table / YAML map | **no** | **yes (keys)** |

Forcing object validation through an ordered regular language would be both
awkward (which key order do you encode?) and wrong (it would reject valid
re-orderings). So the per-state child constraint is abstracted into a
`ContentModel` interface with three implementations — ordered `HLang`, unordered
`MapModel`, leaf `ScalarModel` — sharing one interface
(`accepts`, `is_subset_of`, `canonical_key`, `mandatory_symbols`,
`remove_symbol`, `is_empty`). The five schema algorithms are written purely
against that interface, so they work identically for XML and JSON/TOML/YAML.

This is the key extension over the paper, which only addresses XML/XSD.

## Value domains: a set of kinds, typed throughout

A value domain admits a **set** of scalar kinds (e.g. `integer | string`), plus
optional nullability and an optional enumeration. This is what lets schema
inference represent a field that varies across samples *without* silently
rejecting some of its own input.

Two relations operate on value domains, and both use **data-format (typed)
semantics**, so they agree with each other:

* `VDom.admits(value_type)` — can a value of this *type* appear in the domain?
  Used when validating a typed node. `1` is rejected where a string is expected;
  an integer is accepted where a *number* is expected (numeric widening).
* `VDom.is_subset_of(other)` — domain-vs-domain inclusion, used for
  **schema-vs-schema** subschema testing. Typed, so `INTS ⊆ DECS` but
  `INTS ⊄ STRS`. This keeps `subschema_sa` consistent with `validate`.

For *untyped* data (hand-built XML trees whose nodes carry no `vdom` hint),
validation falls back to string-based `VDom.contains`, where `STRS` matches any
string — faithful to the paper's XML/XSD value model.

---

## What inference *can* now express

Several cases that earlier raised `ValueError` are now first-class:

* **Scalar unions** — a position that is `integer | string` across samples
  becomes a union value domain that admits both (and exports as
  `"type": ["integer", "string"]`). Numeric mixes widen: `integer + float` →
  `number`. *This also fixed a soundness bug* where a generalised domain could
  reject some of its own training data.
* **Nullable scalars** — `string | null` via a nullable value domain.
* **Nullable objects / arrays** — `object | null` and `array | null` via
  per-state structural nullability. The non-null form is still fully type-checked
  (e.g. an object's fields keep their types).
* **Open objects** — `infer_schema(samples, open_maps=True)` produces maps that
  tolerate undeclared keys (`additionalProperties: true`); undeclared keys carry
  no type constraint.

The guiding invariant, exercised by a property test over hundreds of random
shapes: **an inferred schema always accepts every sample it was inferred from.**

## Known limitations

These are honest boundaries of the current model, each chosen to fail loudly
rather than silently produce a wrong schema.

### 1. Genuine non-null structural unions

A single SA state carries one content model and one value domain, so it still
cannot express a *non-null* union of unlike shapes — `object | string`,
`array | object`, `array | string`. Inference **raises `ValueError`** for these
rather than guessing. (Nullable variants — `object | null`, `array | null`,
`scalar | null` — *are* supported, as above.)

*Possible extension:* explicit union states that delegate to several alternative
(content model, value domain) branches, discriminated by structural kind.

### 2. Arrays observed only empty

If every sample array at a position is empty, no element type can be inferred, so
the position infers to **empty-sequence-only** and a later non-empty array is
rejected. This keeps the automaton consistent (Definition 2) and predictable; it
is conservative by design.

### 3. Open-map inference is all-or-nothing

`open_maps=True` makes **every** inferred object open; the model supports
per-object openness (`MapModel(fields, open=True)`) but inference applies one
policy uniformly, since "this particular object allows extra keys" cannot be
concluded from a finite sample.

### 4. XSD feature coverage

Following the paper, the Schema Automaton models the commonly-used core of XSD
(complex/simple types, element sequences, occurrence constraints, built-in
scalar types). It does **not** model open-content wildcards such as `xs:any`,
attribute-vs-element distinctions, namespaces, or identity constraints
(key/keyref). These are noted as extensions in §8 of the paper.

### 5. Performance of regular-expression tests

Equivalence and inclusion of ordered content languages are decided **exactly**
via DFA operations, which are PSPACE-complete in the worst case. For very large
ordered schemas, the paper's filtering heuristics (literal-equality short-circuit
and a PTIME weak test for simple expressions, §6) would be a worthwhile addition;
they are not yet implemented here. Unordered `MapModel` comparisons are linear.

---

## Project layout

```
src/
  nfa.py              NFA/DFA engine (Thompson, subset construction, Hopcroft)
  content_model.py    ContentModel ABC + MapModel + ScalarModel
  hlang.py            HLang — the ordered (sequence) content model
  vdom.py             value domains (STRS/INTS/DECS/BOOL/NULL/enum/nullable)
  data_tree.py        Data Tree (Definition 1)
  schema_automaton.py Schema Automaton (Definition 2) + validation (Definition 3)
  algorithms.py       Algorithms 1–5 + conforms_to (Definition 3)
  formats.py          JSON/YAML/TOML loaders + schema inference
  export.py           Schema Automaton → JSON-Schema-like dict
  schema_dsl.py       textual Schema DSL: parse_schema / schema_to_dsl
tests/
  test_paper.py       reproduces the CIKM 2010 examples
  test_formats.py     map model, loaders, inference, validation, export
  test_dsl.py         DSL parse/serialize/round-trip + conformance algorithm
demos/                seven runnable, self-contained demos
docs/                 this documentation + the source paper (docs/paper/)
main.py               quick combined tour
```

## Relationship to the paper

This implementation reproduces the paper's worked examples (SA1/SA2/SA3
equivalence, subschema testing, and subschema extraction) in
`tests/test_paper.py` and `demos/01_xml_paper_examples.py`, and extends the
models with the format-agnostic Content Model, typed value domains, schema
inference, path-aware validation, and JSON-Schema export. The source paper is
included at
[`paper/Lee-Cheung-2010-XML-Schema-Computations-CIKM.pdf`](paper/Lee-Cheung-2010-XML-Schema-Computations-CIKM.pdf).
