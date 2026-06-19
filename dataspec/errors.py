"""Exceptions used across dataspec."""


class DataspecError(Exception):
    """Base class for all dataspec errors."""


class SchemaError(DataspecError):
    """The schema text or structure is invalid."""


class ParseError(DataspecError):
    """A document could not be read from its format (outside the supported profile)."""


class WriteError(DataspecError):
    """A document cannot be represented in the target format."""
