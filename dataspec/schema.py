"""The schema model and validation.

A **Document** is just plain Python data — `dict`, `list`, `str`, `int`,
`float`, `bool`, `None`, and `datetime.date` / `.time` / `.datetime`.  There is
no custom node type; you work with the data directly.

A **Schema** describes the shape a Document should have.  It is built from three
kinds of **types** that mirror the data:

    object   — keyed fields (a dict)         -> ObjectType
    array    — an ordered list               -> ArrayType
    scalar   — a single value                -> ScalarType

Named types (with recursion) are supported via `RefType` and `Schema.types`.

`schema.validate(data)` returns a `ValidationResult` with the verdict and
path-aware errors.  The comparison methods (`equivalent`, `compatible_with`,
`normalize`) live here too — there is no "algorithm" surface; they are just
things a Schema can do.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Set, Tuple

from .errors import SchemaError


# Scalar kind names (null is handled by `nullable`, not a kind).
STRING = "string"
INTEGER = "integer"
NUMBER = "number"
BOOLEAN = "boolean"
DATE = "date"
TIME = "time"
DATETIME = "datetime"

SCALAR_KINDS = {STRING, INTEGER, NUMBER, BOOLEAN, DATE, TIME, DATETIME}


# ===========================================================================
# Validation result
# ===========================================================================

class ValidationResult:
    def __init__(self) -> None:
        self.errors: List[Tuple[str, str]] = []  # (path, message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        if self.ok:
            return "valid"
        return "invalid:\n" + "\n".join(f"  at {p}: {m}" for p, m in self.errors)

    def __repr__(self) -> str:
        return f"ValidationResult(ok={self.ok}, errors={len(self.errors)})"


# ===========================================================================
# Types
# ===========================================================================

class Type:
    """Base class for schema types. Any type may be `nullable` (also accepts null)."""
    kind: str = ""
    nullable: bool = False


class ScalarType(Type):
    """A single value: one or more scalar kinds, optionally nullable / enum."""
    kind = "scalar"

    def __init__(self, kinds, nullable: bool = False, enum: Optional[Set[Any]] = None) -> None:
        ks = set(kinds)
        bad = ks - SCALAR_KINDS
        if bad:
            raise SchemaError(f"unknown scalar kind(s): {sorted(bad)}")
        self.kinds: Set[str] = ks
        self.nullable = nullable
        self.enum: Optional[frozenset] = frozenset(enum) if enum is not None else None

    def __repr__(self) -> str:
        if self.enum is not None:
            body = "enum" + repr(sorted(self.enum))
        else:
            body = "|".join(sorted(self.kinds)) or "?"
        return f"scalar({body}{'?' if self.nullable else ''})"


class ArrayType(Type):
    """An ordered list of `item`, with a length between `min` and `max`."""
    kind = "array"

    def __init__(self, item: Type, min: int = 0, max: Optional[int] = None,
                 nullable: bool = False) -> None:
        self.item = item
        self.min = min
        self.max = max  # None = unbounded
        self.nullable = nullable

    def __repr__(self) -> str:
        hi = "" if self.max is None else self.max
        return f"array({self.item!r})[{self.min},{hi}]"


class Field:
    def __init__(self, type: Type, required: bool) -> None:
        self.type = type
        self.required = required


class ObjectType(Type):
    """A keyed record: named fields (required/optional), optionally open."""
    kind = "object"

    def __init__(self, fields: Dict[str, Field], open: bool = False,
                 nullable: bool = False) -> None:
        self.fields = fields
        self.open = open
        self.nullable = nullable

    @staticmethod
    def of(required: Dict[str, Type] = None, optional: Dict[str, Type] = None,
           open: bool = False) -> "ObjectType":
        fields: Dict[str, Field] = {}
        for k, t in (required or {}).items():
            fields[k] = Field(t, True)
        for k, t in (optional or {}).items():
            fields[k] = Field(t, False)
        return ObjectType(fields, open)

    def required_keys(self) -> Set[str]:
        return {k for k, f in self.fields.items() if f.required}

    def __repr__(self) -> str:
        return f"object({sorted(self.fields)}{', open' if self.open else ''})"


class RefType(Type):
    """A reference to a named type (enables reuse and recursion)."""
    kind = "ref"

    def __init__(self, name: str, nullable: bool = False) -> None:
        self.name = name
        self.nullable = nullable

    def __repr__(self) -> str:
        return f"ref({self.name}{'?' if self.nullable else ''})"


# Convenience scalar builders
def string(nullable=False): return ScalarType({STRING}, nullable)
def integer(nullable=False): return ScalarType({INTEGER}, nullable)
def number(nullable=False): return ScalarType({NUMBER}, nullable)
def boolean(nullable=False): return ScalarType({BOOLEAN}, nullable)
def date(nullable=False): return ScalarType({DATE}, nullable)
def time(nullable=False): return ScalarType({TIME}, nullable)
def datetime(nullable=False): return ScalarType({DATETIME}, nullable)
def enum(*values, nullable=False): return ScalarType({STRING}, nullable, set(values))


# ===========================================================================
# Schema
# ===========================================================================

class Schema:
    """A schema: a root type plus any named types (for reuse / recursion)."""

    def __init__(self, root: Type, types: Optional[Dict[str, Type]] = None) -> None:
        self.root = root
        self.types: Dict[str, Type] = types or {}

    # -- resolution -----------------------------------------------------
    def resolve(self, t: Type) -> Type:
        """Follow a chain of named-type references to a concrete type."""
        return self.peel(t)[0]

    def peel(self, t: Type) -> Tuple[Type, bool]:
        """Resolve refs to a concrete type, OR-ing nullability along the chain.

        Returns (concrete_type, nullable) so a `Ref?` makes the position nullable
        without mutating the shared named type.
        """
        nullable = t.nullable
        seen = set()
        while isinstance(t, RefType):
            if t.name in seen:
                raise SchemaError(f"cyclic type alias chain at {t.name!r}")
            seen.add(t.name)
            if t.name not in self.types:
                raise SchemaError(f"unknown type {t.name!r}")
            t = self.types[t.name]
            nullable = nullable or t.nullable
        return t, nullable

    # -- validation -----------------------------------------------------
    def validate(self, data: Any) -> ValidationResult:
        """Check a Document (plain Python data) against this schema."""
        result = ValidationResult()
        self._check(data, self.root, "$", result)
        return result

    def accepts(self, data: Any) -> bool:
        return self.validate(data).ok

    def _check(self, data: Any, t: Type, path: str, res: ValidationResult) -> None:
        t, nullable = self.peel(t)
        if data is None:
            if not nullable:
                res.errors.append((path, "null not allowed here"))
            return
        if isinstance(t, ObjectType):
            self._check_object(data, t, path, res)
        elif isinstance(t, ArrayType):
            self._check_array(data, t, path, res)
        elif isinstance(t, ScalarType):
            self._check_scalar(data, t, path, res)
        else:  # pragma: no cover
            res.errors.append((path, f"unhandled type {t!r}"))

    def _check_object(self, data, t: ObjectType, path, res) -> None:
        if not isinstance(data, dict):
            res.errors.append((path, f"expected object, got {_typename(data)}"))
            return
        for key, field in t.fields.items():
            if key in data:
                self._check(data[key], field.type, _join(path, key), res)
            elif field.required:
                res.errors.append((path, f"missing required field {key!r}"))
        if not t.open:
            extra = [k for k in data if k not in t.fields]
            for k in extra:
                res.errors.append((_join(path, k), "unexpected field"))

    def _check_array(self, data, t: ArrayType, path, res) -> None:
        if not isinstance(data, list):
            res.errors.append((path, f"expected array, got {_typename(data)}"))
            return
        n = len(data)
        if n < t.min or (t.max is not None and n > t.max):
            bound = f"{t.min}.." + ("∞" if t.max is None else str(t.max))
            res.errors.append((path, f"array length {n} not in {bound}"))
        for i, item in enumerate(data):
            self._check(item, t.item, f"{path}[{i}]", res)

    def _check_scalar(self, data, t: ScalarType, path, res) -> None:
        if t.enum is not None:
            if data not in t.enum:
                res.errors.append((path, f"{data!r} not one of {sorted(t.enum)}"))
            return
        if not _scalar_matches(data, t.kinds):
            res.errors.append((path, f"expected {'|'.join(sorted(t.kinds))}, "
                                     f"got {_typename(data)}"))

    # -- comparison -----------------------------------------------------
    def compatible_with(self, other: "Schema") -> bool:
        """True if every document this schema accepts is also accepted by
        `other` (i.e. this schema is a subset / `other` is backward-compatible)."""
        return _subtype(self, self.root, other, other.root, set())

    def equivalent(self, other: "Schema") -> bool:
        """True if both schemas accept exactly the same documents."""
        return self.compatible_with(other) and other.compatible_with(self)

    def normalize(self) -> "Schema":
        """Return an equivalent schema with structurally-identical named types
        merged (a simple canonical form)."""
        # group named types by structural key
        groups: Dict[tuple, List[str]] = {}
        for name, t in self.types.items():
            groups.setdefault(_struct_key(self, t, set()), []).append(name)
        # map each name to a representative
        rep: Dict[str, str] = {}
        for names in groups.values():
            keep = sorted(names)[0]
            for n in names:
                rep[n] = keep
        new_types = {}
        for name, t in self.types.items():
            if rep[name] == name:
                new_types[name] = _remap_refs(t, rep)
        new_root = _remap_refs(self.root, rep)
        return Schema(new_root, new_types)

    # -- serialization (defined in dsl to avoid a cycle) ----------------
    def to_dsl(self) -> str:
        from .dsl import to_dsl
        return to_dsl(self)

    def __repr__(self) -> str:
        return f"Schema(root={self.root!r}, types={list(self.types)})"


# ===========================================================================
# Helpers
# ===========================================================================

def _typename(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, _dt.datetime):
        return "datetime"
    if isinstance(v, _dt.date):
        return "date"
    if isinstance(v, _dt.time):
        return "time"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    return type(v).__name__


def _scalar_matches(value: Any, kinds: Set[str]) -> bool:
    for k in kinds:
        if _matches_kind(value, k):
            return True
    return False


def _matches_kind(value: Any, kind: str) -> bool:
    if kind == STRING:
        return isinstance(value, str)
    if kind == BOOLEAN:
        return isinstance(value, bool)
    if kind == INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == DATE:
        if isinstance(value, _dt.datetime):
            return False
        if isinstance(value, _dt.date):
            return True
        return _is_iso(value, _dt.date)
    if kind == TIME:
        if isinstance(value, _dt.time):
            return True
        return _is_iso(value, _dt.time)
    if kind == DATETIME:
        if isinstance(value, _dt.datetime):
            return True
        return _is_iso(value, _dt.datetime)
    return False


def _is_iso(value: Any, cls) -> bool:
    """Allow temporal values that arrive as ISO-8601 strings (e.g. from JSON)."""
    if not isinstance(value, str):
        return False
    try:
        cls.fromisoformat(value)
        return True
    except ValueError:
        return False


def _join(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f'{path}["{key}"]'


# -- subtype check (compatible_with) ------------------------------------

def _subtype(sa: Schema, a: Type, sb: Schema, b: Type, seen: Set[tuple]) -> bool:
    a, a_null = sa.peel(a)
    b, b_null = sb.peel(b)
    if a_null and not b_null:
        return False  # a admits null where b does not
    key = (id(a), id(b))
    if key in seen:
        return True  # assume compatible on cycles (co-inductive)
    seen = seen | {key}

    if isinstance(a, ScalarType) and isinstance(b, ScalarType):
        return _scalar_subtype(a, b)
    if isinstance(a, ArrayType) and isinstance(b, ArrayType):
        if a.min < b.min:
            return False
        if b.max is not None and (a.max is None or a.max > b.max):
            return False
        return _subtype(sa, a.item, sb, b.item, seen)
    if isinstance(a, ObjectType) and isinstance(b, ObjectType):
        # every required field of b must be required by a
        for k in b.required_keys():
            if k not in a.required_keys():
                return False
        # every field a may emit must be allowed by b
        for k, fa in a.fields.items():
            if k in b.fields:
                if not _subtype(sa, fa.type, sb, b.fields[k].type, seen):
                    return False
            elif not b.open:
                return False
        if a.open and not b.open:
            return False
        return True
    return False


def _scalar_subtype(a: ScalarType, b: ScalarType) -> bool:
    # nullability already handled by _subtype via peel()
    if a.enum is not None:
        if b.enum is not None:
            return a.enum <= b.enum
        return all(_kind_in(_value_kind(v), b.kinds) for v in a.enum)
    if b.enum is not None:
        return False  # an open scalar isn't a subset of a finite enum
    return all(_kind_in(k, b.kinds) for k in a.kinds)


def _kind_in(k: str, kinds: Set[str]) -> bool:
    if k in kinds:
        return True
    if k == INTEGER and NUMBER in kinds:
        return True  # an integer is also a number
    if k == DATE and DATETIME in kinds:
        return False
    return False


def _value_kind(v: Any) -> str:
    if isinstance(v, bool):
        return BOOLEAN
    if isinstance(v, int):
        return INTEGER
    if isinstance(v, float):
        return NUMBER
    return STRING


# -- normalize helpers --------------------------------------------------

def _struct_key(s: Schema, t: Type, seen: Set[str]) -> tuple:
    # keep references symbolic (so recursion terminates); fold ref-nullability in
    if isinstance(t, RefType):
        return ("ref", t.name, t.nullable)
    null = t.nullable
    if isinstance(t, ScalarType):
        return ("scalar", frozenset(t.kinds), null, t.enum)
    if isinstance(t, ArrayType):
        return ("array", null, t.min, t.max, _struct_key(s, t.item, seen))
    if isinstance(t, ObjectType):
        fields = tuple(sorted(
            (k, f.required, _struct_key(s, f.type, seen)) for k, f in t.fields.items()))
        return ("object", null, t.open, fields)
    return ("?",)


def _remap_refs(t: Type, rep: Dict[str, str]) -> Type:
    if isinstance(t, RefType):
        return RefType(rep.get(t.name, t.name), t.nullable)
    if isinstance(t, ArrayType):
        return ArrayType(_remap_refs(t.item, rep), t.min, t.max, t.nullable)
    if isinstance(t, ObjectType):
        return ObjectType({k: Field(_remap_refs(f.type, rep), f.required)
                           for k, f in t.fields.items()}, t.open, t.nullable)
    return t
