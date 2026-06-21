# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/); this project is
**alpha** and the public API may still change between releases.

## [v0.1.1a9]

A pre-publish review pass: no new features, but a real bug fix and a
substantial test-coverage push (89% -> 96% line coverage on `omnist/`).

- **Fixed:** `Schema(root, env)` / the `schema()` builder didn't validate
  that every environment entry is a `Record` — handing in a bare `Scalar`
  (e.g. `schema(ref("R"), R=t.string)`) crashed with a raw `AttributeError`
  from deep inside `check_refs()` instead of a clean `SchemaError`. Now
  validated up front with a clear message. (This also made a defensive
  "root must resolve to a record" check at the end of `check_refs()`
  provably unreachable dead code; removed it.)
- Closed real test gaps found while reviewing: every distinct DSL parser
  error path (missing colon, garbage top-level token, no `root`, duplicate
  definition, unquoted field label, empty cardinality, unknown reference,
  and — found while writing these — the old enum-rejection test was
  actually hitting the *tokenizer's* `|` rejection, not the parser's
  literal-type rejection, so that path was untested until now); the
  recursion-depth and cycle-detection guards `SECURITY.md` describes;
  `Doc.from_yaml`/`from_toml`/`from_xml`, `to_json`/`to_yaml`/`to_xml`,
  and `Doc == Doc`/`Doc.validate()`; malformed-input `ParseError`s for all
  four formats; the `string.ambiguous`/`null.omitted` XML adjustment codes;
  TOML's top-level-table requirement; several `compatible_with` edge cases
  (cardinality `[0,0]`, unbounded vs. bounded, a field one side doesn't
  know about); `infer()`'s zero-sample, non-object-root, mixed-type, and
  generated-name-collision cases. `dsl.py`, `document.py`, `infer.py`,
  `operations.py`, and `deserialize.py` are now at 100% line coverage.

## [v0.1.1a8]

**Breaking:** the project is renamed from `dataspec` to `omnist` ("omni-structure"),
before the first PyPI release (no users yet, so this is a clean rename, not a
deprecation period). `import dataspec` becomes `import omnist`; `DataspecError`
becomes `OmnistError`. The GitHub repository moves to
[tomlee/omnist](https://github.com/tomlee/omnist) (GitHub redirects the old
`tomlee/dataspec` URL). No behavioral changes.

## [v0.1.1a7]

Schema-directed deserialization: pass `schema=` to `read_json`/`read_yaml`/
`read_toml`/`read_xml` (and `Doc.from_json`/`from_yaml`/`from_toml`/`from_xml`)
to upgrade each leaf to match what the schema declares, when the conversion
is value-exact (`"2024-01-01" -> date`, `1.0 -> int 1`), and raise
`ParseError` when it isn't (`1.5 -> integer`, `"abc" -> integer`). Exposed
directly as `materialize(node, schema)` for already-parsed nodes. This was
the deserialization feature blocked by the value-domain ambiguity fixed in
v0.1.1a6 — every field now has exactly one candidate scalar, so there's never
a choice between candidate representations.

## [v0.1.1a6]

**Breaking:** removed value-domain composition (enums/unions) from the schema
model. A field's type is now always exactly one of the seven fixed scalars
(`string`, `integer`, `number`, `boolean`, `date`, `time`, `datetime` —
optionally nullable, e.g. `string?`) or one `Ref` to a named record — never a
composition of either. The DSL no longer has a `|` operator, literal values in
type position, or a `union`/`domain` keyword. Composable value domains made
schema-directed deserialization ambiguous: a value could satisfy more than one
candidate representation with no principled way to choose which Python type to
materialize it as, so the feature is gone rather than fixed. On the Python
builder side, the `union(...)` function is removed; a new `Scalar` class
replaces it, with ready-to-use instances exported as `STRING`, `INTEGER`,
`NUMBER`, `BOOLEAN`, `DATE`, `TIME`, `DATETIME` (also under a `t` namespace,
e.g. `t.string`) that can be passed directly as a field's type, plus a new
`nullable(scalar)` builder for the `?` form.

## [v0.1.1a5]

**Fixed:** `datetime` accepted a bare date-only string (`"2024-01-01"`) as a
valid value, because `datetime.fromisoformat` is lenient -- it defaults a
missing time component to midnight rather than rejecting the string. That
silently treated "no time given" as "the time is exactly midnight," and
meant `date` and `datetime` weren't actually mutually exclusive for the
string form (only for real `datetime.date`/`datetime.datetime` objects).
`matches_kind` now also requires that the string does *not* parse as a bare
`date`, so `date`, `time`, and `datetime` are exclusive for every value,
string or object. Narrows acceptance -- a previously-(incorrectly-)valid
string now fails `datetime`, so this is a behavior change, not purely
additive.

