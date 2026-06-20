"""Format codecs: read a syntax into a Document, write a Document to a syntax.

A **Document** is plain Python data (`dict`, `list`, `str`, `int`, `float`,
`bool`, `None`, and `datetime` values).  Every format is a codec over the same
Document, so converting between them is just *read one, write another*::

    write_toml(read_json('{"name": "Ann"}'))

**Conversion is lenient by default.**  When a target format can't hold a value
losslessly (TOML/XML have no ``null``; JSON has no dates), the writer *adjusts*
the data and records what it did in a :class:`~dataspec.report.WriteReport`
rather than raising.  You choose how much you want to know:

* ``write_toml(doc)`` — just the output; adjustments are made silently.
* ``write_toml(doc, report=rep)`` — output, plus ``rep`` lists every change.
* ``check_toml(doc)`` — the report only, no output; nothing is raised.
* ``write_toml(doc, strict=True)`` — raises ``WriteError`` (carrying the report)
  if anything can't round-trip, guaranteeing lossless output.

Adjustment knobs:

* ``null_style`` (TOML/XML) — ``"omit"`` (default) flags a dropped *array* item
  as an error-severity adjustment; ``"drop"`` treats it as an ordinary warning.
  Null *object fields* are always omitted (warning) either way.
* ``wrap_key`` (TOML) — the key a top-level array/scalar is wrapped under,
  since TOML requires a top-level object.

YAML is restricted to its JSON-compatible core (string keys, a tree, standard
scalars); a standalone time-of-day is written as a string.  XML is restricted to
data-XML: elements only — no attributes, mixed content, namespaces, or CDATA;
repeated child names become lists.  XML scalars are untyped text, so they are
read back with best-effort typing.

XML is **single-rooted**: an XML document has exactly one top-level element, so
``read_xml``/``write_xml`` work with a Document that has exactly one top-level
key (e.g. ``{"x": {"y": 1}}``  <->  ``<x><y>1</y></x>``) -- the document
element's tag *is* that key, not a discardable wrapper.  A Document that isn't
single-rooted (multiple top-level keys, or a top-level list/scalar) has no
single XML document representation; use ``read_xml_documents``/
``write_xml_documents`` instead, which translate a Document <-> a *forest* of
XML documents (one per top-level key, repeated for a list value).
"""

from __future__ import annotations

import datetime as _dt
import json as _json
import math as _math
import re as _re
from typing import Any, Optional, Tuple

from .errors import DocumentError, ParseError, UnsafeXMLWarning, WriteError
from .report import WriteReport, finish_write

# Bounds recursion depth well under Python's default recursion limit (1000),
# so deeply/adversarially nested data raises a clean error instead of
# crashing the process with an uncatchable RecursionError.
_MAX_DEPTH = 200


def _depth_guard(path: str, depth: int) -> None:
    if depth > _MAX_DEPTH:
        raise DocumentError(
            f"{path}: nesting exceeds the maximum depth ({_MAX_DEPTH})")


def _json_key_str(k: Any) -> str:
    """The key string ``json.dumps`` would emit for a non-string dict key."""
    if isinstance(k, bool):
        return "true" if k else "false"
    if k is None:
        return "null"
    return str(k)


# ===========================================================================
# JSON
# ===========================================================================

# JavaScript represents all numbers as IEEE-754 doubles, which can only
# represent integers exactly up to 2**53 (Number.MAX_SAFE_INTEGER). A Python
# int beyond this round-trips exactly through dataspec's own read_json (it
# uses arbitrary-precision ints), but silently loses precision in a
# JS-based JSON parser -- the same class of interop risk as TOML's i64 limit.
_JS_SAFE_INT_MAX = 2 ** 53
_JS_SAFE_INT_MIN = -(2 ** 53)


def read_json(text: str) -> Any:
    try:
        return _json.loads(text)
    except _json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc


def write_json(data: Any, *, indent: Optional[int] = None, sort_keys: bool = False,
               strict: bool = False, report: Optional[WriteReport] = None) -> str:
    text, rep = _serialize_json(data, indent=indent, sort_keys=sort_keys)
    return finish_write(text, rep, strict=strict, report=report)


def check_json(data: Any) -> WriteReport:
    """Simulate writing JSON and return the report without producing output."""
    _text, rep = _serialize_json(data, indent=None, sort_keys=False)
    return rep


