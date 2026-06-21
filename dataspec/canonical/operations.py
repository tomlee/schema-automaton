"""Schema operations on the canonical model.

* ``compatible_with(a, b)`` — every document ``a`` accepts is also accepted by
  ``b`` (``a`` is a subschema / ``b`` is backward-compatible).
* ``equivalent(a, b)`` — both accept exactly the same documents.
* ``normalize(s)`` — merge structurally-identical named definitions.

All checks are structural and order-free, and handle recursion co-inductively.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from .schema import (
    INTEGER,
    NUMBER,
    Field,
    Kind,
    Record,
    Ref,
    Schema,
    Union,
    _same_literal,  # type-aware literal equality
    matches_kind,
)

# ---------------------------------------------------------------------------
# compatible_with  /  equivalent
# ---------------------------------------------------------------------------

def compatible_with(a: Schema, b: Schema) -> bool:
    return _sub(a, a.root, b, b.root, set())


def equivalent(a: Schema, b: Schema) -> bool:
    return compatible_with(a, b) and compatible_with(b, a)


def _sub(sa: Schema, ta, sb: Schema, tb, seen: Set[Tuple[int, int]]) -> bool:
    da = sa.resolve(ta)
    db = sb.resolve(tb)
    key = (id(da), id(db))
    if key in seen:
        return True                       # co-inductive: assume on a cycle
    seen = seen | {key}
    if isinstance(da, Union) and isinstance(db, Union):
        return _union_sub(da, db)
    if isinstance(da, Record) and isinstance(db, Record):
        return _record_sub(sa, da, sb, db, seen)
    return False                          # a value vs an object — never compatible


def _union_sub(a: Union, b: Union) -> bool:
    if a.null and not b.null:
        return False
    for k in a.kinds:
        if not _kind_in(k, b.kinds):
            return False
    for lit in a.literals:
        in_lits = any(_same_literal(lit, bl) for bl in b.literals)
        in_kinds = any(matches_kind(lit, k) for k in b.kinds)
        if not (in_lits or in_kinds):
            return False
    return True


def _kind_in(k: Kind, kinds) -> bool:
    if k in kinds:
        return True
    if k == INTEGER and NUMBER in kinds:
        return True                       # an integer is also a number
    return False


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


# ---------------------------------------------------------------------------
# normalize — merge structurally identical named definitions
# ---------------------------------------------------------------------------

def normalize(s: Schema) -> Schema:
    groups: Dict[tuple, List[str]] = {}
    for name, d in s.env.items():
        groups.setdefault(_struct_key(d), []).append(name)
    rep: Dict[str, str] = {}
    for names in groups.values():
        keep = sorted(names)[0]
        for n in names:
            rep[n] = keep
    new_env: Dict[str, Any] = {}
    for name, d in s.env.items():
        if rep[name] == name:
            new_env[name] = _remap(d, rep)
    new_root = Ref(rep.get(s.root.name, s.root.name))
    return Schema(new_root, new_env)


def _struct_key(d) -> tuple:
    if isinstance(d, Union):
        kinds = tuple(sorted(k.name for k in d.kinds))
        lits = tuple(sorted(repr(v) for v in d.literals))
        return ("union", kinds, lits, d.null)
    fields = tuple((f.label, f.min, f.max, _type_key(f.type)) for f in d.fields)
    return ("record", fields)


def _type_key(t) -> tuple:
    if isinstance(t, Ref):
        return ("ref", t.name)
    return _struct_key(t)


def _remap(d, rep: Dict[str, str]):
    if isinstance(d, Union):
        return d
    return Record([Field(f.label, _remap_type(f.type, rep), f.min, f.max)
                   for f in d.fields])


def _remap_type(t, rep: Dict[str, str]):
    if isinstance(t, Ref):
        return Ref(rep.get(t.name, t.name))
    return t
