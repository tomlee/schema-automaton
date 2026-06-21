# Design: Canonical Document & Schema Model

**Status:** Draft / proposal — for review, not yet implemented
**Date:** 2026-06-21
**Supersedes:** the current `Doc` (dict/list/scalar) and `Type` tree (`ObjectType`/`ArrayType`/`ScalarType`/`RefType`/`AnyType`)

---

## 1. Summary

This proposes a redesign of dataspec's two core models — the **Document** (the data) and the **Schema** (the constraint) — so that both are faithful to the Data Tree / Schema Automaton (SA) formalism dataspec already cites (Lee & Cheung, CIKM 2010), simplified deliberately for the JSON-family of formats.

The headline changes:

1. A **Document is an ordered list of labeled edges** (a Data Tree), not a map whose values may be arrays.
2. A **Schema has exactly two state kinds** — `record` (constrained by child labels) and `union` (constrained by values) — plus `Ref` for naming/recursion.
3. **Field cardinality `[min,max]`** is the single mechanism for optional / required / array. There is no separate array type.
4. The model is **restrictive by default**: records are closed, and the structureless escape hatches (`Any`, open objects, maps) are removed.

This is a breaking redesign of the core; §9 covers impact.

---

## 2. Motivation

The current model accreted three problems, each surfaced while reconciling it against the SA formalism:

- **The Document can't faithfully represent all inputs.** XML may interleave repeated elements (`<member/><other/><member/>`); a dict-with-array-values (`{"member": […], "other": …}`) has already reordered reality and cannot express the interleaving. The Document is supposed to be *canonical regardless of format*, but it is JSON-shaped.

- **The type system fragments one SA concept across three places.** The SA gives an object-state a single child-language (`HLang`). dataspec splits it into a per-field `required` flag, `ArrayType` length bounds, and an open-map `rest` attribute. They are three shards of one idea, which is why each felt ad hoc and why `rest` was the source of a real soundness bug in `compatible_with`.

- **Structureless escape hatches undercut the tool's purpose.** `Any`, open objects, and the `[string]: T` map all let a schema declare "no structure here," which is the opposite of what a schema is for. They also have no clean SA analogue (the paper explicitly excludes the `xs:any` content model).

The redesign collapses the three shards into one (`cardinality`), gives the Document a canonical form that represents every input faithfully, and removes the escape hatches.

---

## 3. Goals and non-goals

**Goals**
- One canonical Document model, format-independent, faithful to every supported input (including XML interleaving).
- A schema model that is a faithful, simplified Schema Automaton — every construct maps to an SA concept.
- Restrictive by default: a schema guarantees structure.
- A clean formal definition both models can be specified and reasoned about from.

**Non-goals (deliberately deferred)**
- **Maps / open key sets** (`{ [string]: T }`). Removed for now; reintroduce later as an explicit, opt-in construct if needed.
- **Wildcard / open records** and **`Any`** — removed; they abandon structure.
- **Structural unions** (`{a}|{b}`) and **positional tuples** (`[string, integer]`) — not expressible; deferred.
- **Constrained scalars** (e.g. `Email = string matching …`) — no value refinements yet.
- **Ordered content models** (XSD `xs:sequence` ordering) — validation is order-free (see §4, §7).

---

## 4. Document model (Data Tree)

A Document is a **node**, defined as an ordered list of labeled edges — Lee & Cheung's `CEdges(n) = e₁…eₖ`.

```
value   = scalar  (string · integer · number · boolean · date · time · datetime)  |  null
edge    = (label: String, target)            where target = value | node
node    = [ edge, edge, … ]                  -- ordered; labels MAY repeat
Document = node                              -- (or a bare value at a leaf)
```

**Properties**

- **"Many" is a repeated label.** An array of `Member`s is the label `member` occurring N times — not a field pointing to an array. JSON `{"member":[A,B]}` and XML `<member>A</member><x/><member>B</member>` both become `[(member,A), …, (member,B)]`.
- **Object and array unify.** A node is just an ordered edge list; the object-vs-array distinction vanishes.
- **Order is preserved in the Document** (it is the canonical, faithful record) but is **data, never a schema constraint** (§7). A reordered round-trip remains schema-valid.

