"""Canonical model (design proposal implementation).

A self-contained implementation of the redesigned Document and Schema models
described in ``docs/design/model.md``:

* :mod:`~omnist.canonical.document` — the Document as an ordered list of
  labeled edges, not a dict-with-arrays.
* :mod:`~omnist.canonical.schema` — the Schema as ``Record`` (labels) /
  ``Scalar`` (one of seven, never composed) / ``Ref``, with field
  cardinality, plus conformance.
* :mod:`~omnist.canonical.osd` — the ``record`` text syntax (OSD).
* :mod:`~omnist.canonical.ops` — ``compatible_with`` / ``equivalent``
  / ``normalize`` on the new model.

This package is the implementation of the model; ``import omnist`` is its
public surface.
"""

from .deserialize import materialize
from .document import Doc, doc
from .formats import (
    check_json,
    check_toml,
    check_xml,
    check_yaml,
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
from .ops import compatible_with, equivalent, normalize
from .osd import parse_schema, to_osd
from .registry import Format, formats, get_format, register_format

# register the four built-in formats
from .registry import _register_builtins as _rb  # noqa: E402
from .report import Adjustment, WriteReport, finish_write
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
    Scalar,
    Schema,
    ValidationResult,
    field,
    nullable,
    record,
    ref,
    schema,
    t,
)

_rb()

__all__ = [
    "Doc", "doc",
    "Schema", "Record", "Scalar", "Ref", "Field", "ValidationResult",
    "record", "ref", "field", "schema", "nullable", "t",
    "STRING", "INTEGER", "NUMBER", "BOOLEAN", "DATE", "TIME", "DATETIME",
    "parse_schema", "to_osd",
    "compatible_with", "equivalent", "normalize", "infer", "materialize",
    "read_json", "read_yaml", "read_toml", "read_xml",
    "write_json", "write_yaml", "write_toml", "write_xml",
    "check_json", "check_yaml", "check_toml", "check_xml",
    "WriteReport", "Adjustment", "finish_write",
    "Format", "register_format", "get_format", "formats",
]
