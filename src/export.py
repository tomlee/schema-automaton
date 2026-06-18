"""Render a Schema Automaton as a human-readable, JSON-Schema-like dictionary.

This is a *view* of the canonical Schema Automaton — handy for inspecting an
inferred schema or documenting one.  It is not a full JSON Schema serializer;
it covers the structures the SA models (objects, arrays, scalars with the value
domains in ``vdom``).
"""

from __future__ import annotations
from typing import Any, Dict, Set

from .schema_automaton import SchemaAutomaton
from .content_model import KIND_MAP, KIND_SEQUENCE, MapModel
from .vdom import VDom
from .formats import ITEM


_KIND_TO_JSON = {
    VDom.STRS: "string",
    VDom.INTS: "integer",
    VDom.DECS: "number",
    VDom.BOOL: "boolean",
}


def _maybe_null(base: str, nullable: bool) -> Any:
    return [base, "null"] if nullable else base


def _vdom_type(vd: VDom) -> Any:
    if vd.enum is not None:
        enum = {"enum": sorted(vd.enum)}
        if vd.nullable:
            enum["enum"] = enum["enum"] + [None]
        return enum

    types = [_KIND_TO_JSON[k] for k in sorted(vd.kinds)]
    if vd.nullable:
        types.append("null")
    if not types:
        return "null"
    return types[0] if len(types) == 1 else types


def to_json_schema(sa: SchemaAutomaton, item_symbol: str = ITEM) -> Dict[str, Any]:
    """Return a JSON-Schema-like dict describing ``sa``'s language.

    Recursion through the automaton is guarded against cycles (recursive
    schemas) by emitting a ``{"$ref": "#recursive"}`` placeholder.
    """

    def _node(state: Any, seen: Set[Any]) -> Dict[str, Any]:
        if state in seen:
            return {"$ref": "#recursive"}
        seen = seen | {state}

        content = sa.get_content(state)
        vd = sa.get_vdom(state)
        nullable = sa.is_struct_nullable(state)

        if content.kind == KIND_MAP and isinstance(content, MapModel):
            props: Dict[str, Any] = {}
            required = sorted(content.mandatory_symbols())
            for key in sorted(content.fields):
                nxt = sa.transition(state, key)
                props[key] = _node(nxt, seen) if nxt is not None else {}
            schema: Dict[str, Any] = {"type": _maybe_null("object", nullable),
                                      "properties": props}
            if required:
                schema["required"] = required
            schema["additionalProperties"] = bool(content.open)
            return schema

        if content.kind == KIND_SEQUENCE and content.symbols():
            nxt = sa.transition(state, item_symbol)
            items = _node(nxt, seen) if nxt is not None else {}
            schema = {"type": _maybe_null("array", nullable), "items": items}
            if content.is_mandatory(item_symbol):
                schema["minItems"] = 1
            return schema

        # scalar (or empty sequence) leaf
        return {"type": _vdom_type(vd)}

    return _node(sa.initial, set())
