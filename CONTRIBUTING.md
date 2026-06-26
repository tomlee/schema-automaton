# Contributing

Omnist is **alpha** and the API can still change, but the workflow below is
the real one this project uses — not a placeholder.

## Setup

```bash
git clone https://github.com/omnist-dev/omnist.git
cd omnist
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]      # core + all formats + pytest + ruff
```

## Workflow

Changes go through a pull request, not a direct push to `master`:

1. Create a branch: `git checkout -b <type>/<short-description>`, e.g.
   `fix/registry-thread-safety` or `docs/plugins-guide`. Prefixes in use:
   `fix`, `feat`, `docs`, `test`, `chore`, `ci`.
2. Make the change. Keep a PR to one coherent change set — a batch of
   doc fixes, one bug fix, one feature — not an unrelated grab-bag.
3. Before pushing, run both gates locally (CI runs the same two):
   ```bash
   ruff check .
   pytest -q
   ```
4. Push the branch and open a PR (`gh pr create`) describing the *intent*
   of the change, not just a restatement of the diff.
5. Branch protection on `master` requires the `test (3.11)` / `test (3.12)` /
   `test (3.13)` checks to pass (and the branch to be up to date) before
   merging. Squash-merge once green.

## Code style

- `ruff` is the source of truth (`pyproject.toml`'s `[tool.ruff]`); fix
  whatever it flags rather than arguing with it locally.
- This codebase uses `;`-joined one-liners and one-line class/def bodies in a
  few places (notably `osd.py`) — that's intentional (see the `E701`/`E702`
  ignores in `pyproject.toml`), not something to "clean up" in an unrelated PR.
- No type checker is wired in yet; `omnist/py.typed` exists so callers'
  type checkers trust the package's hints, but nothing currently verifies the
  hints themselves.

## Tests

- Every new function or fixed bug gets a test. Tests that assert *errors* are
  raised matter as much as tests for the happy path — see
  `tests/test_canonical.py`'s `TestOsdRobustness` and `TestValidation` classes
  for the pattern: verify the actual exception type and message against the
  real code before writing the assertion, don't guess at what it "should" say.
- `examples/*.py` are documentation with executable code, not throwaway
  demos. `tests/test_examples.py` runs every one of them and will fail CI if
  any of them breaks — if you change something an example depends on (a
  function signature, example data referenced elsewhere in the docs), run the
  examples yourself before opening the PR, don't rely on CI to find it first.
- If you touch a doc's code block, run it. A doc claiming output that the
  code doesn't actually produce is worse than no example at all.

## Releases

Tags follow `v<version>` matching `pyproject.toml`'s `version`. This project
is still pre-1.0 alpha (`0.1.1aN`), so a version bump is just a marker for
"a meaningful batch of work landed," not a stability promise — bump it,
update `CHANGELOG.md`, tag, push the tag. Not published to PyPI yet; see
the README's Status section for the current plan.

## Reporting issues

<https://github.com/omnist-dev/omnist/issues>