**Format mapping**

| Source | Document |
|---|---|
| JSON object `{"a":1,"b":2}` | `[(a,1),(b,2)]` |
| JSON keyed array `{"m":[A,B]}` | `[(m,A),(m,B)]` |
| YAML mapping / sequence | as JSON |
| TOML table / array-of-tables | as JSON |
| XML elements (incl. interleaved) | `[(tag,…),…]`, order preserved |

---

## 5. Schema model

A **Schema** is `(root, env)`, where `root` is a `Ref` and `env` maps names to **definitions**. There are exactly two definition kinds, split along the SA's two axes.

```
Schema      = root: Ref ;  env: Name ⇀ Definition
Definition  = Record | Union

Record  = { Field… }                         -- CLOSED; constrained by HLang
Field   = (label: String, type: Type, cardinality: [min, max])
Type    = Ref(Name) | Union                  -- a field points to a named def, or an inline union

Union   = a value domain (a VDom)            -- a set of members, each one of:
            kind     (string · integer · number · boolean · date · time · datetime)
            literal  (a quoted string, or a bare non-string literal: null, true, 42)
            null
          -- members are value domains only; never a Record
```

**Rules**

- **Records are closed.** Any label not named by a field is invalid. (No wildcard.)
- **Cardinality is the unordered HLang** and the *only* mechanism for multiplicity: `[1,1]` required (default), `[0,1]` optional, `[0,∞]` array, `[1,∞]` non-empty array, `[2,5]` bounded. **There is no separate Array type** — array-of-record is `cardinality > 1` with a `Ref` item.
- **`?` is value-domain-only.** `string?` ≡ `Union{ string, null }`. It adds `null` to a Union; it **cannot** apply to a `Ref`. "This record may be absent" is `cardinality [0,1]`, never `?`.
- **Records are always named and reached by `Ref`.** No inline/anonymous records — this keeps the schema a graph of named states (the automaton), not a nested tree, and makes recursion/reuse uniform. Unions may be inline or named.
- **Members of a Union are value domains only** — kinds, literals, null — never a record.

**Surface syntax** (shorthands desugar to the model)

```
record Member {
    "name": string,                  -- string = Union{ string }
    "role": string,
}
record Team {
    "name":         string,
    "members" [0,]: Member,          -- cardinality [0,∞]; Ref(Member)
    "lead" [0,1]:   Member,          -- optional
}
union  License { "auto", "manual", null }    -- enum + null, one value domain
root Team
```

- **Quoting rule:** `"quoted"` = a **data string** (a field label or a string literal); an **unquoted identifier** = a **schema name** (a kind or a `Ref`); a **bare keyword** = a non-string literal (`null`, `true`, `42`).
- `enum` = a `Union` of only-literals. `"a" | "b"`, `string?`, `integer | "x"` are inline-`Union` shorthands.
- `record` / `union` are the two naming keywords. ("type" is *not* a keyword — it was overloaded between the category, the binding, and `Record`.)

---

## 6. SA grounding

