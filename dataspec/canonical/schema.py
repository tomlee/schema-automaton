"""The Schema model — two state kinds plus naming, per ``docs/design/model.md``.

* **Record** — a closed set of fields, each ``(label, type, cardinality)``.
  Constrained by its child labels (the SA's HLang); cardinality is the
  *unordered* multiplicity of a label.
* **Union** — a value domain: a set of members, each a *kind* (string, integer,
  …), a *literal*, or ``null``.  Constrained by values (the SA's VDom).
* **Ref** — a pointer into the schema's named environment; enables reuse and
  recursion.

A field's ``type`` is a ``Ref`` (to a named record or union) or an inline
``Union``.  There are no inline records and no separate array type — "array" is
just a field with cardinality ``max > 1``.  Validation ignores order.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, NamedTuple, Optional
from typing import Union as _U

from ..errors import SchemaError


class Kind:
    """A scalar kind atom (``string``, ``integer``, …) — a sentinel distinct
    from a string literal, so a Union can hold both unambiguously."""
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Kind) and other.name == self.name

    def __hash__(self) -> int:
        return hash(("Kind", self.name))


STRING = Kind("string")
INTEGER = Kind("integer")
NUMBER = Kind("number")
BOOLEAN = Kind("boolean")
DATE = Kind("date")
TIME = Kind("time")
DATETIME = Kind("datetime")

SCALAR_KINDS = {STRING, INTEGER, NUMBER, BOOLEAN, DATE, TIME, DATETIME}
_KIND_BY_NAME = {k.name: k for k in SCALAR_KINDS}


def kind_by_name(name: str) -> Kind:
    try:
        return _KIND_BY_NAME[name]
    except KeyError:
        raise SchemaError(f"unknown scalar kind {name!r}") from None


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Union:
    """A value domain: kinds ∪ literals ∪ (null?)."""

    __slots__ = ("kinds", "literals", "null")

    def __init__(self, kinds=(), literals=(), null: bool = False) -> None:
        ks = frozenset(kinds)
        bad = ks - SCALAR_KINDS
        if bad:
            raise SchemaError(f"unknown scalar kind(s): {sorted(repr(b) for b in bad)}")
        self.kinds: frozenset = ks
        self.literals: frozenset = frozenset(literals)
        self.null: bool = bool(null)
        if not (self.kinds or self.literals or self.null):
            raise SchemaError("a union must have at least one member")

    def __repr__(self) -> str:
        parts = [k.name for k in sorted(self.kinds, key=lambda k: k.name)]
        parts += [repr(v) for v in sorted(self.literals, key=repr)]
        if self.null:
            parts.append("null")
        return "union{" + ", ".join(parts) + "}"

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, Union) and other.kinds == self.kinds
                and other.literals == self.literals and other.null == self.null)

    def __hash__(self) -> int:
        return hash((Union, self.kinds, self.literals, self.null))


class Ref:
    """A reference to a named definition (record or union)."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"ref({self.name})"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Ref) and other.name == self.name

    def __hash__(self) -> int:
        return hash((Ref, self.name))


Type = _U[Ref, Union]


class Field:
    """One labeled edge of a record: ``label`` of ``type``, occurring
    ``[min, max]`` times (``max=None`` is unbounded)."""

    __slots__ = ("label", "type", "min", "max")

    def __init__(self, label: str, type: Type, min: int = 1,
                 max: Optional[int] = 1) -> None:
        if not isinstance(type, (Ref, Union)):
            raise SchemaError(f"field {label!r} type must be a Ref or Union, got {type!r}")
        if min < 0 or (max is not None and max < min):
            raise SchemaError(f"field {label!r} has an invalid cardinality [{min},{max}]")
        self.label = label
        self.type = type
        self.min = min
        self.max = max

    def cardinality_str(self) -> str:
        if (self.min, self.max) == (1, 1):
            return "exactly 1"
        if (self.min, self.max) == (0, 1):
            return "0 or 1"
        if self.max is None:
            return f"at least {self.min}"
        return f"between {self.min} and {self.max}"

    def __repr__(self) -> str:
        hi = "" if self.max is None else self.max
        return f"Field({self.label!r}[{self.min},{hi}]: {self.type!r})"


class Record:
    """A closed set of named fields (constrained by its child labels)."""

    __slots__ = ("fields",)

    def __init__(self, fields: List[Field]) -> None:
        self.fields = list(fields)
        seen = set()
        for f in self.fields:
            if f.label in seen:
                raise SchemaError(f"duplicate field label {f.label!r} in a record")
            seen.add(f.label)

    def field(self, label: str) -> Optional[Field]:
        for f in self.fields:
            if f.label == label:
                return f
        return None

    def __repr__(self) -> str:
        return "record{" + ", ".join(repr(f) for f in self.fields) + "}"


Definition = _U[Record, Union]


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

class Error(NamedTuple):
    path: str
    message: str


