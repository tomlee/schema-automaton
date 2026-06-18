# Algorithms

The five schema computations from §5 of the paper, all implemented in
`src/algorithms.py` against the `ContentModel` interface (so they are
independent of data format). Each operates on a `SchemaAutomaton`.

| Function | Paper | Signature |
|----------|-------|-----------|
| `make_useful_sa` | Alg. 1 | `(sa) -> None` (in place) |
| `minimize_sa` | Alg. 2 | `(sa) -> SchemaAutomaton` |
| `equivalent_sa` | Alg. 3 | `(a, b) -> bool` |
| `subschema_sa` | Alg. 4 | `(a, b) -> IncompatibilityReport` |
| `extract_subschema` | Alg. 5 | `(sa, permitted_symbols) -> SchemaAutomaton` |
| `conforms_to` | Def. 3 | `(sa, tree) -> ConformanceResult` |

---

## MakeUsefulSA (Algorithm 1)

Removes **useless** states, producing an equivalent *useful* SA. A state is
useless if it is (Theorem 1):

1. **inaccessible** — unreachable from `q0`; or
2. **irrational** — on a cycle of *mandatory* transitions (it would force an
   infinite subtree, which no finite Data Tree can satisfy); or
3. has a mandatory path to an irrational state; or
4. reachable only through useless states.

Implementation notes:

* Irrational states are found with **Tarjan's SCC** over the graph of mandatory
  transitions (a transition `q --a--> q'` is mandatory when `a` occurs in every
  string of `Content(q)`).
* Uselessness then propagates backward along mandatory transitions.
* Content models of surviving states are rewritten with `remove_symbol` to drop
  any transition into a removed state.
* If `q0` itself becomes useless, the SA's language is empty and the function
  raises `ValueError` ("no useful SA equivalent exists").

---

## MinimizeSA (Algorithm 2)

Returns the **minimal** SA — the fewest states among all equivalent SAs — which
is the unique canonical form of the language (up to isomorphism, Theorem 4).

* First makes the SA useful.
* Then **partition refinement**: states start grouped by
  `(content.canonical_key(), vdom)`; a block is split whenever two of its states
  transition on the same symbol into states in different blocks. Iterate to a
  fixed point; each final block is an equivalence class and becomes one state.

The number of equivalence classes is the lower bound on the size of any
equivalent SA (Theorem 3).

---

## EquivalentSA (Algorithm 3)

Decides `L(A) = L(B)`.

* Minimize both inputs.
* Walk them in **parallel BFS** from their initial states, checking at each
  paired state that the value domains are equal and the content-model languages
  are equal, and that transitions correspond one-to-one.

Exactness relies on Theorem 4 (the minimal SA is unique up to isomorphism).

---

## SubschemaSA (Algorithm 4)

Decides `L(A) ⊆ L(B)` — equivalently, *"is B compatible with A?"*.

* Makes A useful, then walks A and B together from their initial states. For each
  reached pair `(qa, qb)` it requires:
  * `VDom(qa) ⊆ VDom(qb)` (value domains),
  * `Content(qa) ⊆ Content(qb)` (child languages),
  * every transition present in A is present in B.
* Returns an **`IncompatibilityReport`** rather than a bare boolean:

  ```python
  report = subschema_sa(a, b)
  report.is_compatible       # bool
  report.vdom_issues         # [(qa, qb), ...]
  report.content_issues      # [(qa, qb), ...]
  report.transition_issues   # [(qa, symbol), ...]
  print(report)              # formatted explanation
  ```

This is the operation behind version-compatibility checking
([User Guide §7](user-guide.md#7-check-version-backward-compatibility)).

---

## ExtractSubschema (Algorithm 5)

Given a set of **permitted symbols** `X' ⊆ X`, produces a subschema accepting
exactly those instances of the original whose edge symbols all lie in `X'`.

* Every transition on a non-permitted symbol is queued for deletion.
* Deleting a transition rewrites the source state's content with
  `remove_symbol`. If that empties the content (the symbol was mandatory there),
  the source node cannot exist, so transitions *into* it are queued too; if this
  reaches `q0`, no valid subschema exists and it raises `ValueError`.
* Finally the result is made useful and minimized.

The output is guaranteed to be a subschema of the input.

---

## Conformance — `conforms_to` (Definition 3)

Decides whether a Data Tree is an *instance* of an SA, made constructive: it
builds the paper's **binding map** `Bind : N → Q` top-down from the root. At each
d-node `n` bound to state `q` it checks the value lies in `VDom(q)`, the
child-symbol sequence lies in `Content(q)`, and binds each child via
`δ(q, Sym(e))`.

```python
r = conforms_to(sa, tree)
r.ok            # bool (also truthy/falsy directly)
r.binding       # {node_id: state} — every conforming node and the state it bound to
r.errors        # [(path, message), ...] with JSON-path-like locations
```

`conforms_to`, `SchemaAutomaton.accepts` (boolean), and
`SchemaAutomaton.validate` (diagnostics, no binding) all agree on the verdict;
`conforms_to` additionally returns the binding. A nullable object/array state
binds a JSON `null` directly; an open-map's additional keys are bound as
unconstrained.

## Complexity & performance

Each algorithm's main loop is polynomial in the number of states. The
non-polynomial cost is in comparing the **regular content languages** of
ordered models:

* regular-expression **equivalence** `L(r1) = L(r2)` and **inclusion**
  `L(r1) ⊆ L(r2)` are PSPACE-complete in general.

This library decides them exactly via the DFA engine in `src/nfa.py` (Thompson
construction → subset construction → product intersection / complement over the
shared alphabet → emptiness; Hopcroft minimization for canonical keys).

The paper reports large speed-ups by short-circuiting most comparisons with a
cheap **literal-equality** test before the full automaton test, and a PTIME
**weak test** for the simple regular expressions that dominate real-world
schemas (≈97% of industry XSDs).

* The **literal-equality short-circuit is implemented**: `HLang.is_subset_of`
  and `HLang.language_equals` return immediately when two content models have
  identical regular-expression text (identical text ⇒ identical language), which
  the paper notes covers most positive cases in practice (e.g. an unchanged
  complex type across schema versions).
* The PTIME **weak test** for simple expressions (§6 of the paper) is not yet
  implemented and remains a natural future optimization.

For unordered `MapModel` content, subset and equality are decided directly on the
field sets in linear time.
