# Getting Started

## Requirements

* **Python 3.11+** (TOML loading uses the standard-library `tomllib`, added in
  3.11; on older Pythons install the `tomli` backport).
* No required third-party packages for the core library or JSON support.
* Optional:
  * **PyYAML** — only if you load YAML (`tree_from_yaml`).
  * **pytest** — only to run the test suite.

## Setup

Clone the repository and (optionally) create a virtual environment:

```bash
git clone https://github.com/tomlee/schema-automaton.git
cd schema-automaton

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

# Optional extras
pip install pytest pyyaml
```

There is nothing to compile or build — the library is pure Python under `src/`.

> **Importing the library.** The package currently lives under `src/`, so the
> examples import it as `from src import ...` when run from the repository root.
> If you copy `src/` into your own project, rename or place it on your
> `PYTHONPATH` and import accordingly.

## Run the test suite

```bash
python -m pytest tests/ -q
```

You should see **154 passing tests**. They cover:

* `tests/test_paper.py` — reproduces the CIKM 2010 worked examples (SA1/SA2/SA3
  equivalence, subschema testing, extraction, irrational-state removal).
* `tests/test_formats.py` — the unordered `MapModel`, the JSON/YAML/TOML
  loaders, schema inference, validation diagnostics, and JSON-Schema export.
* `tests/test_dsl.py` — the textual Schema DSL (parsing, serialization,
  round-trip, errors) and the `conforms_to` conformance algorithm.

## Run the demos

Each demo is self-contained and prints a narrated walkthrough. Run them from the
repository root:

```bash
python demos/01_xml_paper_examples.py      # the paper's XML schema computations
python demos/02_infer_and_validate_json.py # infer a schema, validate, export
python demos/03_cross_format.py            # one schema validates JSON / YAML / TOML
python demos/04_schema_versioning.py       # backward-compatibility via subschema
python demos/05_subschema_extraction.py    # trim a schema to the keys a client needs
python demos/06_unions_and_nullable.py     # scalar unions + nullable objects/arrays
python demos/07_schema_dsl.py              # textual schema DSL + conformance checking
```

Or run the quick combined tour:

```bash
python main.py
```

### A note on Windows consoles

The demos print Unicode (`§`, `≡`, `⊆`, `ε`). They force UTF-8 output, but if
your terminal still mojibakes, set:

```bash
set PYTHONIOENCODING=utf-8     # cmd
$env:PYTHONIOENCODING="utf-8"  # PowerShell
```

## Next steps

* Read the [Data Model Specification](data-model.md) to understand Data Trees
  and Schema Automata.
* Follow the [User Guide](user-guide.md) for task-oriented recipes.