## [v0.1.1a4]

Three robustness fixes for the schema DSL parser, found by probing it
against its own grammar rather than just reading it (PR 2 of the model
replan):

- **Fixed:** a non-integer cardinality bound (e.g. `[1.5,3]`) crashed with
  an uncaught `ValueError` instead of a clean `SchemaError`.
- **Fixed:** the "depth guard" counted total `{` characters across the
  *whole* schema text as a proxy for nesting depth, so a large but
  perfectly flat schema (hundreds of unrelated top-level records, no
  nesting at all) was falsely rejected. The grammar has no inline
  nesting to guard against in the first place (records are never
  anonymous), so the check is removed rather than recalibrated.
- **Fixed:** a `record` or `union` could be defined with the same name
  as a builtin scalar keyword (`record string { ... }`) with no error —
  but it could never actually be referenced, since a bare name in a type
  position always means the builtin scalar. Now raises `SchemaError` at
  definition time.

## [v0.1.1a3]

`Doc` gains `check_json` / `check_yaml` / `check_toml` / `check_xml` / a
generic `check_format`, completing the `from_*`/`to_*` symmetry the v0.1.1a2
report machinery left out — every format had a `Doc.to_*` writer, but
"simulate that write and inspect the report" required dropping down to the
module-level `check_*` function on `d.to_data()`. `Format` gains an optional
fourth field, `check`, so a plugin can support `Doc.check_format` too; the
four built-ins all provide it.

## [v0.1.1a2]

Two features deferred from the v0.1.1a1 redesign, now implemented on the
canonical model:

- **Adjustment reports + strict mode for the codecs.** Writing to a format
  that can't hold every value losslessly (TOML has no `null`; JSON/XML have
  no date type; JSON has no `NaN`/`Infinity`) is lenient by default — the
  writer adjusts the value and records it as an `Adjustment` in a
  `WriteReport` — instead of losing it silently. `write_json` / `write_yaml`
  / `write_toml` / `write_xml` (and the matching `Doc.to_*`) now accept
  `report=` to inspect what changed, and `strict=True` to raise `WriteError`
  instead of adjusting. `check_json` / `check_yaml` / `check_toml` /
  `check_xml` simulate a write and return the report with no output.
- **Format registry.** `register_format(Format(name, read, write))` adds a
  custom format usable everywhere via `Doc.from_format` / `Doc.to_format`;
  `get_format` / `formats()` look up / list what's registered. The four
  built-ins register themselves on import.

