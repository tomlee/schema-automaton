"""Field-signature helpers for schema minimization (and, later, isomorphism).

``struct_key`` is the structural identity used by ``normalize`` today: the
full per-field shape INCLUDING ref target names.  The partition-refinement
rewrite (MinimizeSA, issue #140) will add a target-blind variant here when
it lands, shared with the isomorphism check (issue #141).
"""

from __future__ import annotations

from typing import Tuple, Union

from ..schema import Record, Ref, Scalar


def struct_key(rec: Record) -> Tuple:
    """The structural key for a record, including ref target names."""
    fields = tuple(
        (f.label, f.min, f.max, _type_key(f.type))
        for f in rec.fields
    )
    return ("record", fields)


def _type_key(t: Union[Ref, Scalar]) -> Tuple:
    if isinstance(t, Ref):
        return ("ref", t.name)
    return ("scalar", t.name, t.nullable)
