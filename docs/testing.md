# Testing

How Omnist's test suite is laid out, how coverage is measured and treated,
what the fuzz tests actually fuzz, and what CI runs on every push and PR.

## Layout

All tests live in `tests/`, run with `pytest`.

- **`tests/test_canonical.py`** — the core test file for the canonical
  (current) Document/Schema model described in `docs/design/model.md`: the
  edge-list `Doc`, the `record`/`Ref` schema model with its seven scalar
  kinds and field cardinality, OSD, validation (`Schema.validate`,
  `accepts`), the schema operations (`compatible_with`, `equivalent`,
  `infer`), and the codecs (`check_*`/`read_*`/`write_*` for JSON, YAML,
  TOML, XML). It's organized into `Test*` classes by area — public API,
  `Doc`, `infer`, validation, OSD robustness, temporal boundary values,
  operations, malformed input, codecs, deserialize-with-schema, reports,
  the format registry, `Doc`/module-level check parity, `WriteReport.__str__`,
  OSD error messages, document/schema-construction error paths, schema model
  dunders (`__repr__`/`__eq__`/`__hash__`/`__str__`/`__bool__`),
  `matches_kind`/`value_kind`, infer errors, and TOML/XML-specific edge
  cases.
- **`tests/test_oml.py`** — OML (Omnist's own format), covering happy-path
  round-tripping of every scalar kind plus null, string escaping, raw
  strings, multiline strings and their interaction with the line/`;`
  separator, top-level brace disambiguation, structural parse errors inside
  braces, reserved words used as labels, numeric edge cases, the
  nesting-depth limit, BOM/encoding handling, full Document round-trips
  (repeated/interleaved labels, nesting), schema-directed reads, and a
  full real-life document matching the design doc's worked example.
- **`tests/test_docs.py`** — every key snippet shown in the docs
  (`README.md`, `docs/guide.md`, `docs/schema.md`, `docs/formats/*.md`,
  etc.) is executed as an assertion here, so a documentation change that
  silently breaks the described behavior fails CI instead of rotting
  unnoticed.
- **`tests/test_examples.py`** — runs every `examples/*.py` file as a
  subprocess (via `pytest.mark.parametrize`) and asserts a clean exit code,
  printing stdout/stderr on failure. Examples are documentation too, and
  nothing else exercises them as scripts.
- **`tests/test_fuzz.py`** — property-based fuzzing with
  [Hypothesis](https://hypothesis.readthedocs.io/), added in #64. See
  [Fuzzing](#fuzzing) below.

## Coverage

Run the full suite under coverage with:

```sh
coverage run -m pytest -q && coverage report -m
```

**Target: 100% line coverage across the `omnist` package** (every module
under `omnist/`). At the time of writing this measured as:

```
Name                              Stmts   Miss  Cover
---------------------------------------------------------------
omnist/__init__.py                   12      0   100%
omnist/canonical/__init__.py         12      0   100%
omnist/canonical/deserialize.py      75      0   100%
omnist/canonical/document.py        202      0   100%
omnist/canonical/osd.py             149      0   100%
omnist/canonical/formats.py         217      0   100%
omnist/canonical/infer.py            77      0   100%
omnist/canonical/oml.py             437      0   100%
omnist/canonical/operations.py       76      0   100%
omnist/canonical/registry.py         32      0   100%
omnist/canonical/report.py           35      0   100%
omnist/canonical/schema.py          247      0   100%
omnist/errors.py                     10      0   100%
---------------------------------------------------------------
(package total: 1769 stmts, 0 missed, 100%)
```

(`tests/test_fuzz.py` and `tests/test_docs.py` themselves show a handful of
missed lines in any single run — defensive `except Exception` branches
inside the fuzz/doc tests that only fire when a property actually fails, or
a NaN-handling branch not hit by every Hypothesis seed. That's expected and
unrelated to the 100% target, which applies to the package under test, not
to the test files.)

**How a gap is treated**, following the precedent set in #63 (the PR that
first brought the package to 100%, omnist-dev/omnist#74): for every line/branch
reported as missing,

1. Read the surrounding code to understand what path is untested.
2. Decide: is it a *real, reachable* edge case, or *dead/unreachable* code?
3. If reachable — add a targeted test in the relevant existing file
   (`test_canonical.py` for schema/document/report code, `test_oml.py` for
   `oml.py`, or a new file if nothing existing fits) that exercises real
   behavior. Coverage should follow from testing real behavior, not the
   reverse — don't change behavior just to make a line easier to hit.
4. If dead — delete it. (#63's PR removed `formats.get_reader()`, a helper
   left over from before the `registry.py`/`get_format()` plugin system,
   confirmed via a history search to be unused and unreferenced.)
5. Some lines are defense-in-depth that the public API can't reach through
   normal use (e.g. a cyclic-reference guard that construction-time checks
   already make unreachable). These are tested by deliberately bypassing
   the guard (e.g. mutating private state) rather than marked
   `# pragma: no cover` — `# pragma: no cover` is reserved for lines that
   are genuinely untestable, such as an `ImportError` fallback for an
   optional dependency that's always installed in CI, and each such pragma
   must be justified in its PR.

## Fuzzing

`tests/test_fuzz.py` uses Hypothesis to fuzz two different things:

**1. Round-trip fuzzing.** Randomly generated canonical Document nodes (the
`[(label, child), ...]` edge-list/scalar-leaf shape, nested up to 5 levels
deep, with all seven scalar kinds plus `null`, including edge-case values
like signed zero, NaN/inf, and dates spanning year 1 to year 9999) are
round-tripped through every codec:

- **OML** (`write_oml`/`read_oml`) must round-trip *exactly*, with zero
  reported adjustments — OML is the one format with no documented lossiness.
- **JSON, YAML, TOML, XML** must round-trip exactly *modulo documented
  adjustments* — the test asserts every adjustment code returned by
  `check_json`/`check_yaml`/`check_toml`/`check_xml` is one already
  documented (e.g. `temporal.stringified`, `null.omitted`,
  `string.ambiguous`, `key.sanitized`, `float.special`) and only skips the
  exact-equality assertion when an adjustment was actually reported. An
  *undocumented* mismatch — an adjustment code the test doesn't recognize,
  or data that changes without any reported adjustment at all — fails the
  test. TOML is restricted to list-shaped (table) roots, since it has no
  scalar top level.
- **`doc(...)`/`build_node`** round-trip from an equivalent plain Python
  value (dict/list/scalar, generated separately since a Python dict can't
  express repeated/interleaved same-level labels), and the resulting node
  is itself round-tripped through OML.

**2. Crash-freedom fuzzing.** Arbitrary text — both fully random Unicode and
text drawn from an alphabet biased toward OML/OSD syntax characters (more
likely to reach deep parser states) — is fed into `read_oml` and
`parse_schema`. The only exceptions either is allowed to raise are
`ParseError`/`SchemaError` (or a subclass); anything else escaping is
treated as a hardening bug and fails the test immediately.

**What's deliberately *not* fuzzed**: the third-party format parsers
themselves (PyYAML, `tomllib`/`tomli_w`, the stdlib/`defusedxml` XML parser,
the stdlib `json` module) — Omnist's codecs are fuzzed at the boundary
(Document in, formatted text out, and back), not the underlying libraries'
own parsing correctness, which is out of scope.

A handful of known, separately-filed bugs are excluded from the generators
with an explanation in the code (each cross-references its own issue) so
the fuzz suite tests the *currently documented* contract rather than
red-lining on already-tracked gaps — e.g. `"inf"`/`"nan"`/`"-inf"` excluded
from generated labels (#71), documents containing U+0085 excluded from the
YAML round-trip test (#69), and two XML round-trip gaps around control
characters and empty containers (#67, #68). Found bugs are not fixed inside
this test file — per the project's standing workflow, a real bug found by
fuzzing gets its own issue and its own fix PR; only a flaw in the fuzz
test's own assumptions (e.g. an equality helper that doesn't handle NaN) is
fixed here directly.

To run only the fuzz tests:

```sh
pytest -q tests/test_fuzz.py
```

There are no custom pytest markers for fuzz tests; they're ordinary
`@given`-decorated test functions, scoped to one file, so running that file
is the standalone invocation. Hypothesis settings are tuned for CI in the
module-level `_SUPPRESS` settings object (`deadline=None`, `max_examples=150`,
`HealthCheck.too_slow` suppressed) and apply automatically to every test
in the file.

## CI

`.github/workflows/test.yml` runs on every push to `master` and every pull
request targeting `master`. One job (`test`), matrixed over
**Python 3.11, 3.12, and 3.13**. Each matrix run:

1. Checks out the repo (`actions/checkout@v4`).
2. Sets up the matrix Python version (`actions/setup-python@v5`).
3. Installs the package with dev extras: `pip install -e .[dev]`.
4. Lints: `ruff check .`.
5. Tests: `pytest -q`.

Coverage is not enforced in CI (no `coverage run`/coverage threshold step in
the workflow) — the 100% target above is a contributor discipline backed by
the periodic coverage sweeps described in [Coverage](#coverage), checked
manually rather than gated in the pipeline.
