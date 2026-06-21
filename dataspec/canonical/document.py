"""The Document — a canonical Data Tree of ordered, labeled edges.

A Document is the formal Data Tree of Lee & Cheung (CIKM 2010): a node is either

* a **leaf** holding a scalar value (``str``/``int``/``float``/``bool``/
  ``datetime`` values, or ``None``), or
* an **internal node** holding an *ordered list of edges*, each a
  ``(label, child)`` pair.  **Labels may repeat** — "many members" is the label
  ``member`` appearing several times, not a field pointing to an array.

The canonical Python form of a node is therefore::

    scalar                                   # a leaf
    [(label, node), (label, node), ...]      # an internal node (ordered)

This single shape represents every supported format canonically, including
XML's interleaved repeated elements, which a dict-with-array-values cannot.
``Doc`` is a thin, guarded wrapper with navigation helpers.  Order is preserved
(it is data); schema validation ignores it.  See ``docs/design/model.md``.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator, List, Optional, Tuple

from ..errors import DocumentError

_MAX_DEPTH = 200

Edge = Tuple[str, Any]   # (label, node)


def _is_scalar(v: Any) -> bool:
    # bool is an int subclass and datetime a date subclass — both are fine here.
    return isinstance(v, (str, int, float, _dt.date, _dt.time, _dt.datetime)) or v is None


# ---------------------------------------------------------------------------
# Building a node from a plain Python value (JSON-shaped)
# ---------------------------------------------------------------------------

def build_node(value: Any, path: str = "$", depth: int = 0,
               seen: Optional[frozenset] = None) -> Any:
    """Turn a plain Python value into a canonical node.

    A ``dict`` becomes an ordered edge list; a key whose value is a list expands
    into one edge **per item** (the same label repeated).  A scalar becomes a
    leaf.  A *bare* list (a top-level array, or a list nested directly inside a
    list) has no labeled-edge form and raises ``DocumentError``.
    """
    if depth > _MAX_DEPTH:
        raise DocumentError(f"{path}: nesting exceeds the maximum depth ({_MAX_DEPTH})")
    if isinstance(value, dict):
        seen = seen or frozenset()
        if id(value) in seen:
            raise DocumentError(f"{path}: cycle detected")
        seen = seen | {id(value)}
        edges: List[Edge] = []
        for k, v in value.items():
            if not isinstance(k, str):
                raise DocumentError(f"{path}: object key {k!r} is not a string")
            kp = _join(path, k)
            for child in _children(v, kp, depth + 1, seen):
                edges.append((k, child))
        return edges
    if isinstance(value, (list, tuple)):
        raise DocumentError(f"{path}: a bare array has no labeled-edge form "
                            "(arrays appear only as a repeated field)")
    if _is_scalar(value):
        return value
    raise DocumentError(f"{path}: {type(value).__name__} is not a Document value")


def _children(v: Any, path: str, depth: int, seen: frozenset) -> Iterator[Any]:
    if isinstance(v, (list, tuple)):
        for i, item in enumerate(v):
            if isinstance(item, (list, tuple)):
                raise DocumentError(
                    f"{path}[{i}]: an array of arrays has no Data-Tree form")
            yield build_node(item, f"{path}[{i}]", depth + 1, seen)
    else:
        yield build_node(v, path, depth, seen)


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if key.isidentifier() else f'{path}["{key}"]'


# ---------------------------------------------------------------------------
# Doc — guarded wrapper with navigation
# ---------------------------------------------------------------------------

class Doc:
    """A guarded handle on a Document node (a leaf value or an edge list)."""

    __slots__ = ("_node", "path")

    def __init__(self, node: Any, path: str = "$") -> None:
        self._node = node
        self.path = path

    # -- construction ---------------------------------------------------
    @classmethod
    def of(cls, value: Any) -> "Doc":
        return cls(build_node(value))

    @classmethod
    def from_format(cls, name: str, text: str) -> "Doc":
        from .formats import get_reader
        return cls(get_reader(name)(text))

    @classmethod
    def from_json(cls, text: str) -> "Doc":
        from .formats import read_json
        return cls(read_json(text))

    @classmethod
    def from_yaml(cls, text: str) -> "Doc":
        from .formats import read_yaml
        return cls(read_yaml(text))

    @classmethod
    def from_toml(cls, text: str) -> "Doc":
        from .formats import read_toml
        return cls(read_toml(text))

    @classmethod
    def from_xml(cls, text: str) -> "Doc":
        from .formats import read_xml
        return cls(read_xml(text))

    # -- shape ----------------------------------------------------------
    @property
    def is_leaf(self) -> bool:
        return not isinstance(self._node, list)

    @property
    def value(self) -> Any:
        if isinstance(self._node, list):
            raise DocumentError(f"{self.path}: not a leaf; use edges()")
        return self._node

    def edges(self) -> List[Tuple[str, "Doc"]]:
        if not isinstance(self._node, list):
            raise DocumentError(f"{self.path}: a leaf has no edges")
        out, counts = [], {}
        for label, child in self._node:
            i = counts.get(label, 0)
            counts[label] = i + 1
            cp = f"{self.path}.{label}" if i == 0 else f"{self.path}.{label}[{i}]"
            out.append((label, Doc(child, cp)))
        return out

    def labels(self) -> List[str]:
        seen, out = set(), []
        for label, _ in self._iter():
            if label not in seen:
                seen.add(label)
                out.append(label)
        return out

    def get(self, label: str) -> List["Doc"]:
        return [c for lbl, c in self.edges() if lbl == label]

    def get_one(self, label: str) -> "Doc":
        cs = self.get(label)
        if len(cs) != 1:
            raise DocumentError(
                f"{self.path}: expected exactly one {label!r}, found {len(cs)}")
        return cs[0]

    def count(self, label: str) -> int:
        return sum(1 for lbl, _ in self._iter() if lbl == label)

    def _iter(self) -> Iterator[Tuple[str, Any]]:
        if isinstance(self._node, list):
            yield from self._node

    def child(self, label: str) -> "Doc":
        """A cursor to the single child under ``label`` (editable if internal)."""
        return self.get_one(label)

    # -- editing (mutates the underlying edge list) ---------------------
    def add(self, label: str, value: Any) -> "Doc":
        """Append an edge ``(label, value)``.  A repeated label is how an array
        grows.  Returns ``self`` for chaining."""
        self._require_internal("add")
        self._node.append((label, build_node(value, f"{self.path}.{label}")))
        return self

    def remove(self, label: str) -> "Doc":
        """Remove every edge under ``label``."""
        self._require_internal("remove")
        self._node[:] = [(lbl, c) for lbl, c in self._node if lbl != label]
        return self

    def set(self, label: str, value: Any) -> "Doc":
        """Replace the (single) child under ``label``, or add it if absent."""
        self._require_internal("set")
        new = build_node(value, f"{self.path}.{label}")
        for i, (lbl, _) in enumerate(self._node):
            if lbl == label:
                self._node[i] = (label, new)
                return self
        self._node.append((label, new))
        return self

    def _require_internal(self, op: str) -> None:
        if not isinstance(self._node, list):
            raise DocumentError(f"{self.path}: cannot {op} on a leaf")

    # -- export ---------------------------------------------------------
    def to_data(self) -> Any:
        return _copy(self._node)

    def to_grouped(self) -> Any:
        """A JSON-shaped projection: same-label edges grouped into a list.

        A label seen once stays a single value; a label seen more than once
        becomes a list (the schema-less fallback of the count-1 rule, see
        ``docs/design/model.md`` §10)."""
        return _grouped(self._node)

    def to_json(self, **o: Any) -> str:
        from .formats import write_json
        return write_json(self._node, **o)

    def to_yaml(self, **o: Any) -> str:
        from .formats import write_yaml
        return write_yaml(self._node, **o)

    def to_toml(self, **o: Any) -> str:
        from .formats import write_toml
        return write_toml(self._node, **o)

    def to_xml(self, **o: Any) -> str:
        from .formats import write_xml
        return write_xml(self._node, **o)

    def validate(self, schema):
        return schema.validate(self)

    # -- dunders --------------------------------------------------------
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Doc):
            return self._node == other._node
        try:
            return self._node == build_node(other)
        except DocumentError:
            return NotImplemented

    def __repr__(self) -> str:
        return f"Doc({'leaf' if self.is_leaf else 'node'}: {self._node!r})"


def doc(value: Any) -> Doc:
    """Build a :class:`Doc` from a plain Python value."""
    return value if isinstance(value, Doc) else Doc.of(value)


def _copy(node: Any) -> Any:
    if isinstance(node, list):
        return [(label, _copy(child)) for label, child in node]
    return node


def _grouped(node: Any) -> Any:
    if not isinstance(node, list):
        return node
    counts: dict = {}
    for label, _ in node:
        counts[label] = counts.get(label, 0) + 1
    out: dict = {}
    for label, child in node:
        g = _grouped(child)
        if counts[label] > 1:
            out.setdefault(label, []).append(g)
        else:
            out[label] = g
    return out