class ValidationResult:
    def __init__(self) -> None:
        self.errors: List[Error] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, path: str, message: str) -> None:
        self.errors.append(Error(path, message))

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        if self.ok:
            return "valid"
        return "invalid:\n" + "\n".join(f"  at {e.path}: {e.message}" for e in self.errors)

    def __repr__(self) -> str:
        return f"ValidationResult(ok={self.ok}, errors={len(self.errors)})"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class Schema:
    """A schema: a root reference plus an environment of named definitions."""

    def __init__(self, root: Ref, env: Optional[Dict[str, Definition]] = None) -> None:
        if not isinstance(root, Ref):
            raise SchemaError("a schema root must be a Ref to a named record")
        self.root = root
        self.env: Dict[str, Definition] = dict(env or {})
        self.check_refs()

    def resolve(self, t: Type) -> Definition:
        """Follow a chain of Refs to a concrete Record or Union."""
        seen = set()
        while isinstance(t, Ref):
            if t.name in seen:
                raise SchemaError(f"cyclic reference chain at {t.name!r}")
            seen.add(t.name)
            if t.name not in self.env:
                raise SchemaError(f"unknown type {t.name!r}")
            t = self.env[t.name]
        return t

    def check_refs(self) -> None:
        def walk(t: Type) -> None:
            if isinstance(t, Ref):
                if t.name not in self.env:
                    raise SchemaError(f"unknown type {t.name!r}")
        walk(self.root)
        for d in self.env.values():
            if isinstance(d, Record):
                for f in d.fields:
                    walk(f.type)
        # the root must resolve to a record (single-rooted)
        if not isinstance(self.resolve(self.root), Record):
            raise SchemaError("the schema root must resolve to a record")

    # -- validation -----------------------------------------------------
    def validate(self, doc) -> ValidationResult:
        from .document import Doc
        if not isinstance(doc, Doc):
            raise TypeError("validate() expects a Doc; wrap your data with doc(...)")
        res = ValidationResult()
        self._conform(doc, self.root, res)
        return res

    def accepts(self, doc) -> bool:
        return self.validate(doc).ok

    def _conform(self, doc, t: Type, res: ValidationResult) -> None:
        d = self.resolve(t)
        if isinstance(d, Union):
            self._conform_union(doc, d, res)
        else:
            self._conform_record(doc, d, res)

    def _conform_union(self, doc, u: Union, res: ValidationResult) -> None:
        if not doc.is_leaf:
            res.add(doc.path, f"expected a value ({u}), got an object")
            return
        if not value_in_union(doc.value, u):
            res.add(doc.path, f"{doc.value!r} is not in {u}")

    def _conform_record(self, doc, rec: Record, res: ValidationResult) -> None:
        if doc.is_leaf:
            res.add(doc.path, "expected an object, got a value")
            return
        counts: Dict[str, int] = {}
        for label, child in doc.edges():
            counts[label] = counts.get(label, 0) + 1
            f = rec.field(label)
            if f is None:
                res.add(child.path, "unexpected field")
            else:
                self._conform(child, f.type, res)
        for f in rec.fields:
            c = counts.get(f.label, 0)
            if c < f.min or (f.max is not None and c > f.max):
                res.add(doc.path,
                        f"field {f.label!r} occurs {c} time(s), expected {f.cardinality_str()}")

    # -- serialization --------------------------------------------------
    def to_dsl(self) -> str:
        from .dsl import to_dsl
        return to_dsl(self)

    def __repr__(self) -> str:
        return f"Schema(root={self.root!r}, env={list(self.env)})"


# ---------------------------------------------------------------------------
# Value-domain membership
# ---------------------------------------------------------------------------

def value_in_union(value: Any, u: Union) -> bool:
    if value is None:
        return u.null
    if any(_same_literal(value, lit) for lit in u.literals):
        return True
    return any(matches_kind(value, k) for k in u.kinds)


def _same_literal(a: Any, b: Any) -> bool:
    # Exact match that never lets True == 1 (or 1 == True) cross the bool line.
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def matches_kind(value: Any, k: Kind) -> bool:
    if k == STRING:
        return isinstance(value, str)
    if k == BOOLEAN:
        return isinstance(value, bool)
    if k == INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if k == NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if k == DATE:
        if isinstance(value, _dt.datetime):
            return False
        if isinstance(value, _dt.date):
            return True
        return _is_iso(value, _dt.date)
    if k == TIME:
        if isinstance(value, _dt.time):
            return True
        return _is_iso(value, _dt.time)
    if k == DATETIME:
        if isinstance(value, _dt.datetime):
            return True
        return _is_iso(value, _dt.datetime)
    return False


def _is_iso(value: Any, cls) -> bool:
    if not isinstance(value, str):
        return False
    try:
        cls.fromisoformat(value)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Python builders
# ---------------------------------------------------------------------------

def union(*members: Any, null: bool = False) -> Union:
    """Build a Union from kind atoms and/or literal values.

    ``union(STRING, null=True)`` — any string, or null.
    ``union("auto", "manual")`` — exactly those two literals.
    ``union(INTEGER, "unknown")`` — any integer, or the literal ``"unknown"``.
    """
    kinds = [m for m in members if isinstance(m, Kind)]
    literals = [m for m in members if not isinstance(m, Kind)]
    return Union(kinds=kinds, literals=literals, null=null)


def field(label: str, type: Type, min: int = 1, max: Optional[int] = 1) -> Field:
    return Field(label, type, min, max)


def record(*fields: Field) -> Record:
    return Record(list(fields))


def ref(name: str) -> Ref:
    return Ref(name)


def schema(root: _U[Ref, str], **env: Definition) -> Schema:
    r = Ref(root) if isinstance(root, str) else root
    return Schema(r, env)
