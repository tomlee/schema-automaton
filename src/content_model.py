"""Content models — the pluggable abstraction that makes a Schema Automaton
data-format agnostic.

In the original paper (Lee & Cheung, CIKM 2010) the permissible children of a
d-node are described by a *horizontal language* (HLang): a regular language over
the ordered sequence of child-edge symbols.  That is exactly right for XML, where
element order is significant.  But other popular formats are not ordered:

    * JSON objects   — unordered set of unique keys
    * TOML tables    — unordered set of unique keys
    * YAML mappings  — unordered set of unique keys
    * JSON arrays    — ordered, usually homogeneous
    * YAML sequences — ordered

To model all of these with one Schema Automaton, we generalise the HLang into a
``ContentModel``: anything that can decide which child-symbol sequences are
permissible under a node, and that supports the handful of operations the schema
algorithms need (subset testing, minimization keys, mandatory-symbol detection,
symbol removal).

Three concrete content models are provided:

    SequenceModel  ordered  — regular language over symbols (this is the paper's
                              HLang; implemented in ``hlang.HLang``)
    MapModel       unordered — a record of named fields, each required or optional,
                              optionally "open" to additional keys
    ScalarModel    leaf      — no children; the value is constrained by the VDom

All three share the ``ContentModel`` interface so the algorithms in
``algorithms.py`` are completely independent of the underlying data format.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Set


# Canonical structural kinds shared by content models and data-tree nodes.
KIND_SEQUENCE = "SEQUENCE"
KIND_MAP = "MAP"
KIND_SCALAR = "SCALAR"


class ContentModel(ABC):
    """Abstract permissible-children model for a Schema Automaton state."""

    #: one of KIND_SEQUENCE / KIND_MAP / KIND_SCALAR
    kind: str = ""

    # -- membership --------------------------------------------------------
    @abstractmethod
    def accepts(self, sequence: List[str]) -> bool:
        """Does this content model permit the given ordered child-symbol sequence?"""

    def accepts_empty(self) -> bool:
        return self.accepts([])

    # -- symbol queries ----------------------------------------------------
    @abstractmethod
    def symbols(self) -> Set[str]:
        """All symbols that may appear in some accepted sequence."""

    @abstractmethod
    def mandatory_symbols(self) -> Set[str]:
        """Symbols that appear in *every* accepted (non-empty) sequence."""

    def is_mandatory(self, symbol: str) -> bool:
        return symbol in self.mandatory_symbols()

    def permits_untyped_child(self, symbol: str) -> bool:
        """True if a child on *symbol* is allowed without a declared type.

        Only open maps return True (for additional/undeclared keys, whose value
        is unconstrained). Such children have no δ transition and any subtree is
        accepted under them.
        """
        return False

    # -- transformations ---------------------------------------------------
    @abstractmethod
    def remove_symbol(self, symbol: str) -> "ContentModel":
        """Return a content model accepting the same sequences except those
        containing *symbol* (used by subschema extraction, Algorithm 5)."""

    @abstractmethod
    def is_empty(self) -> bool:
        """Does this content model accept *no* sequence at all?"""

    # -- comparison --------------------------------------------------------
    @abstractmethod
    def is_subset_of(self, other: "ContentModel") -> bool:
        """Is the set of accepted sequences a subset of ``other``'s?"""

    @abstractmethod
    def canonical_key(self) -> tuple:
        """A hashable form; equal keys iff the languages are equal."""

    def language_equals(self, other: "ContentModel") -> bool:
        return self.is_subset_of(other) and other.is_subset_of(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ContentModel):
            return NotImplemented
        return self.canonical_key() == other.canonical_key()

    def __hash__(self) -> int:
        return hash(self.canonical_key())


# ===========================================================================
# MapModel — unordered record of named fields (JSON objects, TOML/YAML maps)
# ===========================================================================