def _serialize_json(data: Any, *, indent: Optional[int],
                    sort_keys: bool) -> Tuple[str, WriteReport]:
    rep = WriteReport()
    _scan_json(data, "$", rep, 0)
    text = _json.dumps(data, indent=indent, sort_keys=sort_keys,
                       ensure_ascii=False, default=_iso)
    return text, rep


def _scan_json(data: Any, path: str, rep: WriteReport, depth: int) -> None:
    if isinstance(data, bool):
        return
    if isinstance(data, int):
        if not (_JS_SAFE_INT_MIN <= data <= _JS_SAFE_INT_MAX):
            rep.add(path, "integer.precision_risk",
                    f"{data} exceeds JavaScript's safe integer range "
                    "(±2**53) and may lose precision in a JS-based "
                    "JSON parser, even though it round-trips exactly here",
                    "warning")
        return
    if isinstance(data, float):
        if _math.isnan(data) or _math.isinf(data):
            rep.add(path, "float.special",
                    f"{data} is not valid JSON (emitted as-is)", "error")
        return
    if isinstance(data, (_dt.date, _dt.time)):
        rep.add(path, "temporal.stringified",
                "temporal value written as an ISO-8601 string", "warning")
        return
    if isinstance(data, dict):
        _depth_guard(path, depth + 1)
        seen: dict = {}
        for k, v in data.items():
            if not isinstance(k, str):
                rep.add(f"{path}.{k}", "key.coerced",
                        f"non-string key {k!r} coerced to a string", "warning")
            key_str = k if isinstance(k, str) else _json_key_str(k)
            if key_str in seen:
                rep.add(f"{path}.{k}", "key.collision",
                        f"key {k!r} collides with {seen[key_str]!r} after "
                        f"coercion to {key_str!r}; one overwrites the other",
                        "error")
            else:
                seen[key_str] = k
            _scan_json(v, f"{path}.{k}", rep, depth + 1)
    elif isinstance(data, list):
        _depth_guard(path, depth + 1)
        for i, v in enumerate(data):
            _scan_json(v, f"{path}[{i}]", rep, depth + 1)


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
    _yaml_core_check(data, "$", frozenset(), set(), 0)
    return data


def write_yaml(data: Any, *, sort_keys: bool = False,
               strict: bool = False, report: Optional[WriteReport] = None) -> str:
    text, rep = _serialize_yaml(data, sort_keys=sort_keys)
    return finish_write(text, rep, strict=strict, report=report)


def check_yaml(data: Any) -> WriteReport:
    """Simulate writing YAML and return the report without producing output."""
    _text, rep = _serialize_yaml(data, sort_keys=False)
    return rep


def _serialize_yaml(data: Any, *, sort_keys: bool) -> Tuple[str, WriteReport]:
    rep = WriteReport()
    prepared = _yaml_prepare(data, "$", rep, 0)
    yaml = _need("yaml", "PyYAML", "pip install pyyaml")
    text = yaml.safe_dump(prepared, sort_keys=sort_keys, allow_unicode=True,
                          default_flow_style=False)
    return text, rep


def _yaml_prepare(data: Any, path: str, rep: WriteReport, depth: int) -> Any:
    # YAML carries dates/datetimes natively; only a standalone time has no
    # representation, so it downgrades to a string.
    if isinstance(data, _dt.time):
        rep.add(path, "temporal.stringified",
                "time-of-day written as a string (YAML has no standalone time)",
                "warning")
        return data.isoformat()
    if isinstance(data, dict):
        _depth_guard(path, depth + 1)
        return {k: _yaml_prepare(v, f"{path}.{k}", rep, depth + 1)
                for k, v in data.items()}
    if isinstance(data, list):
        _depth_guard(path, depth + 1)
        return [_yaml_prepare(v, f"{path}[{i}]", rep, depth + 1)
                for i, v in enumerate(data)]
    return data


