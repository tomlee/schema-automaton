"""Schema Automaton (SA) — Definition 2 from the paper, generalised to be
data-format agnostic.

An SA is a 6-tuple (Q, X, q0, δ, Content, VDom) where:
    Q        finite set of states (each representing a data type)
    X        finite set of symbols (element names / object keys / array marker)
    q0       initial state
    δ        Q × X → Q ∪ {⊥}   transition function (missing key = ⊥)
    Content  Q → ContentModel   permissible children of a node in this state
    VDom     Q → value domain   permissible scalar value of a node in this state

The only change from the original paper is that the per-state *horizontal
language* (HLang) is generalised to a ``ContentModel`` so the same automaton can
describe ordered (XML / arrays) and unordered (JSON / TOML / YAML maps) content.
An HLang is simply the ordered ``SequenceModel``; the rest of the machinery is
unchanged.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set

from .content_model import ContentModel, ScalarModel
from .vdom import VDom
from .data_tree import DataTree


_DEAD = None  # sentinel for ⊥ (dead state)


def _is_null_node(node) -> bool:
    """True if a data node represents an explicit JSON/YAML/TOML null.

    A null scalar has kind SCALAR and a value domain hint with no scalar kinds
    (``VDom.null()``). This distinguishes it from an empty string (`""` with the
    STRS kind), which is a genuine string value, not null.
    """
    from .content_model import KIND_SCALAR
    vd = getattr(node, "vdom", None)
    return (node.kind == KIND_SCALAR and vd is not None and not vd.kinds)


class ValidationResult:
    """Outcome of :meth:`SchemaAutomaton.validate` with path-aware diagnostics."""

    def __init__(self) -> None:
        self.errors: List["ValidationError"] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        if self.ok:
            return "valid"
        return "invalid:\n" + "\n".join(f"  at {e.path}: {e.message}" for e in self.errors)


class ValidationError:
    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message

    def __repr__(self) -> str:
        return f"ValidationError({self.path!r}, {self.message!r})"


class SchemaAutomaton:
    """A deterministic automaton that validates Data Trees of any data format."""

    def __init__(self, initial: Any) -> None:
        self.states: Set[Any] = {initial}
        self.symbols: Set[str] = set()
        self.initial: Any = initial
        # δ[state][symbol] = next_state  (absent = ⊥)
        self.delta: Dict[Any, Dict[str, Any]] = {initial: {}}
        self.content: Dict[Any, ContentModel] = {}
        self.vdom: Dict[Any, VDom] = {}
        # states that also accept a JSON null in place of their normal structure
        # (i.e. nullable objects/arrays — "object | null", "array | null")
        self.nullable_struct: Dict[Any, bool] = {}

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def add_state(
        self,
        state: Any,
        content: Optional[ContentModel] = None,
        vdom: Optional[VDom] = None,
    ) -> None:
        self.states.add(state)
        self.delta.setdefault(state, {})
        if content is not None:
            self.content[state] = content
        if vdom is not None:
            self.vdom[state] = vdom

    def set_content(self, state: Any, content: ContentModel) -> None:
        self.content[state] = content

    def set_vdom(self, state: Any, vdom: VDom) -> None:
        self.vdom[state] = vdom

    def set_struct_nullable(self, state: Any, nullable: bool = True) -> None:
        """Mark a state as accepting a JSON null in place of its structure."""
        if nullable:
            self.nullable_struct[state] = True
        else:
            self.nullable_struct.pop(state, None)

    def is_struct_nullable(self, state: Any) -> bool:
        return self.nullable_struct.get(state, False)

    # Backward-compatible aliases (HLang is a ContentModel)
    set_hlang = set_content

    def add_transition(self, src: Any, symbol: str, dst: Any) -> None:
        self.symbols.add(symbol)
        self.delta.setdefault(src, {})[symbol] = dst

    def transition(self, state: Any, symbol: str) -> Optional[Any]:
        """δ(state, symbol) — returns None (⊥) if no transition defined."""
        return self.delta.get(state, {}).get(symbol, _DEAD)

    def get_content(self, state: Any) -> ContentModel:
        return self.content.get(state, ScalarModel())

    # Backward-compatible alias used by older call sites / tests
    get_hlang = get_content

    def get_vdom(self, state: Any) -> VDom:
        return self.vdom.get(state, VDom.strs())

    def _value_ok(self, state: Any, node) -> bool:
        """Validate a node's value against the state's value domain.

        When the node carries a type hint (``node.vdom`` — set by format loaders
        for typed JSON/TOML/YAML data), use type-aware admissibility so that,
        e.g., the number ``1`` is rejected where a string is expected.  Otherwise
        fall back to string-based containment (the paper's XML/XSD semantics).
        """
        schema_vd = self.get_vdom(state)
        if schema_vd.values is not None:           # enum: decide by value
            return schema_vd.contains(node.value)
        if getattr(node, "vdom", None) is not None:  # typed data
            return schema_vd.admits(node.vdom)
        return schema_vd.contains(node.value)        # untyped / XML

    # ------------------------------------------------------------------
    # Validation: SA accepts DT?  (Definition 3, with optional kind check)
    # ------------------------------------------------------------------

    def accepts(self, tree: DataTree) -> bool:
        """Return True if this SA accepts the given DataTree."""
        def _check(node_id: Any, state: Any) -> bool:
            n = tree.node(node_id)
            content = self.get_content(state)

            # Nullable object/array: a JSON null is accepted in place of the
            # node's normal structure.
            if self.is_struct_nullable(state) and _is_null_node(n):
                return True

            # Optional structural-kind agreement (distinguishes empty map vs seq
            # vs scalar when the data tree carries kind information).
            if n.kind is not None and content.kind and n.kind != content.kind:
                return False

            # Condition 2: value must be in VDom(state)
            if not self._value_ok(state, n):
                return False

            # Condition 3a: child symbol sequence must be in Content(state)
            cseq = tree.child_symbol_sequence(node_id)
            if not content.accepts(cseq):
                return False

            # Condition 3b: each child must be accepted by δ(state, symbol)
            for edge in tree.child_edges(node_id):
                next_state = self.transition(state, edge.symbol)
                if next_state is _DEAD:
                    # an additional property of an open map: any subtree allowed
                    if content.permits_untyped_child(edge.symbol):
                        continue
                    return False
                if not _check(edge.child_id, next_state):
                    return False
            return True

        return _check(tree.root_id, self.initial)

    def validate(self, tree: DataTree, item_symbol: str = "[]") -> ValidationResult:
        """Like :meth:`accepts`, but returns path-aware diagnostics.

        Reports every offending node it can reach (value-domain violations,
        disallowed/missing children, and unexpected child symbols), each with a
        JSON-path-like location such as ``$.users[].name``.
        """
        result = ValidationResult()

        def _path(parent: str, symbol: str) -> str:
            if symbol == item_symbol:
                return f"{parent}[]"
            return f"{parent}.{symbol}" if parent else symbol

        def _check(node_id: Any, state: Any, path: str) -> None:
            n = tree.node(node_id)
            content = self.get_content(state)

            if self.is_struct_nullable(state) and _is_null_node(n):
                return

            if n.kind is not None and content.kind and n.kind != content.kind:
                result.errors.append(ValidationError(
                    path, f"expected {content.kind.lower()} but found {n.kind.lower()}"))
                return

            if not self._value_ok(state, n):
                found = f" (found {n.vdom!r})" if getattr(n, "vdom", None) is not None else ""
                result.errors.append(ValidationError(
                    path, f"value {n.value!r}{found} not in {self.get_vdom(state)!r}"))

            cseq = tree.child_symbol_sequence(node_id)
            if not content.accepts(cseq):
                missing = content.mandatory_symbols() - set(cseq)
                allowed = content.symbols()
                unexpected = [s for s in cseq if s not in allowed and s != item_symbol] \
                    if content.kind == "MAP" else []
                detail = []
                if missing:
                    detail.append(f"missing required {sorted(missing)}")
                if unexpected:
                    detail.append(f"unexpected {sorted(set(unexpected))}")
                msg = "; ".join(detail) if detail else \
                    f"child sequence {cseq} not permitted by {content!r}"
                result.errors.append(ValidationError(path, msg))

            for edge in tree.child_edges(node_id):
                next_state = self.transition(state, edge.symbol)
                child_path = _path(path, edge.symbol)
                if next_state is _DEAD:
                    # already reported as unexpected/illegal above when relevant
                    continue
                _check(edge.child_id, next_state, child_path)

        _check(tree.root_id, self.initial, "$")
        return result

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def describe(self) -> str:
        lines = [f"SchemaAutomaton(initial={self.initial!r})"]
        lines.append(f"  States:  {sorted(str(s) for s in self.states)}")
        lines.append(f"  Symbols: {sorted(self.symbols)}")
        for q in sorted(self.states, key=str):
            content = self.get_content(q)
            v = self.get_vdom(q)
            trans = self.delta.get(q, {})
            lines.append(f"  {q}: Content={content!r}  VDom={v!r}  δ={trans}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"SchemaAutomaton(states={len(self.states)}, initial={self.initial!r})"
