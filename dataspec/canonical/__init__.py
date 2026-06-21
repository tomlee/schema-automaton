"""Canonical model (design proposal implementation).

A self-contained implementation of the redesigned Document and Schema models
described in ``docs/design/model.md``:

* :mod:`~dataspec.canonical.document` — the Document as an ordered list of
  labeled edges (a Data Tree), not a dict-with-arrays.
* :mod:`~dataspec.canonical.schema` — the Schema as ``Record`` (HLang) /
  ``Union`` (VDom) / ``Ref``, with field cardinality, plus conformance.
* :mod:`~dataspec.canonical.dsl` — the ``record`` / ``union`` text syntax.
* :mod:`~dataspec.canonical.operations` — ``compatible_with`` / ``equivalent``
  / ``normalize`` on the new model.

This lives alongside the current (v0.1) package; it does not replace it yet.
"""

from .document import Doc, doc
from .dsl import parse_schema, to_dsl
from .formats import (
    read_json,
    read_toml,
    read_xml,
    read_yaml,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)
from .infer import infer
from .operations import compatible_with, equivalent, normalize
from .schema import (
    BOOLEAN,
    DATE,
    DATETIME,
    INTEGER,
    NUMBER,
    STRING,
    TIME,
    Field,
    Record,
    Ref,
    Schema,
    Union,
    ValidationResult,
    field,
    record,
    ref,
    schema,
    union,
)

__all__ = [
    "Doc", "doc",
    "Schema", "Record", "Union", "Ref", "Field", "ValidationResult",
    "record", "union", "ref", "field", "schema",
    "STRING", "INTEGER", "NUMBER", "BOOLEAN", "DATE", "TIME", "DATETIME",
    "parse_schema", "to_dsl",
    "compatible_with", "equivalent", "normalize", "infer",
    "read_json", "read_yaml", "read_toml", "read_xml",
    "write_json", "write_yaml", "write_toml", "write_xml",
]