class MapModel(ContentModel):
    """
    Unordered content model.

    A *map* permits a set of child symbols (keys) with no significant order and
    no duplicates.  Each declared field is either required or optional.  When
    ``open`` is True, keys other than the declared fields are also allowed
    (cf. JSON Schema ``additionalProperties``).
    """

    kind = KIND_MAP

    def __init__(
        self,
        fields: Dict[str, bool],
        open: bool = False,
        forbidden: Iterable[str] = (),
        _empty: bool = False,
    ) -> None:
        # fields: key -> required?
        self.fields: Dict[str, bool] = dict(fields)
        self.open = open
        self.forbidden: Set[str] = set(forbidden)
        self._empty = _empty

    # -- factories ---------------------------------------------------------
    @staticmethod
    def empty() -> "MapModel":
        """A map model that accepts nothing."""
        return MapModel({}, _empty=True)

    @staticmethod
    def of(required: Iterable[str] = (), optional: Iterable[str] = (),
           open: bool = False) -> "MapModel":
        fields = {k: True for k in required}
        fields.update({k: False for k in optional})
        return MapModel(fields, open=open)

    # -- membership --------------------------------------------------------
    def accepts(self, sequence: List[str]) -> bool:
        if self._empty:
            return False
        seen: Set[str] = set()
        for sym in sequence:
            if sym in seen:
                return False  # duplicate key — invalid in a map
            seen.add(sym)
            if sym in self.forbidden:
                return False
            if sym not in self.fields and not self.open:
                return False
        # every required field must be present
        for key, required in self.fields.items():
            if required and key not in seen:
                return False
        return True

    # -- symbol queries ----------------------------------------------------
    def symbols(self) -> Set[str]:
        return set(self.fields)

    def mandatory_symbols(self) -> Set[str]:
        if self._empty:
            return set()
        return {k for k, required in self.fields.items() if required}

    def permits_untyped_child(self, symbol: str) -> bool:
        return self.open and symbol not in self.fields and symbol not in self.forbidden

    # -- transformations ---------------------------------------------------
    def remove_symbol(self, symbol: str) -> "ContentModel":
        if self._empty:
            return self
        # Removing all accepted sequences that contain `symbol`:
        if self.fields.get(symbol, False):
            # symbol was required -> every accepted sequence contains it -> empty
            return MapModel.empty()
        new_fields = {k: v for k, v in self.fields.items() if k != symbol}
        new_forbidden = set(self.forbidden)
        if self.open:
            # an open map could still admit `symbol` as an extra key — forbid it
            new_forbidden.add(symbol)
        return MapModel(new_fields, open=self.open, forbidden=new_forbidden)

    def is_empty(self) -> bool:
        return self._empty

    # -- comparison --------------------------------------------------------
    def is_subset_of(self, other: "ContentModel") -> bool:
        if self._empty:
            return True
        if not isinstance(other, MapModel):
            # a non-empty map is never a subset of a sequence/scalar model
            return False
        if other._empty:
            return False
        # If self admits arbitrary extra keys, other must too (with nothing it
        # forbids that self would emit).
        if self.open and not other.open:
            return False
        if self.open and other.forbidden:
            return False
        # Every required field of `other` must be required by `self`
        # (otherwise self has a valid sequence missing that key, rejected by other).
        for key, required in other.fields.items():
            if required and not self.fields.get(key, False):
                return False
        # Every key `self` may emit must be allowed by `other`.
        for key in self.fields:
            if key in other.forbidden:
                return False
            if key not in other.fields and not other.open:
                return False
        return True

    def canonical_key(self) -> tuple:
        if self._empty:
            return (KIND_MAP, "EMPTY")
        return (
            KIND_MAP,
            frozenset(self.fields.items()),
            self.open,
            frozenset(self.forbidden),
        )

    def __repr__(self) -> str:
        if self._empty:
            return "MapModel(∅)"
        req = sorted(k for k, v in self.fields.items() if v)
        opt = sorted(k for k, v in self.fields.items() if not v)
        extra = " +open" if self.open else ""
        return f"MapModel(required={req}, optional={opt}{extra})"


# ===========================================================================
# ScalarModel — a leaf node with no children (the value lives in the VDom)
# ===========================================================================

class ScalarModel(ContentModel):
    """Content model for scalar/leaf nodes: accepts only the empty sequence."""

    kind = KIND_SCALAR

    def accepts(self, sequence: List[str]) -> bool:
        return len(sequence) == 0

    def symbols(self) -> Set[str]:
        return set()

    def mandatory_symbols(self) -> Set[str]:
        return set()

    def remove_symbol(self, symbol: str) -> "ContentModel":
        return self  # nothing to remove

    def is_empty(self) -> bool:
        return False  # always accepts []

    def is_subset_of(self, other: "ContentModel") -> bool:
        return isinstance(other, ScalarModel)

    def canonical_key(self) -> tuple:
        return (KIND_SCALAR,)

    def __repr__(self) -> str:
        return "ScalarModel()"
