"""The schema model and validation.

A **Document** is just plain Python data — `dict`, `list`, `str`, `int`,
`float`, `bool`, `None`, and `datetime.date` / `.time` / `.datetime`.  There is
no custom node type; you work with the data directly.

A **Schema** describes the shape a Document should have.  It is built from a few
kinds of **types** that mirror the data:

    object   — keyed fields (a dict)         -> ObjectType
    array    — an ordered list               -> ArrayType
    scalar   — a single value                -> ScalarType
    any      — anything at all               -> AnyType

Objects can also carry a `rest` type to describe a **map**: arbitrary string
keys whose values all share one type (e.g. `{"jan": 1, "feb": 2}`).

Named types (with recursion) are supported via `RefType` and `Schema.types`.

`schema.validate(data)` returns a `ValidationResult` with the verdict and
path-aware errors.  The comparison methods (`equivalent`, `compatible_with`,
`normalize`) live here too — they are just things a Schema can do.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

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

class Error(NamedTuple):
    """A single validation failure.  Unpacks as ``(path, message)`` and also
    exposes ``.path`` and ``.message``."""
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


# ===========================================================================
# Types
# ===========================================================================

class Type:
    """Base class for schema types. Any type may be `nullable` (also accepts null)."""
    kind: str = ""
    nullable: bool = False


class AnyType(Type):
    """Matches any Document, including null. Use sparingly — it turns off checking."""
    kind = "any"
    nullable = True

    def __repr__(self) -> str:
        return "any"


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

    def children(self) -> List[Tuple[str, Type]]:
        """The single child of an array: its item type, under the key ``'[]'``."""
        return [("[]", self.item)]

    def __repr__(self) -> str:
        hi = "" if self.max is None else self.max
        return f"array({self.item!r})[{self.min},{hi}]"


class Field:
    def __init__(self, type: Type, required: bool) -> None:
        self.type = type
        self.required = required


class ObjectType(Type):
    """A keyed object.

    `fields` are the named entries (each required or optional).  `rest`
    describes any *other* keys:

      * ``rest=None``        — closed: no other keys allowed (the default)
      * ``rest=AnyType()``   — open: other keys allowed with any value
      * ``rest=<type>``      — a map: other keys must have this value type

    A pure map is just an ObjectType with no `fields` and a `rest` type.
    """
    kind = "object"

    def __init__(self, fields: Dict[str, Field], rest: Optional[Type] = None,
                 nullable: bool = False) -> None:
        self.fields = fields
        self.rest = rest
        self.nullable = nullable

    @property
    def open(self) -> bool:
        """True if extra keys are allowed (open object or map)."""
        return self.rest is not None

    @staticmethod
    def of(required: Dict[str, Type] = None, optional: Dict[str, Type] = None,
           rest: Optional[Type] = None) -> "ObjectType":
        fields: Dict[str, Field] = {}
        for k, t in (required or {}).items():
            fields[k] = Field(t, True)
        for k, t in (optional or {}).items():
            fields[k] = Field(t, False)
        return ObjectType(fields, rest)

    def required_keys(self) -> Set[str]:
        return {k for k, f in self.fields.items() if f.required}

    # -- uniform child getters ------------------------------------------
    def field(self, name: str) -> Type:
        """The type of a named field, or raise if there is no such field."""
        try:
            return self.fields[name].type
        except KeyError:
            raise SchemaError(f"no field {name!r}") from None

    def field_names(self) -> List[str]:
        return list(self.fields.keys())

    def children(self) -> List[Tuple[str, Type]]:
        """(name, type) for each named field; plus ('[rest]', rest) if a map/open."""
        out: List[Tuple[str, Type]] = [(k, f.type) for k, f in self.fields.items()]
        if self.rest is not None:
            out.append(("[rest]", self.rest))
        return out

    def __repr__(self) -> str:
        tail = "" if self.rest is None else (", ..." if isinstance(self.rest, AnyType)
                                             else f", rest={self.rest!r}")
        return f"object({sorted(self.fields)}{tail})"


class RefType(Type):
    """A reference to a named type (enables reuse and recursion)."""
    kind = "ref"

    def __init__(self, name: str, nullable: bool = False) -> None:
        self.name = name
        self.nullable = nullable

    def __repr__(self) -> str:
        return f"ref({self.name}{'?' if self.nullable else ''})"


# ===========================================================================
# Schema
# ===========================================================================

class Schema:
    """A schema: a root type plus any named types (for reuse / recursion)."""

    def __init__(self, root: Type, types: Optional[Dict[str, Type]] = None) -> None:
        self.root = root
        self.types: Dict[str, Type] = types or {}

    @classmethod
    def parse(cls, text: str) -> "Schema":
        """Parse DSL text into a Schema (same as :func:`dataspec.parse_schema`)."""
        from .dsl import parse_schema
        return parse_schema(text)

    # -- resolution -----------------------------------------------------
    def resolve(self, t: Type) -> Type:
        """Follow a chain of named-type references to a concrete type."""
        return self.peel(t)[0]

    def peel(self, t: Type) -> Tuple[Type, bool]:
        """Resolve refs to a concrete type, OR-ing nullability along the chain."""
        nullable = t.nullable
        if not isinstance(t, RefType):
            return t, nullable  # common case: skip allocating `seen` entirely
        seen: set = set()
        while isinstance(t, RefType):
            if t.name in seen:
                raise SchemaError(f"cyclic type alias chain at {t.name!r}")
            seen.add(t.name)
            if t.name not in self.types:
                raise SchemaError(f"unknown type {t.name!r}")
            t = self.types[t.name]
            nullable = nullable or t.nullable
        return t, nullable

    def check_refs(self) -> None:
        """Raise SchemaError if any named-type reference is undefined."""
        def walk(t: Type) -> None:
            if isinstance(t, RefType):
                if t.name not in self.types:
                    raise SchemaError(f"unknown type {t.name!r}")
            elif isinstance(t, ArrayType):
                walk(t.item)
            elif isinstance(t, ObjectType):
                for f in t.fields.values():
                    walk(f.type)
                if t.rest is not None:
                    walk(t.rest)
        walk(self.root)
        for t in self.types.values():
            walk(t)

    # -- validation -----------------------------------------------------
    def validate(self, doc: Any) -> ValidationResult:
        """Check a :class:`~dataspec.document.Doc` against this schema.

        Validation operates on a Document, not on raw format text — read or
        import your data into a ``Doc`` first (``Doc.from_json`` / ``doc(...)``).
        """
        from .document import Doc
        if not isinstance(doc, Doc):
            raise TypeError(
                "validate() expects a Doc; wrap your data first, e.g. "
                "doc(my_dict) or Doc.from_json(text)")
        result = ValidationResult()
        # Validation only reads the tree, so walk the live data without copying.
        self._check(doc._data, self.root, "$", result)
        return result

    def accepts(self, doc: Any) -> bool:
        return self.validate(doc).ok

    def _check(self, data: Any, t: Type, path: str, res: ValidationResult) -> None:
        t, nullable = self.peel(t)
        if isinstance(t, AnyType):
            return  # matches anything, including null
        if data is None:
            if not nullable:
                res.add(path, "null not allowed here")
            return
        if isinstance(t, ObjectType):
            self._check_object(data, t, path, res)
        elif isinstance(t, ArrayType):
            self._check_array(data, t, path, res)
        elif isinstance(t, ScalarType):
            self._check_scalar(data, t, path, res)
        else:  # pragma: no cover
            res.add(path, f"unhandled type {t!r}")

    def _check_object(self, data, t: ObjectType, path, res) -> None:
        if not isinstance(data, dict):
            res.add(path, f"expected object, got {_typename(data)}")
            return
        for key, field in t.fields.items():
            if key in data:
                self._check(data[key], field.type, _join(path, key), res)
            elif field.required:
                res.add(path, f"missing required field {key!r}")
        extra = [k for k in data if k not in t.fields]
        for k in extra:
            if t.rest is None:
                res.add(_join(path, k), "unexpected field")
            else:
                self._check(data[k], t.rest, _join(path, k), res)

    def _check_array(self, data, t: ArrayType, path, res) -> None:
        if not isinstance(data, list):
            res.add(path, f"expected array, got {_typename(data)}")
            return
        n = len(data)
        if n < t.min or (t.max is not None and n > t.max):
            if t.max is None:
                bound = f"at least {t.min}"
            elif t.min == t.max:
                bound = f"exactly {t.min}"
            else:
                bound = f"between {t.min} and {t.max}"
            res.add(path, f"array length {n} is not {bound}")
        for i, item in enumerate(data):
            self._check(item, t.item, f"{path}[{i}]", res)

    def _check_scalar(self, data, t: ScalarType, path, res) -> None:
        if t.enum is not None:
            if data not in t.enum:
                res.add(path, f"{data!r} not one of {sorted(t.enum)}")
            return
        if not _scalar_matches(data, t.kinds):
            res.add(path, f"expected {'|'.join(sorted(t.kinds))}, got {_typename(data)}")

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
        groups: Dict[tuple, List[str]] = {}
        for name, t in self.types.items():
            groups.setdefault(_struct_key(self, t, set()), []).append(name)
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
    return any(_matches_kind(value, k) for k in kinds)


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
    if isinstance(b, AnyType):
        return True                       # b accepts everything
    if isinstance(a, AnyType):
        return False                      # a accepts things b may not
    if a_null and not b_null:
        return False                      # a admits null where b does not
    key = (id(a), id(b))
    if key in seen:
        return True                       # assume compatible on cycles (co-inductive)
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
        # every named field a may emit must be allowed by b
        for k, fa in a.fields.items():
            if k in b.fields:
                if not _subtype(sa, fa.type, sb, b.fields[k].type, seen):
                    return False
            elif b.rest is not None:
                if not _subtype(sa, fa.type, sb, b.rest, seen):
                    return False
            else:
                return False              # b is closed and has no such field
        # extra keys a may emit (its rest) must be allowed by b's rest
        if a.rest is not None:
            if b.rest is None:
                return False
            if not _subtype(sa, a.rest, sb, b.rest, seen):
                return False
        return True
    return False


def _scalar_subtype(a: ScalarType, b: ScalarType) -> bool:
    if a.enum is not None:
        if b.enum is not None:
            return a.enum <= b.enum
        return all(_kind_in(_value_kind(v), b.kinds) for v in a.enum)
    if b.enum is not None:
        return False                      # an open scalar isn't a subset of a finite enum
    return all(_kind_in(k, b.kinds) for k in a.kinds)


def _kind_in(k: str, kinds: Set[str]) -> bool:
    if k in kinds:
        return True
    if k == INTEGER and NUMBER in kinds:
        return True                       # an integer is also a number
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
    if isinstance(t, RefType):
        return ("ref", t.name, t.nullable)
    null = t.nullable
    if isinstance(t, AnyType):
        return ("any",)
    if isinstance(t, ScalarType):
        return ("scalar", frozenset(t.kinds), null, t.enum)
    if isinstance(t, ArrayType):
        return ("array", null, t.min, t.max, _struct_key(s, t.item, seen))
    if isinstance(t, ObjectType):
        fields = tuple(sorted(
            (k, f.required, _struct_key(s, f.type, seen)) for k, f in t.fields.items()))
        rest = None if t.rest is None else _struct_key(s, t.rest, seen)
        return ("object", null, rest, fields)
    return ("?",)


def _remap_refs(t: Type, rep: Dict[str, str]) -> Type:
    if isinstance(t, RefType):
        return RefType(rep.get(t.name, t.name), t.nullable)
    if isinstance(t, ArrayType):
        return ArrayType(_remap_refs(t.item, rep), t.min, t.max, t.nullable)
    if isinstance(t, ObjectType):
        rest = None if t.rest is None else _remap_refs(t.rest, rep)
        return ObjectType({k: Field(_remap_refs(f.type, rep), f.required)
                           for k, f in t.fields.items()}, rest, t.nullable)
    return t
