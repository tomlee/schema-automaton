"""Value Domain (VDom) — constrains the data values stored in d-nodes.

A value domain admits a **set** of scalar kinds, optionally an enumeration of
literal values, and optionally the null value (``nullable``).  Supporting a set
of kinds (rather than a single kind) is what lets schema inference represent a
position that is, e.g., *integer or string* across samples — without that, a
generalised domain would silently reject some of its own input.

Scalar kinds (mirroring XML simple types and JSON/TOML/YAML scalars):

    STRS  — string        (xs:string, JSON string)
    INTS  — integer       (xs:int, JSON/TOML integer)
    DECS  — decimal/float  (xs:decimal, JSON/TOML float)
    BOOL  — boolean        (xs:boolean, JSON/TOML bool)

The *null* value ``ε`` is modelled by ``nullable`` (and by the empty kind set,
used for complex map/sequence nodes whose own value is ``ε``).
"""

from __future__ import annotations
from typing import FrozenSet, Iterable, Optional, Set


class VDom:
    # public single-kind names (also used as the kind atoms in the kind set)
    STRS = "STRS"
    INTS = "INTS"
    DECS = "DECS"
    BOOL = "BOOL"
    NULL = "NULL"      # reported .kind for the pure-null / complex-node domain
    CUSTOM = "CUSTOM"  # reported .kind for an enumeration
    UNION = "UNION"    # reported .kind for a multi-kind domain

    _SCALAR_ATOMS = {STRS, INTS, DECS, BOOL}

    def __init__(
        self,
        kinds: Iterable[str] = (),
        nullable: bool = False,
        enum: Optional[Iterable[str]] = None,
    ) -> None:
        ks = frozenset(kinds)
        bad = ks - self._SCALAR_ATOMS
        if bad:
            raise ValueError(f"Unknown scalar kind(s): {sorted(bad)}")
        self.kinds: FrozenSet[str] = ks
        self.nullable = nullable
        self.enum: Optional[FrozenSet[str]] = frozenset(enum) if enum is not None else None

    # ------------------------------------------------------------------
    # Back-compatible scalar single-kind view
    # ------------------------------------------------------------------

    @property
    def kind(self) -> str:
        """A representative kind name (back-compatible single-kind view)."""
        if self.enum is not None:
            return self.CUSTOM
        if not self.kinds:
            return self.NULL
        if len(self.kinds) == 1:
            return next(iter(self.kinds))
        return self.UNION

    @property
    def values(self) -> Optional[FrozenSet[str]]:
        """Back-compatible alias for the enumeration set."""
        return self.enum

    # ------------------------------------------------------------------
    # Membership (string-based — for untyped / XML data)
    # ------------------------------------------------------------------

    def contains(self, value: str) -> bool:
        if value in ("", None):
            # ε is admitted by nullable domains, the pure-null/complex domain,
            # an enum containing it, or the string kind (the empty string is a
            # string — matches the paper's STRS = "all strings").
            if self.nullable or not self.kinds:
                return True
            if self.enum is not None:
                return "" in self.enum
            return self.STRS in self.kinds
        if self.enum is not None:
            return value in self.enum
        if self.STRS in self.kinds:
            return True
        if self.INTS in self.kinds and _is_int(value):
            return True
        if self.DECS in self.kinds and _is_float(value):
            return True
        if self.BOOL in self.kinds and str(value).lower() in ("true", "false"):
            return True
        return False

    # ------------------------------------------------------------------
    # Typed-value admissibility (JSON/TOML/YAML data, where 1 ≠ "1")
    # ------------------------------------------------------------------

    def admits(self, value_type: "VDom") -> bool:
        """Can a value whose *type* is ``value_type`` appear in this domain?

        Uses data-format semantics where ``1`` and ``"1"`` are distinct types.
        Enum domains are decided by value (via :meth:`contains`), so a typed
        node against an enum domain returns True here and the caller checks the
        literal value.
        """
        # the null value
        if value_type.kind == self.NULL or (value_type.nullable and not value_type.kinds):
            return self.nullable
        if value_type.nullable and not self.nullable:
            return False
        if self.enum is not None:
            return True  # decided by value elsewhere
        for k in value_type.kinds:
            if k in self.kinds:
                continue
            if k == self.INTS and self.DECS in self.kinds:
                continue  # an integer is an admissible number
            return False
        return True

    # ------------------------------------------------------------------
    # Subset relationship   (VDom(q) ⊆ VDom(q')  for schema comparison)
    # ------------------------------------------------------------------

    def is_subset_of(self, other: "VDom") -> bool:
        if self.nullable and not other.nullable:
            return False
        if self.enum is not None:
            if other.enum is not None:
                return self.enum <= other.enum
            # enum of strings ⊆ other iff other admits strings (or the kinds match)
            return all(other._base_admits_kind(self.STRS) for _ in [0]) \
                if self.kinds <= {self.STRS} else \
                all(other._base_admits_kind(k) for k in self.kinds)
        if other.enum is not None:
            # a non-enum domain is broader than an enumeration
            return not self.kinds
        return all(other._base_admits_kind(k) for k in self.kinds)

    def _base_admits_kind(self, k: str) -> bool:
        if k in self.kinds:
            return True
        if k == self.INTS and self.DECS in self.kinds:
            return True
        return False

    # ------------------------------------------------------------------
    # Generalisation — least domain covering both (used by schema inference)
    # ------------------------------------------------------------------

    @staticmethod
    def union(a: "VDom", b: "VDom") -> "VDom":
        nullable = a.nullable or b.nullable
        kinds: Set[str] = set(a.kinds) | set(b.kinds)
        # numeric widening: a number kind subsumes integers
        if VDom.DECS in kinds and VDom.INTS in kinds:
            kinds.discard(VDom.INTS)

        if a.enum is not None and b.enum is not None and a.kinds <= {VDom.STRS} \
                and b.kinds <= {VDom.STRS}:
            return VDom({VDom.STRS}, nullable=nullable, enum=set(a.enum) | set(b.enum))
        # if either side is a non-enum domain, the union is a plain (non-enum) domain
        return VDom(kinds, nullable=nullable)

    def as_nullable(self) -> "VDom":
        return VDom(self.kinds, nullable=True, enum=self.enum)

    # ------------------------------------------------------------------
    # Pre-built singletons
    # ------------------------------------------------------------------

    @staticmethod
    def strs() -> "VDom":
        return VDom({VDom.STRS})

    @staticmethod
    def ints() -> "VDom":
        return VDom({VDom.INTS})

    @staticmethod
    def decs() -> "VDom":
        return VDom({VDom.DECS})

    @staticmethod
    def bool_() -> "VDom":
        return VDom({VDom.BOOL})

    @staticmethod
    def null() -> "VDom":
        return VDom((), nullable=True)

    @staticmethod
    def finite(*values: str) -> "VDom":
        return VDom({VDom.STRS}, enum=set(values))

    @staticmethod
    def union_of(*domains: "VDom") -> "VDom":
        result = domains[0]
        for d in domains[1:]:
            result = VDom.union(result, d)
        return result

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VDom):
            return False
        return (self.kinds == other.kinds
                and self.enum == other.enum
                and self.nullable == other.nullable)

    def __hash__(self) -> int:
        return hash((self.kinds, self.enum, self.nullable))

    def __repr__(self) -> str:
        suffix = "?" if self.nullable else ""
        if self.enum is not None:
            return f"VDom({{{', '.join(sorted(self.enum))}}}){suffix}"
        if not self.kinds:
            return "VDom(NULL)" if self.nullable else "VDom(∅)"
        if len(self.kinds) == 1:
            return f"VDom({next(iter(self.kinds))}){suffix}"
        return f"VDom({'|'.join(sorted(self.kinds))}){suffix}"


def _is_int(value: str) -> bool:
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False
