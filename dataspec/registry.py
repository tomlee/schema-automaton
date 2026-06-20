"""A small registry of format plugins.

Each format (JSON, YAML, TOML, XML, …) is described by a :class:`Format`: a name,
file extensions, optional dependencies, and the three codec callables
``read`` / ``write`` / ``check``.  Built-in formats register themselves when
``dataspec.formats`` is imported; a third party can add a new format simply by
calling :func:`register_format` from their own module — no change to dataspec.

    from dataspec import register_format, Format

    register_format(Format(
        name="csv", extensions=(".csv",),
        read=my_read, write=my_write, check=my_check,
    ))

The :class:`~dataspec.document.Doc` model dispatches through this registry, so a
newly registered format is immediately usable via ``Doc.from_format("csv", text)``
and ``doc.to_format("csv")``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from .report import WriteReport


@dataclass(frozen=True)
class Format:
    """A pluggable codec over the shared Document model."""

    name: str
    read: Callable[[str], Any]
    write: Callable[..., str]
    check: Callable[..., WriteReport]
    extensions: Tuple[str, ...] = ()
    requires: Tuple[str, ...] = ()        # optional third-party deps, for docs/errors


_FORMATS: Dict[str, Format] = {}
_LOCK = threading.Lock()


def register_format(fmt: Format) -> None:
    """Add (or replace) a format in the registry, keyed by ``fmt.name``.

    Thread-safe: registration is rare (typically once, at import time), so a
    lock costs nothing in practice but protects every lookup
    (``get_format``/``formats``/``Doc.from_format``/``to_format``) from racing
    a plugin registered from another thread.
    """
    with _LOCK:
        _FORMATS[fmt.name] = fmt


def get_format(name: str) -> Format:
    """Look up a registered format by name, or raise a clear error."""
    with _LOCK:
        try:
            return _FORMATS[name]
        except KeyError:
            known = ", ".join(sorted(_FORMATS)) or "(none)"
            raise KeyError(f"unknown format {name!r}; registered: {known}") from None


def formats() -> List[str]:
    """The names of all registered formats, sorted."""
    with _LOCK:
        return sorted(_FORMATS)