def _yaml_core_check(node: Any, path: str, ancestors: frozenset, visited: set,
                     depth: int) -> None:
    """Validate a parsed YAML tree: string keys only, no cycles, bounded depth.

    ``visited`` records nodes already fully checked via one alias reference,
    so a node reused by many aliases -- YAML's normal, memory-sharing way of
    representing repeated structure, not necessarily a cycle -- is walked
    once, not once per reference.  Without this, a small, perfectly ordinary
    YAML payload using aliases takes time exponential in the nesting depth to
    validate even though ``yaml.safe_load`` parses it instantly (PyYAML
    shares the constructed objects; this function used to re-walk them).
    ``ancestors`` is unrelated and tracks the current path, to still catch a
    genuine cycle (a node that contains itself).
    """
    if isinstance(node, (dict, list)):
        if id(node) in ancestors:
            raise ParseError(f"recursive YAML at {path} is not supported")
        if id(node) in visited:
            return
        _depth_guard(path, depth + 1)
        anc = ancestors | {id(node)}
        if isinstance(node, dict):
            for k, v in node.items():
                if not isinstance(k, str):
                    raise ParseError(f"non-string key {k!r} at {path} is not supported")
                _yaml_core_check(v, f"{path}.{k}", anc, visited, depth + 1)
        else:
            for i, v in enumerate(node):
                _yaml_core_check(v, f"{path}[{i}]", anc, visited, depth + 1)
        visited.add(id(node))


# ===========================================================================
# TOML
# ===========================================================================

def read_toml(text: str) -> Any:
    try:
        import tomllib as toml
    except ImportError:  # pragma: no cover
        toml = _need("tomli", "tomli", "pip install tomli")
    try:
        return toml.loads(text)
    except toml.TOMLDecodeError as exc:
        raise ParseError(f"invalid TOML: {exc}") from exc


def write_toml(data: Any, *, strict: bool = False,
               report: Optional[WriteReport] = None,
               null_style: str = "omit", wrap_key: str = "value") -> str:
    text, rep = _serialize_toml(data, null_style=null_style, wrap_key=wrap_key)
    return finish_write(text, rep, strict=strict, report=report)


def check_toml(data: Any, *, null_style: str = "omit",
               wrap_key: str = "value") -> WriteReport:
    """Simulate writing TOML and return the report without producing output."""
    _text, rep = _serialize_toml(data, null_style=null_style, wrap_key=wrap_key)
    return rep


_TOML_INT_MIN = -(2 ** 63)
_TOML_INT_MAX = 2 ** 63 - 1


def _serialize_toml(data: Any, *, null_style: str,
                    wrap_key: str) -> Tuple[str, WriteReport]:
    rep = WriteReport()
    body = _prepare_toml(data, "$", rep, null_style, 0)
    if body is None:
        rep.add("$", "null.toplevel.empty",
                "top-level null written as an empty document", "error")
        body = {}
    if not isinstance(body, dict):
        rep.add("$", "toplevel.wrapped",
                f"top-level {_name(body)} wrapped under {wrap_key!r} "
                "(TOML needs a top-level object)", "warning")
        body = {wrap_key: body}
    tomli_w = _need("tomli_w", "tomli_w", "pip install tomli_w")
    return tomli_w.dumps(body), rep


def _prepare_toml(data: Any, path: str, rep: WriteReport, null_style: str,
                  depth: int) -> Any:
    """One tree walk doing everything TOML needs before ``tomli_w.dumps``:
    flag out-of-range integers, stringify offset-aware times, and strip
    nulls (TOML has none of the three natively). Combined into a single
    pass -- rather than three separate ones, each re-walking and (for two of
    them) rebuilding the whole tree -- since profiling showed the three
    passes cost roughly as much as ``tomli_w``'s own serialization combined.

    Null *object fields* are omitted (warning).  Null *array items* are
    dropped; that shifts positions, so it is an error-severity adjustment
    under ``null_style="omit"`` and an ordinary warning under ``"drop"``.
    """
    if isinstance(data, bool):
        return data
    if isinstance(data, int):
        if not (_TOML_INT_MIN <= data <= _TOML_INT_MAX):
            rep.add(path, "integer.out_of_range",
                    f"{data} is outside TOML's signed 64-bit integer range "
                    "and may not round-trip in other TOML implementations",
                    "warning")
        return data
    if isinstance(data, _dt.time) and data.tzinfo is not None:
        rep.add(path, "temporal.stringified",
                "a time with a UTC offset has no native TOML representation "
                "(only date-time can carry an offset); written as text",
                "warning")
        return data.isoformat()
    if isinstance(data, dict):
        _depth_guard(path, depth + 1)
        out = {}
        for k, v in data.items():
            if v is None:
                rep.add(f"{path}.{k}", "null.field.omitted",
                        "null object field omitted", "warning")
                continue
            out[k] = _prepare_toml(v, f"{path}.{k}", rep, null_style, depth + 1)
        return out
    if isinstance(data, list):
        _depth_guard(path, depth + 1)
        out = []
        for i, v in enumerate(data):
            if v is None:
                sev = "warning" if null_style == "drop" else "error"
                rep.add(f"{path}[{i}]", "null.item.dropped",
                        "null array item dropped (shifts positions)", sev)
                continue
            out.append(_prepare_toml(v, f"{path}[{i}]", rep, null_style, depth + 1))
        return out
    return data


