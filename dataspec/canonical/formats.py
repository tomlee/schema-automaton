"""Codecs over the canonical Document (edge-list) model.

Readers parse a format into a node; writers project a node back.  JSON/YAML/TOML
go through the JSON-shaped grouping (``to_grouped``); XML uses repeated elements
directly, so it preserves interleaving on read and needs a single document
element on write.

These are intentionally simpler than the v0.1 codecs (no adjustment reports yet)
— enough to round-trip documents for the new model.  Strict/report machinery
will return in a later phase.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
import re as _re
import warnings
from typing import Any, Callable

from ..errors import ParseError, UnsafeXMLWarning, WriteError
from .document import _grouped, build_node


def get_reader(name: str) -> Callable[[str], Any]:
    return {"json": read_json, "yaml": read_yaml, "toml": read_toml,
            "xml": read_xml}[name]


# --------------------------------------------------------------- JSON
def read_json(text: str) -> Any:
    try:
        return build_node(_json.loads(text))
    except _json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc


def write_json(node: Any, *, indent: int = None) -> str:
    return _json.dumps(_grouped(node), indent=indent, ensure_ascii=False, default=_iso)


def _iso(o: Any) -> str:
    if isinstance(o, (_dt.date, _dt.time)):
        return o.isoformat()
    raise TypeError(f"cannot serialize {type(o).__name__}")


# --------------------------------------------------------------- YAML
def read_yaml(text: str) -> Any:
    yaml = _need("yaml", "pip install pyyaml")
    try:
        return build_node(yaml.safe_load(text))
    except yaml.YAMLError as exc:  # pragma: no cover
        raise ParseError(f"invalid YAML: {exc}") from exc


def write_yaml(node: Any) -> str:
    yaml = _need("yaml", "pip install pyyaml")
    return yaml.safe_dump(_grouped(node), sort_keys=False, allow_unicode=True,
                          default_flow_style=False)


# --------------------------------------------------------------- TOML
def read_toml(text: str) -> Any:
    import tomllib
    try:
        return build_node(tomllib.loads(text))
    except tomllib.TOMLDecodeError as exc:
        raise ParseError(f"invalid TOML: {exc}") from exc


def write_toml(node: Any) -> str:
    tomli_w = _need("tomli_w", "pip install tomli_w")
    grouped = _grouped(node)
    if not isinstance(grouped, dict):
        raise WriteError("TOML needs a top-level table (the root must be an object)")
    return tomli_w.dumps(grouped)


# --------------------------------------------------------------- XML
_XML_NAME = _re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")


def read_xml(text: str) -> Any:
    ET = _xml_parser()
    try:
        root = ET.fromstring(text)
    except Exception as exc:  # pragma: no cover
        raise ParseError(f"invalid XML: {exc}") from exc
    return [(_local(root.tag), _xml_to_node(root))]


def _xml_to_node(elem) -> Any:
    children = list(elem)
    if children:
        return [(_local(c.tag), _xml_to_node(c)) for c in children]
    return _coerce(elem.text or "")


def write_xml(node: Any) -> str:
    if not (isinstance(node, list) and len(node) == 1):
        raise WriteError(
            "XML needs exactly one document element; the root node must have a "
            "single top-level edge (a single-rooted Document)")
    import xml.etree.ElementTree as ET
    (tag, content), = node
    el = ET.Element(_xml_name(tag))
    _node_to_xml(content, el)
    _indent(el)
    return ET.tostring(el, encoding="unicode")


def _node_to_xml(content: Any, parent) -> None:
    import xml.etree.ElementTree as ET
    if isinstance(content, list):
        for label, child in content:
            sub = ET.SubElement(parent, _xml_name(label))
            _node_to_xml(child, sub)
    else:
        parent.text = _xml_text(content)


def _xml_name(name: str) -> str:
    if _XML_NAME.match(name):
        return name
    safe = _re.sub(r"[^A-Za-z0-9_.\-]", "_", name)
    if not safe or not _XML_NAME.match(safe):
        safe = "_" + safe
    return safe


def _xml_text(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    if isinstance(v, (_dt.date, _dt.time)):
        return v.isoformat()
    return str(v)


def _coerce(text: str) -> Any:
    if text == "":
        return ""
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _indent(elem, level: int = 0) -> None:
    pad = "\n" + "  " * level
    children = list(elem)
    if children:
        if not (elem.text and elem.text.strip()):
            elem.text = pad + "  "
        for i, child in enumerate(children):
            _indent(child, level + 1)
            child.tail = (pad + "  ") if i < len(children) - 1 else pad
        if not (elem.tail and elem.tail.strip()):
            elem.tail = pad if level else "\n"


def _xml_parser():
    try:
        import defusedxml.ElementTree as ET
        return ET
    except ImportError:
        warnings.warn(
            "defusedxml is not installed; read_xml() uses the standard library's "
            "XML parser, which is vulnerable to entity-expansion / XXE attacks on "
            "untrusted input. pip install defusedxml to fix this.",
            UnsafeXMLWarning, stacklevel=3)
        import xml.etree.ElementTree as ET
        return ET


def _need(module: str, how: str):
    try:
        return __import__(module)
    except ImportError as exc:  # pragma: no cover
        raise ImportError(f"{module} is required: {how}") from exc
