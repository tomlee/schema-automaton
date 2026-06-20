"""dataspec — one data model, many formats.

A **Document** is a tree of objects, arrays, and scalars, held by a :class:`Doc`.
A **Schema** describes the shape a Document should have. Read a format into a
Doc, validate it against a Schema, and write it back out to any format.

    from dataspec import Doc, obj, arr, schema, t

    d = Doc.from_json('{"name": "Ann", "tags": ["x", "y"]}')
    d.to_toml()                                   # transcode JSON -> TOML

    s = schema(obj(name=t.string, tags=arr(t.string)))
    s.validate(d).ok                              # True

The low-level functional codecs (``read_json`` / ``write_toml`` / …) operate on
plain Python and are still available; ``Doc`` is the object layer over them.
"""

from .builder import (
    arr,
    enum,
    mapping,
    nullable,
    obj,
    optional,
    ref,
    schema,
    t,
)
from .document import Doc, doc
from .dsl import parse_schema, to_dsl
from .errors import (
    DataspecError,
    DetachedNode,
    DocumentError,
    ParseError,
    SchemaError,
    UnsafeXMLWarning,
    WriteError,
)
from .formats import (
    Format,
    check_json,
    check_toml,
    check_xml,
    check_yaml,
    formats,
    get_format,
    read_json,
    read_toml,
    read_xml,
    read_yaml,
    register_format,
    write_json,
    write_toml,
    write_xml,
    write_yaml,
)
from .infer import infer
from .report import Adjustment, WriteReport, finish_write
from .schema import (
    BOOLEAN,
    DATE,
    DATETIME,
    INTEGER,
    NUMBER,
    STRING,
    TIME,
    AnyType,
    ArrayType,
    Error,
    Field,
    ObjectType,
    RefType,
    ScalarType,
    Schema,
    Type,
    ValidationResult,
)

__all__ = [
    # errors
    "DataspecError", "SchemaError", "ParseError", "WriteError", "DocumentError",
    "DetachedNode", "UnsafeXMLWarning",
    # serialization reports
    "WriteReport", "Adjustment", "finish_write",
    # document (data DOM)
    "Doc", "doc",
    # schema model
    "Schema", "ValidationResult", "Error",
    "Type", "AnyType", "ScalarType", "ArrayType", "ObjectType", "Field", "RefType",
    "STRING", "INTEGER", "NUMBER", "BOOLEAN", "DATE", "TIME", "DATETIME",
    # schema builder
    "obj", "arr", "mapping", "ref", "enum", "optional", "nullable", "schema", "t",
    # dsl
    "parse_schema", "to_dsl",
    # operations
    "infer",
    # format registry
    "Format", "register_format", "get_format", "formats",
    # functional codecs
    "read_json", "write_json", "check_json",
    "read_yaml", "write_yaml", "check_yaml",
    "read_toml", "write_toml", "check_toml",
    "read_xml", "write_xml", "check_xml",
]

__version__ = "0.1.0a1"
