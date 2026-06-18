"""Format-agnostic bridge: load JSON / YAML / TOML (and plain Python data) into
the canonical Data Tree model, and infer a canonical Schema Automaton from
sample data trees.

The Data Tree / Schema Automaton models are deliberately independent of any
concrete schema language (XSD, JSON Schema, ...).  This module is the only place
that knows about specific data formats; it maps each format's native data model
onto the canonical Data Tree:

    object / map / table   →  d-node of kind MAP,   one child d-edge per key
    array  / sequence      →  d-node of kind SEQUENCE, child d-edges all labelled
                              with the array item marker ``ITEM``
    scalar (str/num/bool/null) → leaf d-node of kind SCALAR; the value's string
                              form is stored and a VDom hint is attached

Because every format collapses to the same Data Tree shape, a single Schema
Automaton can validate data that originated as JSON, YAML or TOML — and a schema
inferred from, say, JSON samples can be checked against YAML data for free.
"""

from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .data_tree import DataTree
from .schema_automaton import SchemaAutomaton
from .content_model import MapModel, ScalarModel, KIND_MAP, KIND_SEQUENCE, KIND_SCALAR
from .hlang import HLang
from .vdom import VDom
from .nfa import nfa_symbol, nfa_star, nfa_plus
from .algorithms import minimize_sa


#: symbol used to label every element edge of an array/sequence node
ITEM = "[]"


# ===========================================================================
# Scalar value classification
# ===========================================================================

def _scalar(value: Any) -> Tuple[str, VDom, str]:
    """Map a Python scalar to (string form, VDom, kind=SCALAR)."""
    if value is None:
        return "", VDom.null(), KIND_SCALAR
    if isinstance(value, bool):
        return ("true" if value else "false"), VDom.bool_(), KIND_SCALAR
    if isinstance(value, int):
        return str(value), VDom.ints(), KIND_SCALAR
    if isinstance(value, float):
        return repr(value), VDom.decs(), KIND_SCALAR
    if isinstance(value, str):
        return value, VDom.strs(), KIND_SCALAR
    # dates, times, etc. (e.g. from TOML) — keep their textual form
    return str(value), VDom.strs(), KIND_SCALAR


# ===========================================================================
# Python object  →  Data Tree
# ===========================================================================

