"""Schema operations package.

One module per algorithm from the paper (Lee & Cheung, "XML Schema Computations",
CIKM 2010).
"""

from .minimize import normalize
from .subschema import compatible_with, equivalent

__all__ = ["compatible_with", "equivalent", "normalize"]