def _strip_nulls(data: Any, path: str, rep: WriteReport, null_style: str,
                 depth: int) -> Any:
    """Remove nulls for formats that have none (XML; TOML uses
    :func:`_prepare_toml` instead, which folds this in with its other
    TOML-only checks), recording each removal.

    Null *object fields* are omitted (warning).  Null *array items* are
    dropped; that shifts positions, so it is an error-severity adjustment
    under ``null_style="omit"`` and an ordinary warning under ``"drop"``.
    """
    if isinstance(data, dict):
        _depth_guard(path, depth + 1)
        out = {}
        for k, v in data.items():
            if v is None:
                rep.add(f"{path}.{k}", "null.field.omitted",
                        "null object field omitted", "warning")
                continue
            out[k] = _strip_nulls(v, f"{path}.{k}", rep, null_style, depth + 1)
        return out
    if isinstance(data, list):
        _depth_guard(path, depth + 1)
        out = []
        for i, v in enumerate(data):
            if v is None:
                sev = "warning" if null_style == "drop" else "error"
                rep.add(f"{path}[{i}]", "null.item.dropped",
                        "null array item dropped (shifts positions)", sev)
                continue
            out.append(_strip_nulls(v, f"{path}[{i}]", rep, null_style, depth + 1))
        return out
    return data


# ===========================================================================
# XML  (data-XML profile)
# ===========================================================================

_XML_NAME = _re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")

# The legal Char production from the XML 1.0 spec, negated: matches any
# character that cannot appear in well-formed XML at all (most C0 controls,
# surrogates, and a couple of noncharacters) -- not even as a character
# reference, so a value containing one of these can't be written as text.
_XML_ILLEGAL_CHAR = _re.compile(
    '[^\t\n\r\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]')


def read_xml(text: str) -> Any:
    """Read one XML document into a Document.  The document element's tag
    becomes the single top-level key: ``<x><y>1</y></x>`` reads as
    ``{"x": {"y": 1}}`` -- the document element is the one child of the data
    tree's (anonymous) root, connected by an edge labeled with its tag, not
    the root itself.  Scalars are untyped text, read back with best-effort
    typing."""
    ET = _xml_parser()
    try:
        root = ET.fromstring(text)
    except Exception as exc:  # pragma: no cover
        raise ParseError(f"invalid XML: {exc}") from exc
    if root.attrib:
        raise ParseError("attributes at $ are not supported (data-XML)")
    tag = _local(root.tag)
    return {tag: _xml_to_data(root, f"$.{tag}")}


def read_xml_documents(texts: list) -> Any:
    """Read a list of XML documents (a forest) into one Document: each
    document's tag becomes a top-level key, with repeated tags merging into
    a list -- the inverse of :func:`write_xml_documents`."""
    grouped: dict = {}
    order = []
    for text in texts:
        doc = read_xml(text)
        (tag, value), = doc.items()
        if tag not in grouped:
            grouped[tag] = []
            order.append(tag)
        grouped[tag].append(value)
    return {tag: (vs[0] if len(vs) == 1 else vs) for tag in order
            for vs in [grouped[tag]]}


# "Not single-rooted" has no lossless fallback shape at all (unlike, say,
# TOML wrapping a top-level array under a key) -- it's a structural
# impossibility, not a lossy adjustment -- so it always raises from
# write_xml/write_xml_documents, regardless of strict.
_ALWAYS_RAISE = "toplevel.not_rooted"


def _raise_if_not_rooted(rep: WriteReport, report: Optional[WriteReport]) -> None:
    if report is not None:
        report.extend(rep)
    if any(a.code == _ALWAYS_RAISE for a in rep):
        raise WriteError(str(rep), report=rep)


