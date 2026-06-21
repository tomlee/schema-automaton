"""Infer a Schema from example Documents, on the canonical model.

Given one or more sample Documents, draft a ``record``/``union`` schema that
accepts them:

* a label present in every sample with count 1 becomes a required field
  (``[1,1]``); absent in some samples -> ``[0,1]``; seen more than once ->
  an array (``[min,]``);
* scalar children become a ``Union`` of the observed kinds (nullable if any
  sample was null);
* object children become a nested, named ``record`` (recursively).

Since the model has no inline records, nested records are given generated
names derived from their label.  ``normalize`` afterwards merges any that turn
out structurally identical.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List

from ..errors import SchemaError
from .document import Doc, build_node
from .schema import (
    BOOLEAN,
    DATE,
    DATETIME,
    INTEGER,
    NUMBER,
    STRING,
    TIME,
    Field,
    Record,
    Ref,
    Schema,
    Union,
)


def infer(samples: List[Any], root_name: str = "Root") -> Schema:
    nodes = []
    for s in samples:
        nodes.append(s._node if isinstance(s, Doc) else build_node(s))
    if not nodes:
        raise SchemaError("cannot infer a schema from zero samples")
    if any(not isinstance(n, list) for n in nodes):
        raise SchemaError("infer expects object (record) samples at the root")
    env: Dict[str, Any] = {}
    used: set = set()
    _infer_record(nodes, root_name, env, used)
    return Schema(Ref(root_name), env)


def _unique(base: str, used: set) -> str:
    name = _identifier(base) or "Rec"
    name = name[0].upper() + name[1:]
    cand, i = name, 2
    while cand in used:
        cand = f"{name}{i}"
        i += 1
    used.add(cand)
    return cand


def _identifier(s: str) -> str:
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in s)
    return out.lstrip("0123456789_") or out


def _infer_record(nodes: List[Any], name: str, env: Dict[str, Any],
                  used: set) -> None:
    used.add(name)
    # collect, per label, the children across all samples and per-sample counts
    order: List[str] = []
    children: Dict[str, List[Any]] = {}
    per_sample_counts: Dict[str, List[int]] = {}
    for node in nodes:
        seen_here: Dict[str, int] = {}
        for label, child in node:
            if label not in children:
                children[label] = []
                per_sample_counts[label] = []
                order.append(label)
            children[label].append(child)
            seen_here[label] = seen_here.get(label, 0) + 1
        for label in children:
            per_sample_counts[label].append(seen_here.get(label, 0))

    fields: List[Field] = []
    for label in order:
        counts = per_sample_counts[label]
        lo, hi = min(counts), max(counts)
        if hi > 1:
            cmin, cmax = 0, None      # an array: be permissive on length
        else:
            cmin, cmax = lo, 1        # 0 or 1 -> optional/required
        typ = _infer_type(children[label], label, env, used)
        fields.append(Field(label, typ, cmin, cmax))
    env[name] = Record(fields)


def _infer_type(child_nodes: List[Any], label: str, env: Dict[str, Any],
                used: set) -> Any:
    is_obj = [isinstance(c, list) for c in child_nodes]
    if all(is_obj):
        rec_name = _unique(label, used)
        _infer_record(child_nodes, rec_name, env, used)
        return Ref(rec_name)
    if any(is_obj):
        raise SchemaError(
            f"label {label!r} mixes objects and values; cannot infer one type")
    # all scalars
    kinds, null = set(), False
    for v in child_nodes:
        if v is None:
            null = True
        else:
            kinds.add(_value_kind(v))
    if NUMBER in kinds:
        kinds.discard(INTEGER)
    if not kinds and not null:
        return Union(kinds=(STRING,))           # only-empty corpus -> string
    return Union(kinds=kinds, null=null)


def _value_kind(v: Any):
    if isinstance(v, bool):
        return BOOLEAN
    if isinstance(v, int):
        return INTEGER
    if isinstance(v, float):
        return NUMBER
    if isinstance(v, _dt.datetime):
        return DATETIME
    if isinstance(v, _dt.date):
        return DATE
    if isinstance(v, _dt.time):
        return TIME
    return STRING
