"""Format codecs: read a syntax into a Document, write a Document to a syntax.

A **Document** is plain Python data (`dict`, `list`, `str`, `int`, `float`,
`bool`, `None`, and `datetime` values).  Every format is a codec over the same
Document, so converting between them is just *read one, write another*::

    write_toml(read_json('{"name": "Ann"}'))

Each writer enforces what its format can represent and raises ``WriteError``
rather than producing something invalid:

* **JSON / YAML** carry everything (incl. ``null``); temporal values downgrade to
  ISO-8601 strings in JSON.
* **TOML / XML** have no ``null``: a ``null`` *object field* is **omitted**;
  a ``null`` *array item* or a *top-level* ``null`` raises ``WriteError``
  (pass ``strict=True`` to also raise on omitted fields).  TOML/XML also require
  a top-level object.

YAML is restricted to its JSON-compatible core (string keys, a tree, standard
scalars).  XML is restricted to data-XML: elements only — no attributes, mixed
content, namespaces, or CDATA constructs; repeated child names become lists.
XML scalars are untyped text, so they are read back with best-effort typing.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
from typing import Any, Optional

from .errors import ParseError, WriteError


# ===========================================================================
# JSON
# ===========================================================================

def read_json(text: str) -> Any:
    return _json.loads(text)


def write_json(data: Any, *, indent: Optional[int] = None, sort_keys: bool = False) -> str:
    return _json.dumps(data, indent=indent, sort_keys=sort_keys,
                       ensure_ascii=False, default=_iso)


def _iso(o: Any) -> str:
    if isinstance(o, (_dt.date, _dt.time)):
        return o.isoformat()
    raise TypeError(f"cannot serialize {type(o).__name__}")


# ===========================================================================
# YAML  (core / JSON-compatible subset)
# ===========================================================================

def read_yaml(text: str) -> Any:
    yaml = _need("yaml", "PyYAML", "pip install pyyaml")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover
        raise ParseError(f"invalid YAML: {exc}") from exc
    _yaml_core_check(data, "$", set())
    return data


def write_yaml(data: Any, *, sort_keys: bool = False) -> str:
    yaml = _need("yaml", "PyYAML", "pip install pyyaml")
    return yaml.safe_dump(data, sort_keys=sort_keys, allow_unicode=True,
                          default_flow_style=False)


def _yaml_core_check(node: Any, path: str, seen: set) -> None:
    if isinstance(node, dict):
        if id(node) in seen:
            raise ParseError(f"recursive YAML (anchors/aliases) at {path} is not supported")
        seen = seen | {id(node)}
        for k, v in node.items():
            if not isinstance(k, str):
                raise ParseError(f"non-string key {k!r} at {path} is not supported")
            _yaml_core_check(v, f"{path}.{k}", seen)
    elif isinstance(node, list):
        if id(node) in seen:
            raise ParseError(f"recursive YAML at {path} is not supported")
        seen = seen | {id(node)}
        for i, v in enumerate(node):
            _yaml_core_check(v, f"{path}[{i}]", seen)


# ===========================================================================
# TOML
# ===========================================================================

def read_toml(text: str) -> Any:
    try:
        import tomllib as toml
    except ImportError:  # pragma: no cover
        toml = _need("tomli", "tomli", "pip install tomli")
    return toml.loads(text)


def write_toml(data: Any, *, strict: bool = False) -> str:
    tomli_w = _need("tomli_w", "tomli_w", "pip install tomli_w")
    clean = _drop_nulls(data, "$", strict)
    if not isinstance(clean, dict):
        raise WriteError("TOML needs a top-level object; "
                         f"got {_name(clean)}")
    return tomli_w.dumps(clean)


def _drop_nulls(data: Any, path: str, strict: bool) -> Any:
    """Apply null Option C: omit null object-fields; reject null in arrays / top."""
    if data is None:
        raise WriteError(f"null at {path} cannot be represented (TOML/XML have no null)")
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if v is None:
                if strict:
                    raise WriteError(f"null field at {path}.{k} (strict mode)")
                continue  # omit
            out[k] = _drop_nulls(v, f"{path}.{k}", strict)
        return out
    if isinstance(data, list):
        return [_drop_nulls(v, f"{path}[{i}]", strict) for i, v in enumerate(data)]
    return data


# ===========================================================================
# XML  (data-XML profile)
# ===========================================================================

def read_xml(text: str) -> Any:
    """Read data-XML into a Document.  The root element is a wrapper; its content
    is returned.  Scalars are untyped text, read back with best-effort typing."""
    ET = _xml_parser()
    try:
        root = ET.fromstring(text)
    except Exception as exc:  # pragma: no cover
        raise ParseError(f"invalid XML: {exc}") from exc
    return _xml_to_data(root, "$")


def write_xml(data: Any, *, root: str = "root", strict: bool = False) -> str:
    clean = _drop_nulls(data, "$", strict)
    if isinstance(clean, list):
        raise WriteError("XML cannot represent a top-level array (lists must be named "
                         "fields)")
    import xml.etree.ElementTree as ET
    el = ET.Element(root)
    _data_to_xml(clean, el)
    _indent(el)
    return ET.tostring(el, encoding="unicode")


def _xml_to_data(elem, path: str) -> Any:
    if elem.attrib:
        raise ParseError(f"attributes at {path} are not supported (data-XML)")
    children = list(elem)
    if children:
        if (elem.text and elem.text.strip()):
            raise ParseError(f"mixed content at {path} is not supported")
        grouped = {}
        order = []
        for child in children:
            if child.tail and child.tail.strip():
                raise ParseError(f"mixed content at {path} is not supported")
            tag = _local(child.tag)
            if tag not in grouped:
                grouped[tag] = []
                order.append(tag)
            grouped[tag].append(_xml_to_data(child, f"{path}.{tag}"))
        return {tag: (vs[0] if len(vs) == 1 else vs) for tag in order
                for vs in [grouped[tag]]}
    return _coerce(elem.text or "")


def _data_to_xml(data: Any, parent) -> None:
    import xml.etree.ElementTree as ET
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                for item in v:
                    child = ET.SubElement(parent, k)
                    _data_to_xml(item, child)
            else:
                child = ET.SubElement(parent, k)
                _data_to_xml(v, child)
    elif isinstance(data, list):
        raise WriteError("a bare/nested array has no element name in XML")
    else:
        parent.text = _xml_text(data)


def _xml_text(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (_dt.date, _dt.time)):
        return v.isoformat()
    return str(v)


def _coerce(text: str) -> Any:
    """Best-effort typing of XML text (XML scalars are untyped)."""
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
        import defusedxml.ElementTree as ET  # safe against XXE / billion-laughs
        return ET
    except ImportError:  # pragma: no cover
        import xml.etree.ElementTree as ET
        return ET


# ===========================================================================
# shared
# ===========================================================================

def _need(module: str, name: str, how: str):
    try:
        return __import__(module)
    except ImportError as exc:  # pragma: no cover
        raise ImportError(f"{name} is required: {how}") from exc


def _name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__