def write_xml(data: Any, *, strict: bool = False,
              report: Optional[WriteReport] = None,
              null_style: str = "omit") -> str:
    """Write a single-rooted Document as one XML document.  ``data`` must be
    a dict with exactly one key (one child of the anonymous root) whose
    value isn't itself a list -- anything else has no single XML document
    representation and raises ``WriteError`` regardless of ``strict``; use
    :func:`write_xml_documents` for a Document with multiple top-level keys
    or a top-level list."""
    text, rep = _serialize_xml(data, null_style=null_style)
    _raise_if_not_rooted(rep, report)
    return finish_write(text, rep, strict=strict, report=None)


def check_xml(data: Any, *, null_style: str = "omit") -> WriteReport:
    """Simulate writing XML and return the report without producing output."""
    _text, rep = _serialize_xml(data, null_style=null_style)
    return rep


def write_xml_documents(data: Any, *, strict: bool = False,
                        report: Optional[WriteReport] = None,
                        null_style: str = "omit") -> list:
    """Write a Document as a forest of XML documents: one per top-level key,
    with a list value producing one document per item (same tag, repeated)
    -- the inverse of :func:`read_xml_documents`.  ``data`` must be a dict;
    a top-level scalar or list has no top-level tag to use and raises
    ``WriteError``."""
    rep = WriteReport()
    if not isinstance(data, dict):
        rep.add("$", _ALWAYS_RAISE,
                f"top-level {_name(data)} has no element name to write as "
                "(XML documents must be single, named elements)", "error")
        _raise_if_not_rooted(rep, report)
    texts = []
    for k, v in data.items():
        items = v if isinstance(v, list) else [v]
        for item in items:
            text, item_rep = _serialize_xml({k: item}, null_style=null_style)
            rep.extend(item_rep)
            texts.append(text)
    _raise_if_not_rooted(rep, None)
    finish_write("", rep, strict=strict, report=report)
    return texts


def _serialize_xml(data: Any, *, null_style: str) -> Tuple[str, WriteReport]:
    rep = WriteReport()
    body = _strip_nulls(data, "$", rep, null_style, 0)
    if not isinstance(body, dict) or len(body) != 1:
        rep.add("$", _ALWAYS_RAISE,
                f"top-level {_name(body)} is not single-rooted (XML needs "
                "exactly one top-level element); use write_xml_documents() "
                "for a Document with multiple top-level keys or a top-level "
                "list", "error")
        return "", rep
    (tag, content), = body.items()
    if isinstance(content, list):
        rep.add(f"$.{tag}", _ALWAYS_RAISE,
                f"key {tag!r} holds a list, which would be multiple XML "
                "documents with the same tag; use write_xml_documents()",
                "error")
        return "", rep
    import xml.etree.ElementTree as ET
    root_tag = _xml_name(str(tag), "$", rep)
    el = ET.Element(root_tag)
    if isinstance(content, dict) and not content:
        rep.add(f"$.{tag}", "container.empty.ambiguous",
                "empty object written as an empty element; reads back as "
                "an empty string, not an empty object", "warning")
    _data_to_xml(content, el, f"$.{tag}", rep, 0)
    _indent(el)
    return ET.tostring(el, encoding="unicode"), rep


def _xml_to_data(elem, path: str, depth: int = 0) -> Any:
    if elem.attrib:
        raise ParseError(f"attributes at {path} are not supported (data-XML)")
    children = list(elem)
    if children:
        _depth_guard(path, depth + 1)
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
            grouped[tag].append(_xml_to_data(child, f"{path}.{tag}", depth + 1))
        return {tag: (vs[0] if len(vs) == 1 else vs) for tag in order
                for vs in [grouped[tag]]}
    return _coerce(elem.text or "")


