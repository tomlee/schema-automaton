"""omnist — one canonical data model, many formats.

A **Document** is a *tree*: an ordered list of labeled edges (repeated
labels are how arrays appear), held by a :class:`Doc`.  A **Schema** describes
the shape a Document may have, as ``record`` definitions referenced by name.
A field's value side is always exactly one of the seven scalars (``string``,
``integer``, ``number``, ``boolean``, ``date``, ``time``, ``datetime``),
optionally nullable, or a reference to a named record — never a composed
value-domain (no enums, no literal-valued fields). Read a format into a
``Doc``, validate it against a ``Schema``, and write it back to any format.

    from omnist import parse_schema, doc

    s = parse_schema('''
        record Member { "name": string, "role": string }
        record Team   { "name": string, "members" [1,]: Member }
        root Team
    ''')
    s.validate(doc({"name": "X", "members": [{"name": "Ann", "role": "dev"}]})).ok

The model is defined formally in ``docs/design/model.md``.  The implementation
lives in :mod:`omnist.canonical`; this module is its public surface.
"""

from .canonical.deserialize import materialize
from .canonical.document import Doc, doc
from .canonical.formats import (
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
from .canonical.infer import infer
from .canonical.oml import check_oml, read_oml, write_oml
from .canonical.osd import parse_schema, to_osd
from .canonical.registry import Format, formats, get_format, register_format
from .canonical.report import Adjustment, WriteReport, finish_write
from .canonical.schema import (
    BOOLEAN,
    DATE,
    DATETIME,
    INTEGER,
    NUMBER,
    STRING,
    TIME,
    Error,
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
from .errors import (
    DetachedNode,
    DocumentError,
    OmnistError,
    ParseError,
    SchemaError,
    UnsafeXMLWarning,
    WriteError,
)

__version__ = "0.2.11"

__all__ = [
    # errors
    "OmnistError", "SchemaError", "ParseError", "WriteError", "DocumentError",
    "DetachedNode", "UnsafeXMLWarning",
    # document
    "Doc", "doc",
    # schema model
    "Schema", "Record", "Scalar", "Ref", "Field", "ValidationResult", "Error",
    # builders
    "record", "ref", "field", "schema", "nullable", "t",
    "STRING", "INTEGER", "NUMBER", "BOOLEAN", "DATE", "TIME", "DATETIME",
    # osd
    "parse_schema", "to_osd",
    # operations (compatible_with / equivalent / normalize are Schema methods)
    "infer", "materialize",
    # codecs
    "read_json", "write_json", "read_yaml", "write_yaml",
    "read_toml", "write_toml", "read_xml", "write_xml",
    "read_oml", "write_oml",
    "check_json", "check_yaml", "check_toml", "check_xml", "check_oml",
    # adjustment reports
    "WriteReport", "Adjustment", "finish_write",
    # format registry
    "Format", "register_format", "get_format", "formats",
]
