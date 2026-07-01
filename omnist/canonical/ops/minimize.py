"""Schema minimization: merge structurally identical named records.

To be rewritten as the paper's Algorithm 2 (MinimizeSA).
"""

from __future__ import annotations

from typing import Any, Dict

from ..schema import Field, Record, Ref, Schema
from .signature import struct_key


def normalize(s: Schema) -> Schema:
    """An equivalent schema with structurally-identical named records merged."""
    groups: Dict[tuple, list[str]] = {}
    for name, rec in s.env.items():
        groups.setdefault(struct_key(rec), []).append(name)
    rep: Dict[str, str] = {}
    for names in groups.values():
        keep = sorted(names)[0]
        for n in names:
            rep[n] = keep
    new_env: Dict[str, Any] = {}
    for name, rec in s.env.items():
        if rep[name] == name:
            new_env[name] = _remap(rec, rep)
    new_root = Ref(rep.get(s.root.name, s.root.name))
    return Schema(new_root, new_env)


def _remap(rec: Record, rep: Dict[str, str]) -> Record:
    return Record([Field(f.label, _remap_type(f.type, rep), f.min, f.max)
                   for f in rec.fields])


def _remap_type(t, rep: Dict[str, str]):
    if isinstance(t, Ref):
        return Ref(rep.get(t.name, t.name))
    return t