def _data_to_xml(data: Any, parent, path: str, rep: WriteReport, depth: int) -> None:
    import xml.etree.ElementTree as ET
    if isinstance(data, dict):
        _depth_guard(path, depth + 1)
        seen_tags: dict = {}
        for k, v in data.items():
            tag = _xml_name(str(k), f"{path}.{k}", rep)
            if tag in seen_tags and seen_tags[tag] != k:
                rep.add(f"{path}.{k}", "key.collision",
                        f"key {k!r} writes the same XML element name {tag!r} as "
                        f"key {seen_tags[tag]!r}; they will merge into one list "
                        "on read", "error")
            else:
                seen_tags[tag] = k
            if isinstance(v, list):
                if not v:
                    rep.add(f"{path}.{k}", "container.empty.ambiguous",
                            "empty array written as an empty element; reads "
                            "back as an empty string, not an empty array",
                            "warning")
                    ET.SubElement(parent, tag)
                    continue
                for i, item in enumerate(v):
                    child = ET.SubElement(parent, tag)
                    _xml_child(item, child, f"{path}.{k}[{i}]", rep, depth + 1)
            else:
                if isinstance(v, dict) and not v:
                    rep.add(f"{path}.{k}", "container.empty.ambiguous",
                            "empty object written as an empty element; reads "
                            "back as an empty string, not an empty object",
                            "warning")
                child = ET.SubElement(parent, tag)
                _data_to_xml(v, child, f"{path}.{k}", rep, depth + 1)
    elif isinstance(data, list):
        _depth_guard(path, depth + 1)
        # A list reaching a scalar position (e.g. nested array): wrap each item
        # in a synthetic <item> element.  Not unambiguously reversible.
        # Report is added by _xml_child, not here, to avoid double-counting.
        for i, item in enumerate(data):
            child = ET.SubElement(parent, "item")
            _xml_child(item, child, f"{path}[{i}]", rep, depth + 1)
    else:
        parent.text = _xml_text(data, path, rep)


def _xml_child(item: Any, child, path: str, rep: WriteReport, depth: int) -> None:
    if isinstance(item, list):
        rep.add(path, "array.nested.ambiguous",
                "nested array wrapped in <item> elements", "error")
        _data_to_xml({"item": item}, child, path, rep, depth)
    else:
        _data_to_xml(item, child, path, rep, depth)


def _xml_name(k: str, path: str, rep: WriteReport) -> str:
    if _XML_NAME.match(k):
        return k
    safe = _re.sub(r"[^A-Za-z0-9_.\-]", "_", k)
    if not safe or not _XML_NAME.match(safe):
        safe = "_" + safe
    rep.add(path, "key.sanitized",
            f"key {k!r} is not a valid XML name; written as {safe!r}", "warning")
    return safe


def _xml_text(v: Any, path: str, rep: WriteReport) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (_dt.date, _dt.time)):
        rep.add(path, "temporal.stringified",
                "temporal value written as text (reads back as a string)",
                "warning")
        return v.isoformat()
    if not isinstance(v, str):
        return str(v)
    text = v
    if _XML_ILLEGAL_CHAR.search(text):
        # These code points (most C0 controls, surrogates, a few others) have
        # no representation in XML 1.0 at all -- not even a character
        # reference -- so the previous behavior (write them anyway) produced
        # output that doesn't just round-trip differently, it doesn't parse
        # as XML at all. Stripping is lossy, but the alternative is silently
        # writing unreadable output.
        rep.add(path, "string.illegal_xml_char",
                f"string {v!r} contains a character with no legal XML "
                "representation; it was removed", "error")
        text = _XML_ILLEGAL_CHAR.sub("", text)
    if _coerce(text) != text:
        rep.add(path, "string.ambiguous",
                f"string {text!r} looks like a different type and will not "
                "read back as a string", "warning")
    elif "\r" in text:
        rep.add(path, "string.line_ending_normalized",
                "the XML spec requires \\r\\n and \\r to be normalized to "
                "\\n on read, so this string will not read back unchanged",
                "warning")
    return text


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
    except ImportError:
        import warnings
        warnings.warn(
            "defusedxml is not installed; read_xml() will use the standard "
            "library's XML parser, which is vulnerable to entity-expansion "
            "and external-entity (XXE) attacks on untrusted input. "
            "pip install defusedxml (or the 'xml'/'all' extra) to fix this.",
            UnsafeXMLWarning, stacklevel=3)
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


# ===========================================================================
# Registry — register the four built-in formats as plugins
# ===========================================================================

from .registry import (  # noqa: E402,F401  (kept at the bottom to avoid import cycles; get_format/formats re-exported)
    Format,
    formats,
    get_format,
    register_format,
)

register_format(Format("json", read_json, write_json, check_json, (".json",)))
register_format(Format("yaml", read_yaml, write_yaml, check_yaml,
                       (".yaml", ".yml"), ("pyyaml",)))
register_format(Format("toml", read_toml, write_toml, check_toml,
                       (".toml",), ("tomli_w",)))
register_format(Format("xml", read_xml, write_xml, check_xml,
                       (".xml",), ("defusedxml",)))
