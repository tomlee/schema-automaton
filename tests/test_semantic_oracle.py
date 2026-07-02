"""Bounded, deterministic CI version of the brute-force semantic oracle
(``tools/semantic_oracle.py``, issue #158).

Runs the exact same five checks against the exact same set-theoretic
ground-truth definition (``L(s) = {d in U : s.validate(Doc(d)).ok}``) as
the full tool, just over a much smaller universe and schema family so it
fits comfortably inside the normal test suite -- see the module-level
timing note below for the measured runtime. This is a *third* independent
correctness check on the schema algebra, alongside ``compatible_with``
(Algorithm 4, ``omnist/ops/subschema.py``) and the minimize+isomorphism
Theorem-4 oracle (``omnist/ops/isomorphic.py``, cross-checked in
``tests/test_fuzz.py``) -- see ``docs/testing.md``, "the triple-checked
algebra".

No pytest marker infrastructure is used: at well under a second, this
belongs in the normal test run, not a slow/opt-in lane.
"""

from tools.semantic_oracle import (
    OracleResult,
    build_universe,
    check_compatible_with,
    check_extract,
    check_is_empty,
    check_normalize_prune_preserve_language,
    ground_truth,
    schema_family,
    to_doc,
)

# A deliberately small but still representative universe/family:
# base_max=1 keeps the base universe (root edges over {a,b}, 0-1 per label,
# leaf-or-depth-1 children) at 121 documents; extended_max=(2, 3) adds
# cardinality-2/3 witnesses on top for 337 total -- proportionally the same
# construction as the full tool's (base_max=2, extended_max=(3, 4)), just
# one cardinality notch down at every level. random_count=15 (plus the
# fixed 42 systematic + 3 structural + 14 nullable schemas = 74 total)
# keeps the O(n^2) compatible_with sweep (74^2 = 5,476 pairs) and the
# ground-truth computation (74 * 121 = 8,954 validations) small. The 14
# nullable-vs-non-nullable schemas (schema_family()'s nullable_family())
# are always included regardless of random_count -- they're what the
# mutation self-check in the PR body exercises (dropping the nullable
# check in ops/subschema.py's _scalar_sub), so this bounded test must
# always include them too, not just the full-size tool.
_BASE_MAX = 1
_EXTENDED_MAX = (2, 3)
_RANDOM_COUNT = 15
_SEED = 158


def _run_bounded() -> OracleResult:
    base_nodes, ext_nodes = build_universe(base_max=_BASE_MAX, extended_max=_EXTENDED_MAX)
    base_docs = [to_doc(n) for n in base_nodes]
    ext_docs = [to_doc(n) for n in ext_nodes]
    schemas = schema_family(random_count=_RANDOM_COUNT, seed=_SEED)

    truth = ground_truth(schemas, base_docs)
    ext_truth = ground_truth(schemas, ext_docs)
    doc_labels = [
        frozenset(lbl for lbl, _ in d.edges()) if not d.is_leaf else frozenset()
        for d in base_docs
    ]

    result = OracleResult()
    check_compatible_with(schemas, truth, ext_docs, ext_truth, result)
    check_is_empty(schemas, truth, result)
    check_normalize_prune_preserve_language(schemas, truth, base_docs, result)
    check_extract(schemas, base_docs, truth, doc_labels, result)
    result.counts["base_docs"] = len(base_docs)
    result.counts["extended_docs"] = len(ext_docs)
    result.counts["schemas"] = len(schemas)
    return result


def test_semantic_oracle_bounded_run_finds_zero_definite_bugs():
    """The schema algebra, checked against brute-force enumerated ground
    truth over a small but structurally representative universe: zero
    definite bugs is the only acceptable outcome -- a failure here means
    ``compatible_with``, ``is_empty``, ``normalize``, ``prune``, or
    ``extract`` disagrees with ``validate()`` itself, the strongest kind of
    regression this suite can catch (see ``tools/semantic_oracle.py``'s
    module docstring for why this check is independent of the other two
    algebra oracles)."""
    result = _run_bounded()
    assert result.definite_bugs == [], (
        f"semantic oracle found {len(result.definite_bugs)} definite bug(s): "
        + "; ".join(result.definite_bugs[:5])
    )
    # Sanity on the check actually having run over a non-trivial universe --
    # a regression that made the universe/family accidentally empty would
    # otherwise "pass" this test vacuously.
    assert result.counts["base_docs"] > 50
    assert result.counts["schemas"] >= 60
    assert result.counts["pairs_checked"] == result.counts["schemas"] ** 2
    assert result.counts["is_empty_checked"] == result.counts["schemas"]
    assert result.counts["extract_cases_checked"] > 0


def test_semantic_oracle_bounded_needs_review_is_small():
    """``compatible_with`` False answers that neither the base universe,
    the extended universe, nor any targeted witness can vindicate are
    reported as needs-manual-review, not failures (a bounded-universe
    artifact -- see ``tools/semantic_oracle.py``'s ``check_compatible_with``
    docstring). At this bounded size that set should be empty or very
    small; a large jump would signal the witness heuristics regressed, so
    this is a soft ceiling, not a strict zero requirement."""
    result = _run_bounded()
    assert len(result.needs_review) <= 5
