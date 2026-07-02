"""Schema operations package.

One module per algorithm from the paper (Lee & Cheung, "XML Schema Computations",
CIKM 2010).
"""

from .extract import extract
from .minimize import normalize
from .prune import is_empty, prune, satisfiable_set
from .subschema import compatible_with, equivalent

__all__ = [
    "compatible_with", "equivalent", "normalize",
    "is_empty", "prune", "satisfiable_set",
    "extract",
]