def tree_from_python(obj: Any, item_symbol: str = ITEM) -> DataTree:
    """Build a canonical DataTree from a parsed Python value (dict/list/scalar)."""
    counter = [0]

    def _new_id() -> int:
        counter[0] += 1
        return counter[0]

    # Determine root descriptor
    def _describe(value: Any) -> Tuple[str, Any, Optional[VDom]]:
        if isinstance(value, dict):
            return "", KIND_MAP, VDom.null()
        if isinstance(value, (list, tuple)):
            return "", KIND_SEQUENCE, VDom.null()
        v, vd, _ = _scalar(value)
        return v, KIND_SCALAR, vd

    root_val, root_kind, root_vd = _describe(obj)
    tree = DataTree(root_id=0, root_value=root_val, root_kind=root_kind, root_vdom=root_vd)

    def _populate(parent_id: int, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                cval, ckind, cvd = _describe(child)
                cid = _new_id()
                tree.add_node(cid, cval, kind=ckind, vdom=cvd)
                tree.add_edge(parent_id, cid, str(key))
                _populate(cid, child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                cval, ckind, cvd = _describe(child)
                cid = _new_id()
                tree.add_node(cid, cval, kind=ckind, vdom=cvd)
                tree.add_edge(parent_id, cid, item_symbol)
                _populate(cid, child)
        # scalars: no children

    _populate(0, obj)
    return tree


# ===========================================================================
# Format-specific loaders
# ===========================================================================

def tree_from_json(text: str, item_symbol: str = ITEM) -> DataTree:
    import json
    return tree_from_python(json.loads(text), item_symbol)


def tree_from_yaml(text: str, item_symbol: str = ITEM) -> DataTree:
    try:
        import yaml  # PyYAML
    except ImportError as exc:  # pragma: no cover
        raise ImportError("PyYAML is required for YAML support: pip install pyyaml") from exc
    return tree_from_python(yaml.safe_load(text), item_symbol)


def tree_from_toml(text: str, item_symbol: str = ITEM) -> DataTree:
    try:
        import tomllib as toml  # Python 3.11+
        data = toml.loads(text)
    except ImportError:
        try:
            import tomli as toml  # backport
            data = toml.loads(text)
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "A TOML parser is required: use Python 3.11+ or `pip install tomli`"
            ) from exc
    return tree_from_python(data, item_symbol)


# ===========================================================================
# Schema inference:  sample Data Trees  →  canonical Schema Automaton
# ===========================================================================

def _seq_model(item_symbol: str, plus: bool) -> HLang:
    """Build the ordered content model item* or item+ for an array node."""
    base = nfa_symbol(item_symbol)
    nfa = nfa_plus(base) if plus else nfa_star(base)
    return HLang(nfa, f"{item_symbol}{'+' if plus else '*'}")


class SchemaInferencer:
    """Infers a single canonical SchemaAutomaton from sample data trees.

    The trees are assumed to be instances of one common top-level type.  Sibling
    values that must share a type are generalised together:

        * MAP nodes      → fields = union of keys; a field is *required* only if
                           present in every sample, otherwise *optional*
        * SEQUENCE nodes → one item type generalised over all elements; item* if
                           any array was empty, else item+
        * SCALAR nodes   → VDom generalised via VDom.union (nullable as needed)

    Structurally heterogeneous groups (e.g. object in one sample, scalar in
    another) are reported as a ValueError, except that a ``null`` sample is
    absorbed as nullability of the co-occurring type.
    """

    def __init__(self, item_symbol: str = ITEM, open_maps: bool = False) -> None:
        self.item_symbol = item_symbol
        self.open_maps = open_maps
        self.sa = SchemaAutomaton(0)
        self._counter = 0

    def _alloc(self) -> int:
        self._counter += 1
        return self._counter

    def infer(self, trees: Iterable[DataTree]) -> SchemaAutomaton:
        roots = [(t, t.root_id) for t in trees]
        if not roots:
            raise ValueError("Cannot infer a schema from zero sample trees.")
        self._build(roots, state_id=0)
        return minimize_sa(self.sa)

    # ------------------------------------------------------------------
    def _node_kind(self, tree: DataTree, node_id: Any) -> str:
        n = tree.node(node_id)
        if n.kind is not None:
            return n.kind
        edges = tree.child_edges(node_id)
        if not edges:
            return KIND_SCALAR
        if all(e.symbol == self.item_symbol for e in edges):
            return KIND_SEQUENCE
        return KIND_MAP

    def _build(self, group: List[Tuple[DataTree, Any]], state_id: int) -> None:
        tagged = [(t, n, self._node_kind(t, n)) for t, n in group]
        structural = {k for _, _, k in tagged if k in (KIND_MAP, KIND_SEQUENCE)}

        if len(structural) > 1:
            raise ValueError(
                "Cannot infer a single type for a group mixing "
                f"{sorted(structural)} (union of object and array). "
                "Mixed object/array union types are not representable by one "
                "Schema Automaton state."
            )

        if structural:
            # A structural type may coexist with JSON nulls — that is a nullable
            # object/array, which we DO support (the state is marked nullable).
            # But it must not coexist with a *non-null* scalar, which would be a
            # genuine union (e.g. 'object | string'); reject rather than drop data.
            non_null_scalars = [(t, n) for t, n, k in tagged
                                if k == KIND_SCALAR and not _is_null(t, n)]
            if non_null_scalars:
                kind = next(iter(structural))
                raise ValueError(
                    f"Cannot infer a single type for a group mixing {kind} with a "
                    f"non-null scalar value ('{kind.lower()} | scalar'). Such union "
                    "types are not supported (nullable objects/arrays, i.e. "
                    f"'{kind.lower()} | null', ARE supported)."
                )
            nullable = any(k == KIND_SCALAR and _is_null(t, n) for t, n, k in tagged)
            struct_group = [(t, n) for t, n, k in tagged if k in (KIND_MAP, KIND_SEQUENCE)]
            if KIND_MAP in structural:
                self._build_map(struct_group, state_id, nullable=nullable)
            else:
                self._build_sequence(struct_group, state_id, nullable=nullable)
        else:
            self._build_scalar([(t, n) for t, n, k in tagged], state_id)

    # ------------------------------------------------------------------
    def _build_scalar(self, group: List[Tuple[DataTree, Any]], state_id: int) -> None:
        vdom: Optional[VDom] = None
        for tree, nid in group:
            n = tree.node(nid)
            v = n.vdom if n.vdom is not None else _scalar_from_value(n.value)
            vdom = v if vdom is None else VDom.union(vdom, v)
        self.sa.add_state(state_id, ScalarModel(), vdom or VDom.strs())

    # ------------------------------------------------------------------
    def _build_sequence(self, group: List[Tuple[DataTree, Any]], state_id: int,
                        nullable: bool = False) -> None:
        # Pool all element nodes across every array in the group.
        elements: List[Tuple[DataTree, Any]] = []
        any_empty = False
        for tree, nid in group:
            edges = tree.child_edges(nid)
            if not edges:
                any_empty = True
            for e in edges:
                elements.append((tree, e.child_id))

        if not elements:
            # Only ever saw empty arrays — we have no evidence of an element
            # type, so the canonical inference is "the empty sequence only".
            # (Using item* here would be inconsistent: the content language would
            # admit `item` while δ has no transition for it, violating Def. 2.)
            self.sa.add_state(state_id, HLang.epsilon_lang(), VDom.null())
            self.sa.set_struct_nullable(state_id, nullable)
            return

        self.sa.add_state(
            state_id,
            _seq_model(self.item_symbol, plus=not any_empty),
            VDom.null(),
        )
        self.sa.set_struct_nullable(state_id, nullable)
        item_state = self._alloc()
        self.sa.add_transition(state_id, self.item_symbol, item_state)
        self._build(elements, item_state)

    # ------------------------------------------------------------------
    def _build_map(self, group: List[Tuple[DataTree, Any]], state_id: int,
                  nullable: bool = False) -> None:
        n_samples = len(group)
        # Collect, per key, the child nodes and how many samples contain the key.
        key_children: Dict[str, List[Tuple[DataTree, Any]]] = {}
        key_count: Dict[str, int] = {}
        for tree, nid in group:
            seen_keys = set()
            for e in tree.child_edges(nid):
                key_children.setdefault(e.symbol, []).append((tree, e.child_id))
                seen_keys.add(e.symbol)
            for k in seen_keys:
                key_count[k] = key_count.get(k, 0) + 1

        fields: Dict[str, bool] = {
            key: (key_count[key] == n_samples) for key in key_children
        }
        self.sa.add_state(state_id, MapModel(fields, open=self.open_maps), VDom.null())
        self.sa.set_struct_nullable(state_id, nullable)

        for key, children in key_children.items():
            child_state = self._alloc()
            self.sa.add_transition(state_id, key, child_state)
            self._build(children, child_state)


def _is_null(tree: DataTree, node_id: Any) -> bool:
    """True if the node is an explicit JSON/YAML/TOML null (scalar, VDom.null())."""
    n = tree.node(node_id)
    if n.kind not in (None, KIND_SCALAR):
        return False
    if tree.child_edges(node_id):
        return False
    return n.vdom is not None and not n.vdom.kinds


def _scalar_from_value(value: str) -> VDom:
    """Best-effort VDom inference from a bare string value (no hint available)."""
    if value in ("", None):
        return VDom.null()
    if str(value).lower() in ("true", "false"):
        return VDom.bool_()
    try:
        int(value)
        return VDom.ints()
    except (ValueError, TypeError):
        pass
    try:
        float(value)
        return VDom.decs()
    except (ValueError, TypeError):
        pass
    return VDom.strs()


def infer_schema(trees: Iterable[DataTree], item_symbol: str = ITEM,
                 open_maps: bool = False) -> SchemaAutomaton:
    """Convenience wrapper: infer a canonical SchemaAutomaton from sample trees.

    Set ``open_maps=True`` to infer *open* objects (additional, undeclared keys
    are permitted) rather than the default closed objects.
    """
    return SchemaInferencer(item_symbol, open_maps=open_maps).infer(list(trees))