| Construct | Schema Automaton |
|---|---|
| **Record** | a state constrained by **HLang** (its child labels) |
| **Union** | a state constrained by **VDom** (its values) |
| **Field cardinality `[m,n]`** | HLang multiplicity of a symbol — *unordered* (commutative) |
| **Closed record** | δ total over a **finite** label alphabet; unlisted labels → dead state |
| **Ref** | a named, reusable state — enables recursion |
| **`null` in a Union / `?`** | `ε ∈ VDom(q)` (the paper's null value is a VDom member) |
| **Repeated label (array)** | `δ(q, member)=qMember`, HLang `member*` — finite alphabet, unboundedness in the Kleene star |

Two exclusions, in SA terms:

- **`?` on a record** would accept a record *or* a null leaf = `({ε}×{name}) ∪ ({null}×{ε})` — a union of two VDom×HLang rectangles, which no single SA state can express. So `?` is scalar-only and absence is cardinality.
- **Maps / open keys** are the `xs:any` content model the paper explicitly leaves outside the SA.

---

## 7. Conformance (validation)

A node `n` conforms to a `Record R` iff:
1. **Cardinality** — for each field `(label, type, [m,k])`, the count of edges in `n` with that label is in `[m,k]`.
2. **Closedness** — every edge label in `n` is some field of `R`.
3. **Targets** — each matching edge's target conforms to that field's `type`.

A value conforms to a `Union` iff it lies in the Union's value domain. A target conforms to `Ref(N)` iff it conforms to `env[N]`.

**Order is ignored.** Cardinality counts edges; it never constrains their sequence. A JSON document and an interleaved XML document with the same edge multiset conform identically.

---

## 8. Serialization (Document → format)

Group all edges sharing a label into one key, regardless of position: `[(m,A),(x,X),(m,B)]` → `{"m":[A,B], "x":X}`. Within-label order (`A` before `B`) is preserved; cross-label interleaving is dropped (no JSON-family format can express it). See open question (1) for the count-1 ambiguity.

---

## 9. Impact on the current implementation

This is a **breaking redesign of the core**, not an incremental change:

- **Document representation** changes from `dict`/`list`/scalar to an ordered edge list. The `Doc` API (`get`/`child`/`add`/…) would be reframed as a projection over edges; array access becomes "collect same-label edges."
- **Type tree** is replaced: `ObjectType`+`ArrayType` collapse into `Record` (fields with cardinality); `ScalarType` becomes `Union`; `AnyType` is removed; `RefType` stays.
- **Codecs** change: readers build edge lists; writers group by label and consult cardinality (or a fallback) to choose array-vs-bare.
- **DSL** changes: quoted-label rule, `record`/`union` keywords, `[m,n]` cardinality, `?` scalar-only.
- **Operations** (`validate`/`compatible_with`/`equivalent`/`normalize`) re-expressed on the new model — and several get *simpler* (no `rest` special-casing; scalar checks become VDom subset).

A phased path is possible (introduce the edge-list Document behind the existing API first, then the schema model), but the end state is incompatible with today's public types.

---

## 10. Resolved decisions (recommended — pending confirmation)

These were the open questions; here are the recommended resolutions, consistent with the restrictive-by-default philosophy. Confirm or override before the code that depends on them is written.

1. **Count-1 serialization → schema-driven, with an always-list fallback.** When a schema is available, cardinality decides array-vs-bare (`max > 1` → list, else bare) — faithful, idiomatic output. With no schema, fall back to always-list (every grouped label becomes an array). This keeps the Document format-independent (no format-derived bits) and puts the array/bare decision where the cardinality actually lives.
2. **Array-of-scalar → a repeated label**, uniform with array-of-record (`"tags"[0,]: string`). One mechanism (cardinality) for all "many," matching XML's repeated elements.
3. **Bare nested arrays (`[[1,2],[3,4]]`) → forbidden for now.** They have no Data-Tree form (no label for inner elements) and XML can't express them either; reading one raises a clear error. Revisit only if a concrete need appears.
4. **Root → a `Ref` to a single record (single-rooted).** Guarantees a lossless XML round-trip (one document element) and keeps the entry point uniform with every other state.

---

## Appendix: worked example

Schema:

```
record Member {
    "name": string,
    "role": string,
}
record Team {
    "name":         string,
    "members" [0,]: Member,
}
root Team
```

Document (canonical edge list) for a two-member team:

```
[ ("name", "Platform"),
  ("member", [ ("name","Ann"), ("role","dev") ]),
  ("member", [ ("name","Bob"), ("role","pm")  ]) ]
```

- JSON projection: `{"name":"Platform", "members":[{"name":"Ann","role":"dev"},{"name":"Bob","role":"pm"}]}`
- XML projection: `<name>…</name><member>…Ann…</member><member>…Bob…</member>` (and an interleaved XML input round-trips through the *same* Document).
- Conformance: `member` occurs twice ∈ `[0,∞]` ✓; each `member` target conforms to `Member` ✓; `name` once ∈ `[1,1]` ✓; no unlisted labels ✓.
