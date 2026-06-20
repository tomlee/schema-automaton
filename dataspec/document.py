"""The Document data structure — a guarded, format-neutral "data DOM".

A **Document** is a tree of objects, arrays, and scalar values.  :class:`Doc`
wraps that tree and is the *only* supported way to build and change it, so the
data can never drift into a malformed shape:

* every value you put in is checked against the Document model (allowed types,
  string keys, no cycles) and **copied in**, severing outside references;
* you navigate one level at a time (``child`` / ``child_at``) and read snapshots
  (``get`` / ``at``);
* you serialize to any registered format on demand (``to_json`` …), and get the
  plain tree back as a detached copy with ``to_data``.

A ``Doc`` is a **cursor**: ``child("address")`` returns a live cursor into that
subtree, so mutations through it affect the document.  **Leaves are not nodes** —
reading a scalar gives you the plain Python value, which is safe because scalars
are immutable.

This is the structure layer.  *Domains* (types) are not stored on a node — that
is the job of a :class:`~dataspec.schema.Schema`, applied with ``validate``.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterator, List, Optional, Tuple

from .errors import DetachedNode, DocumentError

_MISSING = object()

# Bounds recursion depth well under Python's default recursion limit (1000),
# so deeply/adversarially nested input raises a clean DocumentError instead of
# crashing the process with an uncatchable RecursionError.
_MAX_DEPTH = 200


# ===========================================================================
# Legalization: validate + deep-copy a Python value into a Document fragment
# ===========================================================================

def _legalize(value: Any, path: str) -> Any:
    """Return a deep copy of ``value`` proven to be a legal Document fragment.

    Tuples become lists.  Raises :class:`DocumentError` (with the offending path)
    for unsupported types, non-string keys, cycles, or nesting past
    :data:`_MAX_DEPTH`.
    """
    return _legalize_inner(value, path, ())


def _legalize_inner(value: Any, path: str, ancestors: tuple) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value                              # scalars (bool/int covered)
    if isinstance(value, (_dt.date, _dt.time, _dt.datetime)):
        return value                              # temporal scalars (immutable)
    if isinstance(value, (list, tuple, dict)):
        if id(value) in ancestors:
            raise DocumentError(f"{path}: cycle detected")
        anc = ancestors + (id(value),)
        if len(anc) > _MAX_DEPTH:
            raise DocumentError(
                f"{path}: nesting exceeds the maximum depth ({_MAX_DEPTH})")
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if not isinstance(k, str):
                    raise DocumentError(
                        f"{path}: object key {k!r} is not a string")
                out[k] = _legalize_inner(v, _join(path, k), anc)
            return out
        return [_legalize_inner(v, f"{path}[{i}]", anc) for i, v in enumerate(value)]
    raise DocumentError(
        f"{path}: {type(value).__name__} is not a Document value")


def _is_container(v: Any) -> bool:
    return isinstance(v, (dict, list))


def _join(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f'{path}["{key}"]'


# ===========================================================================
# Doc — a cursor over a Document node
# ===========================================================================

class Doc:
    """A node in a Document tree: an object, an array, or a scalar.

    Construct one with :func:`doc` or ``Doc.from_*``.  Build and edit it only
    through the methods here — never by reaching into the underlying data.
    """

    __slots__ = ("_data", "_parent", "_key")

    # -- construction ---------------------------------------------------
    def __init__(self, value: Any = _MISSING) -> None:
        self._data = {} if value is _MISSING else _legalize(value, "$")
        self._parent: Optional["Doc"] = None
        self._key = None

    @classmethod
    def _cursor(cls, data: Any, parent: "Doc", key) -> "Doc":
        """Internal: wrap an already-legal subtree as a live child cursor."""
        self = object.__new__(cls)
        self._data = data
        self._parent = parent
        self._key = key
        return self

    @classmethod
    def from_data(cls, value: Any) -> "Doc":
        """Import an in-memory Python structure (dict/list/scalars) into a Doc."""
        return cls(value)

    @classmethod
    def from_format(cls, name: str, text: str) -> "Doc":
        """Read ``text`` with the named registered format into a Doc."""
        from .formats import get_format
        return cls(get_format(name).read(text))

    @classmethod
    def from_json(cls, text: str) -> "Doc":
        return cls.from_format("json", text)

    @classmethod
    def from_yaml(cls, text: str) -> "Doc":
        return cls.from_format("yaml", text)

    @classmethod
    def from_toml(cls, text: str) -> "Doc":
        return cls.from_format("toml", text)

    @classmethod
    def from_xml(cls, text: str) -> "Doc":
        return cls.from_format("xml", text)

    # -- identity / shape ----------------------------------------------
    @property
    def kind(self) -> str:
        if isinstance(self._data, dict):
            return "object"
        if isinstance(self._data, list):
            return "array"
        return "scalar"

    @property
    def parent(self) -> Optional["Doc"]:
        return self._parent

    @property
    def key(self):
        """This node's key (in an object) or index (in an array); None at root."""
        return self._key

    @property
    def path(self) -> str:
        if self._parent is None:
            return "$"
        base = self._parent.path
        if isinstance(self._key, int):
            return f"{base}[{self._key}]"
        return _join(base, self._key)

    @property
    def value(self) -> Any:
        """The scalar value of a scalar node.  Errors on objects/arrays."""
        self._attached()
        if _is_container(self._data):
            raise DocumentError(f"{self.path}: not a scalar (it is a {self.kind})")
        return self._data

    # -- object reads ---------------------------------------------------
    def has(self, key: str) -> bool:
        self._require("object")
        return key in self._data

    def keys(self) -> List[str]:
        self._require("object")
        return list(self._data.keys())

    def items(self) -> List[Tuple[str, Any]]:
        """(key, value-snapshot) pairs; container values are detached copies."""
        self._require("object")
        return [(k, _snapshot(v)) for k, v in self._data.items()]

    def get(self, key: str) -> Any:
        """A snapshot of the value at ``key`` (copy for containers, raw scalar)."""
        self._require("object")
        if key not in self._data:
            raise DocumentError(f"{self.path}: no key {key!r}")
        return _snapshot(self._data[key])

    def get_or(self, key: str, default: Any = None) -> Any:
        self._require("object")
        if key not in self._data:
            return default
        return _snapshot(self._data[key])

    def child(self, key: str) -> "Doc":
        """A live cursor into the object/array at ``key`` (errors on a scalar)."""
        self._require("object")
        if key not in self._data:
            raise DocumentError(f"{self.path}: no key {key!r}")
        v = self._data[key]
        if not _is_container(v):
            raise DocumentError(
                f"{_join(self.path, key)}: cannot navigate into a scalar; use get()")
        return Doc._cursor(v, self, key)

    # -- object writes --------------------------------------------------
    def add(self, key: str, value: Any) -> "Doc":
        """Add a new child under ``key`` (which must not already exist)."""
        self._require("object")
        if not isinstance(key, str):
            raise DocumentError("object key must be a string")
        if key in self._data:
            raise DocumentError(
                f"{self.path}: key {key!r} already exists; use set() or remove()")
        self._data[key] = _legalize(value, _join(self.path, key))
        return self

    def add_object(self, key: str) -> "Doc":
        """Add an empty object under ``key`` and return a cursor to it."""
        self.add(key, {})
        return self.child(key)

    def add_array(self, key: str) -> "Doc":
        """Add an empty array under ``key`` and return a cursor to it."""
        self.add(key, [])
        return self.child(key)

    # -- array reads ----------------------------------------------------
    def len(self) -> int:
        """Number of children (object keys or array elements)."""
        self._attached()
        if not _is_container(self._data):
            raise DocumentError(f"{self.path}: a scalar has no length")
        return len(self._data)

    def at(self, index: int) -> Any:
        """A snapshot of the array element at ``index``."""
        self._require("array")
        return _snapshot(self._data[self._index(index)])

    def child_at(self, index: int) -> "Doc":
        """A live cursor into the object/array element at ``index``."""
        self._require("array")
        v = self._data[self._index(index)]
        if not _is_container(v):
            raise DocumentError(
                f"{self.path}[{index}]: cannot navigate into a scalar; use at()")
        return Doc._cursor(v, self, self._index(index))

    # -- array writes ---------------------------------------------------
    def append(self, value: Any) -> "Doc":
        self._require("array")
        self._data.append(_legalize(value, f"{self.path}[{len(self._data)}]"))
        return self

    def append_object(self) -> "Doc":
        self._require("array")
        self._data.append({})
        return self.child_at(len(self._data) - 1)

    def append_array(self) -> "Doc":
        self._require("array")
        self._data.append([])
        return self.child_at(len(self._data) - 1)

    def insert(self, index: int, value: Any) -> "Doc":
        self._require("array")
        self._data.insert(index, _legalize(value, f"{self.path}[{index}]"))
        return self

    # -- shared writes (object key or array index) ----------------------
    def set(self, key, value: Any) -> "Doc":
        """Modify an existing **scalar** leaf in place.

        Refuses to overwrite a subtree or to store a container — reshaping the
        tree must go through ``remove`` + ``add``/``append``.
        """
        self._attached()
        if isinstance(value, (dict, list, tuple)):
            raise DocumentError(
                f"{self.path}: set() takes a scalar; use add/append to build structure")
        if self.kind == "object":
            if key not in self._data:
                raise DocumentError(
                    f"{self.path}: no key {key!r}; use add() to create it")
            target = _join(self.path, key)
            if _is_container(self._data[key]):
                raise DocumentError(
                    f"{target}: holds an {_kindof(self._data[key])}; "
                    "remove() then add() to replace a subtree")
            self._data[key] = _legalize(value, target)
        elif self.kind == "array":
            i = self._index(key)
            if _is_container(self._data[i]):
                raise DocumentError(
                    f"{self.path}[{i}]: holds an {_kindof(self._data[i])}; "
                    "remove() then insert() to replace a subtree")
            self._data[i] = _legalize(value, f"{self.path}[{i}]")
        else:
            raise DocumentError(f"{self.path}: cannot set on a scalar")
        return self

    def remove(self, key) -> "Doc":
        """Remove the whole subtree at ``key`` (object) or ``index`` (array)."""
        self._attached()
        if self.kind == "object":
            if key not in self._data:
                raise DocumentError(f"{self.path}: no key {key!r}")
            del self._data[key]
        elif self.kind == "array":
            del self._data[self._index(key)]
        else:
            raise DocumentError(f"{self.path}: cannot remove from a scalar")
        return self

    def drop(self) -> None:
        """Remove this node from its parent.  Errors at the root."""
        self._attached()
        if self._parent is None:
            raise DocumentError("cannot drop the root document")
        self._parent.remove(self._key)

    # -- serialization --------------------------------------------------
    def to_data(self) -> Any:
        """A detached deep copy of this node's data as plain Python."""
        self._attached()
        return _fast_deepcopy(self._data)

    def to_format(self, name: str, **opts: Any) -> str:
        self._attached()
        from .formats import get_format
        return get_format(name).write(self._data, **opts)

    def to_json(self, **opts: Any) -> str:
        return self.to_format("json", **opts)

    def to_yaml(self, **opts: Any) -> str:
        return self.to_format("yaml", **opts)

    def to_toml(self, **opts: Any) -> str:
        return self.to_format("toml", **opts)

    def to_xml(self, **opts: Any) -> str:
        return self.to_format("xml", **opts)

    # -- dunders --------------------------------------------------------
    def __len__(self) -> int:
        self._attached()
        if not _is_container(self._data):
            raise DocumentError(f"{self.path}: a scalar has no length")
        return len(self._data)

    def __iter__(self) -> Iterator:
        self._attached()
        if self.kind == "object":
            return iter(list(self._data.keys()))
        if self.kind == "array":
            return iter([_snapshot(v) for v in self._data])
        raise DocumentError(f"{self.path}: a scalar is not iterable")

    def __contains__(self, item: Any) -> bool:
        if self.kind == "object":
            return item in self._data
        if self.kind == "array":
            return item in self._data
        return False

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Doc):
            return self._data == other._data
        return self._data == other

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return f"Doc({self.kind}: {self._data!r})"

    # -- internals ------------------------------------------------------
    def _require(self, kind: str) -> None:
        self._attached()
        if self.kind != kind:
            raise DocumentError(
                f"{self.path}: expected a{'n' if kind[0] in 'aeiou' else ''} "
                f"{kind}, this node is a {self.kind}")

    def _attached(self) -> None:
        """Raise DetachedNode if this cursor's node is no longer in the document."""
        node = self
        while node._parent is not None:
            parent = node._parent
            try:
                current = parent._data[node._key]
            except (KeyError, IndexError, TypeError):
                raise DetachedNode(
                    f"{self.path}: this node was removed from the document") from None
            if current is not node._data:
                raise DetachedNode(
                    f"{self.path}: this node was removed from the document")
            node = parent

    def _index(self, index: Any) -> int:
        if not isinstance(index, int) or isinstance(index, bool):
            raise DocumentError(f"{self.path}: array index must be an integer")
        n = len(self._data)
        if index < -n or index >= n:
            raise DocumentError(f"{self.path}: index {index} out of range (len {n})")
        return index if index >= 0 else index + n


def _snapshot(v: Any) -> Any:
    return _fast_deepcopy(v) if _is_container(v) else v


def _fast_deepcopy(v: Any) -> Any:
    """Deep-copy a Document value without ``copy.deepcopy``'s generic
    dispatch/memo machinery.  Safe because a ``Doc`` only ever holds the
    Document model's own types (dict/list/scalars) -- the guard already
    enforces that on the way in -- so none of ``deepcopy``'s generality
    (arbitrary classes, ``__deepcopy__`` hooks, reference-cycle tracking) is
    needed; the result is the same, just faster.
    """
    if isinstance(v, dict):
        return {k: _fast_deepcopy(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_fast_deepcopy(x) for x in v]
    return v  # str/int/float/bool/None/date/time/datetime are all immutable


def _kindof(v: Any) -> str:
    return "object" if isinstance(v, dict) else "array"


# ===========================================================================
# Factory
# ===========================================================================

def doc(value: Any = _MISSING) -> Doc:
    """Build a Document.

    ``doc()`` is an empty object; ``doc(value)`` imports a Python structure
    (dict / list / scalars, tuples become lists), validating and copying it in.
    Raises :class:`DocumentError` if the value isn't a legal Document.
    """
    return Doc() if value is _MISSING else Doc(value)