New: `omnist.canonical.report` (`WriteReport`, `Adjustment`, `finish_write`)
and `omnist.canonical.registry` (`Format`, `register_format`, `get_format`,
`formats`), both re-exported from `omnist`. Documented in
[the API reference](docs/api.md#adjustment-reports-lossy-writes) and
[the guide](docs/guide.md#reading--writing-formats); covered by new tests in
`tests/test_canonical.py` and `tests/test_docs.py`.

## [v0.1.1a1]

**A breaking redesign of the core models** around the formal Data Tree /
Schema Automaton (Lee & Cheung, CIKM 2010). The v0.1.0 API (`ObjectType`,
`ArrayType`, `obj`, `arr`, `t.*`, the `root { … }` DSL) is **removed** — this
is a clean break. See [docs/design/model.md](docs/design/model.md).

- **Document** is now an ordered list of labeled edges (a Data Tree), not a
  dict-with-arrays. "Many" is a repeated label; object and array unify; XML
  interleaving is representable. The same Document represents all four formats.
- **Schema** has two named definition kinds — **`record`** (closed fields,
  each with a cardinality) and **`union`** (a value domain of kinds, literals,
  and/or null) — referenced by name (`Ref`) for reuse and recursion. There is
  no separate array type (an array is a field with `max > 1`), no `Any`, and
  no open maps (deliberately deferred); records are closed.
- **DSL**: `record` / `union` definitions, always-quoted field labels,
  `[min,max]` cardinality, `?` for value-domain null. Operations
  (`compatible_with` / `equivalent` / `normalize`) are **methods on `Schema`**.
- The earlier `compatible_with` soundness bugs cannot recur — the open-map
  `rest` construct that caused them is gone.
- Implementation lives in `omnist.canonical`; `import omnist` is its
  public surface. Docs rewritten: a new [user guide](docs/guide.md) and the
  formal [model spec](docs/design/model.md).

## [v0.1.0a9]

Three schema-compatibility/validation soundness bugs, found by comparing
omnist's `Schema`/`Type` model against the formal Schema Automaton (SA)
model it's based on (Lee & Cheung, CIKM 2010):

- **Fixed (unsound):** `compatible_with()`/`equivalent()` judged a schema
  with an open map (`{[string]: T}` / `rest=`) "backward compatible" with a
  schema that names one of those keys explicitly with an incompatible type
  -- e.g. `{[string]: string}` was wrongly judged compatible with
  `{extra?: integer, [string]: string}`, even though `{"extra": "hello"}`
  is accepted by the former and rejected by the latter. The check only ever
  compared the two schemas' `rest` types to each other and their named
  fields to each other, never a `rest`'s emitted keys against the *other*
  schema's named fields, even though an open map can emit any key,
  including one the other side names explicitly.
- **Fixed:** an `enum` of `date`/`time`/`datetime` values was wrongly
  judged incompatible with a schema accepting that kind outright (e.g. an
  enum of two specific dates vs. a plain `date` field) -- the internal
  helper that classifies an enum literal's kind only recognized
  `bool`/`int`/`float`, silently treating every temporal value as a
  `string`.
- **Fixed (unsound):** the DSL silently dropped an enum constraint when
  mixed with a bare scalar kind in a union -- `integer | "foo"` accepted
  any string, not just `"foo"`, because the parser substituted a bare
  `string` kind for the enum instead of keeping both. The Python builder's
  `enum()` had the same latent bug from the other direction: it set the
  literals' own kind on the `ScalarType` it built, which (now that
  validation correctly falls back to checking kinds alongside an enum)
  would have made every builder-built enum accept any value of that kind,
  not just its specific literals -- caught and fixed in the same pass.
  `ScalarType`/`_check_scalar`/`_scalar_subtype`/`__repr__` now support a
  scalar kind and an enum together as a real, intentional construct rather
  than two mutually-exclusive representations.

## [v0.1.0a8]

A breaking fix to XML's document-root handling, grounded in the labeled-tree
(OEM) data model the schema design is based on: the data tree's true root is
anonymous, and an XML document element is the single *named* child of that
root, not the root itself. The previous implementation conflated the two.

- **Fixed (breaking):** `read_xml` used to discard the document element's
  tag entirely (`<x><y>1</y></x>` read as `{"y": 1}`, not `{"x": {"y": 1}}`),
  and `write_xml` always invented a meaningless `<root>` wrapper, even for
  data that already had an obvious, lossless single-element XML shape. The
  document element's tag is now a real, round-tripping top-level key:
  `read_xml`/`write_xml` work with a Document that has exactly one top-level
  key (a *single-rooted* Document) — `{"x": {"y": 1}}` <-> `<x><y>1</y></x>`,
  exactly, including a detour through another format and back.
- **New:** `read_xml_documents`/`write_xml_documents` for a Document that
  *isn't* single-rooted (multiple top-level keys, or a top-level list) —
  translates a Document <-> a *forest* of XML documents, one per top-level
  key, with a list value producing one repeated-tag document per item.
  `write_xml` itself now raises `WriteError` on a non-single-rooted Document,
  unconditionally (not just under `strict`): unlike every other lossy
  adjustment in the library, there's no value-preserving fallback shape to
  wrap it in — inventing one would mean the round-tripped data no longer
  matches the schema the original was written for.
- **Removed (breaking):** `write_xml`/`check_xml`'s `root=` and `wrap_key=`
  parameters — there's nothing left to invent a name for; the document
  element's name now always comes from the data itself.
- **Documentation:** the previously-documented "XML root-name lossiness"
  (added in v0.1.0a5) is obsolete — it was a symptom of this bug, not an
  accepted limitation — and has been rewritten across `docs/formats/xml.md`,
  `docs/document.md`, `docs/formats/overview.md`, and `docs/faq.md`.

## [v0.1.0a7]

No code changes — a packaging/release-readiness check ahead of
eventually dropping the alpha suffix and publishing.

- Verified the package actually builds and installs as a real
  artifact, not just from an editable source checkout: `python -m
  build` produces a valid sdist and wheel, `twine check` passes both,
  `py.typed` is correctly included in the wheel, and installing the
  built wheel into a clean virtualenv (no source tree on the path)
  and running the full test suite against it passes.
- Found a real blocker for publishing to PyPI under the name
  `dataspec`: an unrelated package already holds it (Covera Health's
  "Data specification and normalization toolkit," last released in
  2020). Resolving this — a different distribution name, or
  requesting release of the apparently-abandoned name — is a
  prerequisite for any PyPI publish, independent of code readiness.

## [v0.1.0a6]

Performance only — no behavior changes (verified: every existing test
passed unmodified, plus the `hypothesis` property suite at 3000
examples/property, before and after each change).

- `write_toml`/`check_toml` merged three separate full-tree passes
  (int-range scan, offset-time fix, null strip) into one. Measured
  **45% faster** on a 2000-section document (52.2ms → 28.5ms) — the
  three old passes cost almost as much as `tomli_w`'s own
  serialization.
- `Doc.to_data()` and the `get()`/`at()` snapshot helper replaced
  `copy.deepcopy` with a small Document-shape-aware copy. Measured
  **~3.5x faster** on a 2000-section document (12.9ms → 3.6ms) —
  `_snapshot()` backs every `get()`/`at()` call on a container field,
  so this is the more frequently-hit fix in practice.
- `Schema.peel()` no longer allocates an empty `set()` for the common
  case (a type that isn't a named-type reference). Measured ~11%
  faster `validate()` on a 2000-field schema with no named types
  (2.99ms → 2.67ms).

## [v0.1.0a5]

- Fixed: `write_toml`/`check_toml` crashed with a raw `ValueError` on a
  timezone-aware `time` (TOML's native `time` type has no offset slot
  at all, only `date-time` does); now stringified and reported as
  `temporal.stringified`.
- New: `integer.precision_risk` — a JSON integer beyond JavaScript's
  safe-integer range (`±2**53`) round-trips exactly through omnist's
  own `read_json`, but silently loses precision in a JS-based parser
  (a browser, Node.js); now reported (the same class of interop risk
  as TOML's existing `integer.out_of_range` check).
- Documented: the XML root element's name is discarded on read and
  doesn't survive a detour through another format — `<k>...</k>` →
  JSON → XML gives `<root>...</root>` back, not `<k>...</k>`, unless
  you explicitly re-supply `root="k"` yourself.
- Documented: a `"How incompatibilities are handled"` overview in
  `docs/formats/overview.md` naming the three buckets every
  cross-format incompatibility falls into — raises (illegal input),
  reported adjustment (lossy-but-legal), or silent read-time
  normalization (comments, XML namespace prefixes — a short, fixed
  list with no report mechanism, since neither was ever part of the
  Document model).
- New: explicit cross-format test coverage for key names that are
  syntactically significant in one format's grammar but not another
  (TOML's `. = [ ]`, YAML's `:`, the `#` comment marker shared by
  both) — found that `.` is actually *legal inside an XML name*, so a
  TOML-special key like `"a.b"` is the one case XML does **not**
  sanitize; documented in `docs/formats/xml.md`.

## [v0.1.0a4]

A security/robustness audit of the format codecs, prompted by the
question "is the library safe now?" Found and fixed five more real
bugs, none caught by the edge-case sweep in v0.1.0a3:

- Fixed: a small, ordinary YAML payload using anchors/aliases to share
  structure (not a cycle, just YAML's normal way of avoiding
  duplication) took time **exponential** in nesting depth to validate
  — a 469-byte, 9-level payload that `yaml.safe_load` parses instantly
  didn't finish validating in 15 seconds. The cause was omnist's own
  post-parse cycle/depth check re-walking a shared subtree once per
  alias reference instead of once per unique object; PyYAML itself
  shares the constructed objects and was never the problem. Now linear
  in the number of unique objects.
- Fixed: `read_xml` silently fell back to the standard library's XML
  parser (vulnerable to XXE/entity-expansion) with no indication at
  all when the optional `defusedxml` dependency isn't installed. Now
  raises `UnsafeXMLWarning` each time this happens.
- Fixed: `read_json`/`read_toml` leaked the underlying parser's native
  exception (`json.JSONDecodeError`, `tomllib.TOMLDecodeError`) on
  malformed input instead of wrapping it in `ParseError` like
  `read_yaml`/`read_xml` already did, breaking the documented
  "catch everything with `except ParseError`" contract.
- Fixed: `write_xml` embedded literal control characters (e.g. a NUL
  byte) directly in the output with no warning — unlike the format's
  other adjustments, this isn't lossy, the result doesn't parse as XML
  *at all*. Now stripped and reported as `string.illegal_xml_char`,
  an error.
- Fixed: `infer()` crashed with a raw `AttributeError`/`TypeError` on a
  sample like `[False, {}]`, instead of the same clean, documented
  `SchemaError` every other "mix of structure and scalar" sample
  already got. A bool was classified separately from other scalars in
  the structural-mixing check; now it isn't.
- New: `tests/test_property.py` — property-based fuzzing with
  `hypothesis`, generating randomized Documents and text across every
  codec and the DSL parser on every CI run. Found three of the five
  bugs above.
- New: `SECURITY.md` — the trust model for each format (what's
  hardened, what isn't) and how to report a vulnerability (GitHub
  private vulnerability reporting, now enabled on this repo).

## [v0.1.0a3]

- Fixed: deeply/adversarially nested input (`Doc` construction, the
  functional `write_*`/`read_*` codecs, and the schema DSL parser) used
  to crash with an uncatchable `RecursionError`; each now raises a clean
  `DocumentError`/`SchemaError` past a depth limit.
- Fixed: a real key collision (e.g. JSON's `{1: "a", "1": "b"}`, or two
  XML keys sanitizing to the same element name) was reported as a soft
  warning even though it silently overwrites one value with the other;
  now reported as `key.collision`, an **error**.
- Fixed: the format registry (`register_format`/`get_format`/`formats()`)
  was an unsynchronized global dict; a plugin registered from a
  background thread could race a concurrent lookup. Now thread-safe.
- Fixed: three more silent XML/TOML data-corruption cases found by a
  systematic edge-case sweep — a string that looks like a number/bool/
  `null` silently changing type on read (`string.ambiguous`), an empty
  object/array silently becoming an empty string or vanishing entirely
  (`container.empty.ambiguous`), an integer beyond TOML's signed 64-bit
  range written without warning (`integer.out_of_range`), and a string
  containing `\r` silently losing its line endings per the XML spec's
  own normalization rules (`string.line_ending_normalized`). All four
  are now reported, and rejected by `strict=True`.
- New: `tests/edge_cases.py` / `tests/test_edge_cases.py` — a shared
  corpus of ~45 edge-case values swept across every format and a few
  API operations (`Doc`, `infer`, DSL round-trip) via general
  invariants rather than hand-coded expectations per case.
- New: `tests/test_dsl.py` negative-path coverage — one case per
  distinct `SchemaError` the hand-written DSL parser can raise.
- CI now runs `ruff check .` and every `examples/*.py` script, not just
  `pytest`.
- New: `CONTRIBUTING.md`.
- Removed the redundant `sys.path.insert` boilerplate from every
  example and test file (the editable install already covers it); a
  few `pyproject.toml` metadata fields filled in.

## [v0.1.0a2]

- New: `finish_write(text, rep, *, strict=False, report=None)`, a public
  helper format plugins can call instead of reimplementing the
  strict/report decision every built-in writer makes; the built-ins
  (`write_json`/`write_yaml`/`write_toml`/`write_xml`) now use it too.
- New: [`docs/plugins.md`](docs/plugins.md) — a guide for writing a format
  plugin (the `Format` contract, the adjustment-report pattern, a
  verified worked example, testing, and a checklist).
- Project practices: `CHANGELOG.md`, `ruff` lint config, a `py.typed`
  marker (PEP 561), and branch protection on `master` requiring CI.
- Changes from here on go through a pull request rather than a direct
  commit to `master`.
- Docs: example city/coordinates data changed from Hong Kong to London
  (and Shenzhen to Dublin); assorted doc-accuracy fixes found during a
  full pass over the doc set (stale TOML array-formatting comments, a
  missing validation error, clarified empty-array inference).

## [v0.1.0a1] - first tagged alpha

- Core model: `Doc` (the guarded data-DOM) and the `Schema`/`Type` tree
  (`ScalarType`, `ArrayType`, `ObjectType`, `AnyType`, `RefType`).
- Schema DSL: `parse_schema` / `to_dsl`, plus a Python schema builder
  (`obj`, `arr`, `mapping`, `enum`, `optional`, `nullable`, `ref`, `schema`,
  and the `t` namespace for scalar atoms).
- Pluggable format registry with built-in JSON, YAML, TOML, and XML codecs
  (`read_*` / `write_*` / `check_*`), lenient by default with adjustment
  reporting (`WriteReport` / `Adjustment`) and an opt-in `strict` mode.
- `infer()` to draft a schema from example Documents.
- Schema comparison operations: `compatible_with`, `equivalent`, `normalize`.
- Full exception hierarchy under `OmnistError`.
- GitHub Actions CI running the test suite (228 tests) on Python 3.11–3.13.
- Complete documentation set: concepts, architecture, getting started, the
  `Doc` API, the schema language, format-by-format pages, inference, schema
  comparison, an API reference, and an FAQ — every code example verified
  against the library.
