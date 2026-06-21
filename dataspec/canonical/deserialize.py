"""Schema-directed deserialization: upgrade a freshly-read node's leaf values
to match a :class:`~dataspec.canonical.schema.Schema`'s declared scalars.

Readers (``read_json``, etc.) hand back text-shaped values: JSON/YAML/TOML
have no ``date``/``time`` type, so a temporal field arrives as an ISO-8601
string; a whole-number ``float`` may need to become an ``int`` (or vice
versa) to match what the schema declares. :func:`materialize` converts each
leaf **only when the conversion is value-exact** -- ``"2024-01-01" -> date``,
``1.0 -> int 1`` -- and raises :class:`~dataspec.errors.ParseError` when it
isn't -- ``1.5 -> integer``, ``"abc" -> integer``.

This is unambiguous by construction: every field has exactly one candidate
scalar (see ``docs/design/model.md``), so there's never a choice between
candidate representations -- only "does this value exactly fit the one
scalar declared, or not."

Shape problems (a missing field, an unexpected field, the wrong cardinality)
are left to :meth:`Schema.validate`, not raised here -- :func:`materialize`
only ever touches values whose field type it can identify; anything it
doesn't recognize is passed through unchanged for ``validate`` to flag.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from ..errors import ParseError
from .schema import Record, Scalar, Schema

_TEMPORAL_CLASS = {"date": _dt.date, "time": _dt.time, "datetime": _dt.datetime}


def materialize(node: Any, schema: Schema) -> Any:
    """A copy of ``node`` with leaf values upgraded to match ``schema``."""
    return _materialize_type(node, schema, schema.root, "$")


def _materialize_type(node: Any, schema: Schema, t: Any, path: str) -> Any:
    d = schema.resolve(t)
    if isinstance(d, Scalar):
        return _materialize_scalar(node, d, path)
    return _materialize_record(node, schema, d, path)


def _materialize_record(node: Any, schema: Schema, rec: Record, path: str) -> Any:
    if not isinstance(node, list):
        return node                       # a shape mismatch -- validate()'s job
    out = []
    counts: dict = {}
    for label, child in node:
        i = counts.get(label, 0)
        counts[label] = i + 1
        p = f"{path}.{label}" if i == 0 else f"{path}.{label}[{i}]"
        f = rec.field(label)
        if f is None:
            out.append((label, child))    # an unexpected field -- validate()'s job
        else:
            out.append((label, _materialize_type(child, schema, f.type, p)))
    return out


def _materialize_scalar(value: Any, s: Scalar, path: str) -> Any:
    if value is None or isinstance(value, list):
        return value                      # null, or a shape mismatch -- validate()'s job
    if s.name == "string":
        if isinstance(value, str):
            return value
    elif s.name == "boolean":
        if isinstance(value, bool):
            return value
    elif s.name == "integer":
        if isinstance(value, bool):
            pass
        elif isinstance(value, int):
            return value
        elif isinstance(value, float) and value.is_integer():
            return int(value)
    elif s.name == "number":
        if isinstance(value, bool):
            pass
        elif isinstance(value, (int, float)):
            return float(value)
    elif s.name in _TEMPORAL_CLASS:
        converted = _materialize_temporal(value, s.name)
        if converted is not _SENTINEL:
            return converted
    raise ParseError(f"{path}: {value!r} cannot be read as {s.name} "
                     "(not a value-exact conversion)")


_SENTINEL = object()


def _materialize_temporal(value: Any, name: str) -> Any:
    cls = _TEMPORAL_CLASS[name]
    if isinstance(value, cls):
        if name == "date" and isinstance(value, _dt.datetime):
            return _SENTINEL               # datetime is a date subclass -- not this kind
        return value
    if not isinstance(value, str):
        return _SENTINEL
    try:
        parsed = cls.fromisoformat(value)
    except ValueError:
        return _SENTINEL
    if name == "datetime" and _is_iso(value, _dt.date):
        return _SENTINEL                  # a bare date string is not a datetime
    return parsed


def _is_iso(value: str, cls) -> bool:
    try:
        cls.fromisoformat(value)
        return True
    except ValueError:
        return False
