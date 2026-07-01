"""Subschema compatibility and equivalence.

Implements the paper's Algorithm 4 (SubschemaSA) restricted to omnist's
counting cardinality languages; ``equivalent`` is bidirectional inclusion.
"""

from __future__ import annotations

from typing import Optional, Set, Tuple

from ..schema import Record, Scalar, Schema


def compatible_with(a: Schema, b: Schema) -> bool:
    """True if every document ``a`` accepts is also accepted by ``b``
    (``a`` is a subschema / ``b`` is backward-compatible)."""
    return _sub(a, a.root, b, b.root, set())


def equivalent(a: Schema, b: Schema) -> bool:
    """True if both schemas accept exactly the same documents."""
    return compatible_with(a, b) and compatible_with(b, a)


def _sub(sa: Schema, ta, sb: Schema, tb, seen: Set[Tuple[int, int]]) -> bool:
    da = sa.resolve(ta)
    db = sb.resolve(tb)
    key = (id(da), id(db))
    if key in seen:
        return True                       # assume compatible when a cycle repeats
    seen = seen | {key}
    if isinstance(da, Scalar) and isinstance(db, Scalar):
        return _scalar_sub(da, db)
    if isinstance(da, Record) and isinstance(db, Record):
        return _record_sub(sa, da, sb, db, seen)
    return False                          # a value vs an object — never compatible


def _scalar_sub(a: Scalar, b: Scalar) -> bool:
    if a.nullable and not b.nullable:
        return False
    if a.name == b.name:
        return True
    return a.name == "integer" and b.name == "number"   # the one subset relation


def _record_sub(sa: Schema, a: Record, sb: Schema, b: Record,
                seen: Set[Tuple[int, int]]) -> bool:
    # Every label A may emit must be allowed by B, with a cardinality range
    # B's covers and a type B accepts.
    for fa in a.fields:
        if fa.max == 0:
            continue                      # A never emits this label
        fb = b.field(fa.label)
        if fb is None:
            return False                  # B is closed and has no such field
        if not (fb.min <= fa.min and _le(fa.max, fb.max)):
            return False                  # [fa.min,fa.max] not a subset of B's range
        if not _sub(sa, fa.type, sb, fb.type, seen):
            return False
    # Every label B *requires* must be guaranteed by A.
    for fb in b.fields:
        if fb.min >= 1:
            fa = a.field(fb.label)
            if fa is None or fa.min < fb.min:
                return False
    return True


def _le(x: Optional[int], y: Optional[int]) -> bool:
    """x <= y, treating None as +infinity (unbounded max)."""
    if y is None:
        return True
    if x is None:
        return False
    return x <= y
