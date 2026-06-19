"""dataspec — one data model, many formats.

A **Document** is plain Python data (objects, arrays, scalars). A **Schema**
describes the shape a Document should have. Read a format into a Document,
validate it against a Schema, and write it back out to any format.

    from dataspec import read_json, write_toml, parse_schema, infer

    data   = read_json('{"name": "Ann", "tags": ["x", "y"]}')
    toml   = write_toml(data)                     # transcode JSON -> TOML

    schema = parse_schema("root { name: string, tags: [string] }")
    schema.validate(data).ok                      # True

    schema2 = infer([data])                       # learn a schema from samples
"""

from .errors import DataspecError, SchemaError, ParseError, WriteError
from .schema import (
    Schema, ValidationResult,
    Type, ScalarType, ArrayType, ObjectType, Field, RefType,
    STRING, INTEGER, NUMBER, BOOLEAN, DATE, TIME, DATETIME,
)
from .dsl import parse_schema, to_dsl
from .infer import infer
from .formats import (
    read_json, write_json,
    read_yaml, write_yaml,
    read_toml, write_toml,
    read_xml, write_xml,
)

__all__ = [
    # errors
    "DataspecError", "SchemaError", "ParseError", "WriteError",
    # schema model
    "Schema", "ValidationResult",
    "Type", "ScalarType", "ArrayType", "ObjectType", "Field", "RefType",
    "STRING", "INTEGER", "NUMBER", "BOOLEAN", "DATE", "TIME", "DATETIME",
    # dsl
    "parse_schema", "to_dsl",
    # operations
    "infer",
    # formats
    "read_json", "write_json", "read_yaml", "write_yaml",
    "read_toml", "write_toml", "read_xml", "write_xml",
]

__version__ = "0.1.0"
