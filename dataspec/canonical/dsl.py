"""The schema text language for the canonical model.

Grammar (informal)::

    schema      := definition* 'root' NAME
    definition  := 'record' NAME '{' field (',' field)* ','? '}'
                 | 'union'  NAME '{' member (',' member)* ','? '}'
    field       := STRING cardinality? ':' type
    cardinality := '[' INT? (',' INT?)? ']'          -- [m,n] [m,] [,n] [n]; absent = [1,1]
    type        := atom ('|' atom)* '?'?             -- a value-domain union, or one Ref
    atom        := kind | STRING | NUMBER | 'null' | 'true' | 'false' | NAME
    member      := kind | STRING | NUMBER | 'null' | 'true' | 'false'

Quoting rule: a ``"quoted"`` token is a data string (a field label or a string
literal); an unquoted identifier is a schema name (a kind keyword, or a ``Ref``);
``null`` / ``true`` / ``false`` / a number are bare non-string literals.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from ..errors import SchemaError
from .schema import (
    Field,
    Record,
    Ref,
    Schema,
    Union,
    kind_by_name,
)

_KINDS = {"string", "integer", "number", "boolean", "date", "time", "datetime"}
_MAX_DEPTH = 100

_TOKEN = re.compile(r"""
      (?P<ws>\s+)
    | (?P<comment>\#[^\n]*)
    | (?P<string>"(?:\\.|[^"\\])*")
    | (?P<number>-?\d+\.\d+|-?\d+)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<punct>[{}\[\]:,|?])
""", re.VERBOSE)


class _Tok:
    __slots__ = ("kind", "text", "pos")

    def __init__(self, kind: str, text: str, pos: int) -> None:
        self.kind, self.text, self.pos = kind, text, pos


def _tokenize(text: str) -> List[_Tok]:
    toks, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if not m:
            raise SchemaError(f"unexpected character {text[i]!r} at {i}")
        i = m.end()
        kind = m.lastgroup
        if kind in ("ws", "comment"):
            continue
        toks.append(_Tok(kind, m.group(), m.start()))
    toks.append(_Tok("eof", "", len(text)))
    return toks


def _unquote(s: str) -> str:
    return re.sub(r'\\(.)', r'\1', s[1:-1])


class _Parser:
    def __init__(self, toks: List[_Tok]) -> None:
        self.toks = toks
        self.i = 0

    def _peek(self) -> _Tok:
        return self.toks[self.i]

    def _next(self) -> _Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def _expect(self, kind: str, text: Optional[str] = None) -> _Tok:
        t = self._next()
        if t.kind != kind or (text is not None and t.text != text):
            want = text or kind
            raise SchemaError(f"expected {want!r} at {t.pos}, got {t.text!r}")
        return t

    def parse(self) -> Schema:
        env: dict = {}
        root: Optional[str] = None
        while self._peek().kind != "eof":
            t = self._peek()
            if t.kind == "name" and t.text == "record":
                name, rec = self._record()
                self._define(env, name, rec)
            elif t.kind == "name" and t.text == "union":
                name, u = self._union_def()
                self._define(env, name, u)
            elif t.kind == "name" and t.text == "root":
                self._next()
                root = self._expect("name").text
            else:
                raise SchemaError(f"expected 'record', 'union', or 'root' at {t.pos}, "
                                  f"got {t.text!r}")
        if root is None:
            raise SchemaError("a schema must declare a root")
        return Schema(Ref(root), env)

    def _define(self, env: dict, name: str, d: Any) -> None:
        if name in env:
            raise SchemaError(f"duplicate definition {name!r}")
        env[name] = d

    def _record(self) -> Tuple[str, Record]:
        self._expect("name", "record")
        name = self._expect("name").text
        self._expect("punct", "{")
        fields: List[Field] = []
        while self._peek().text != "}":
            fields.append(self._field())
            if self._peek().text == ",":
                self._next()
            else:
                break
        self._expect("punct", "}")
        return name, Record(fields)

    def _field(self) -> Field:
        label_tok = self._next()
        if label_tok.kind != "string":
            raise SchemaError(f"expected a quoted field name at {label_tok.pos}, "
                              f"got {label_tok.text!r}")
        label = _unquote(label_tok.text)
        lo, hi = 1, 1
        if self._peek().text == "[":
            lo, hi = self._cardinality()
        self._expect("punct", ":")
        typ = self._type()
        return Field(label, typ, lo, hi)

    def _cardinality(self) -> Tuple[int, Optional[int]]:
        self._expect("punct", "[")
        first = None
        if self._peek().kind == "number":
            first = int(self._next().text)
        if self._peek().text == ",":
            self._next()
            second: Optional[int] = None
            if self._peek().kind == "number":
                second = int(self._next().text)
            lo = first if first is not None else 0
            hi = second
        else:
            if first is None:
                raise SchemaError(f"empty cardinality at {self._peek().pos}")
            lo = hi = first
        self._expect("punct", "]")
        return lo, hi

    def _type(self) -> Any:
        atoms: List[_Tok] = [self._type_atom()]
        while self._peek().text == "|":
            self._next()
            atoms.append(self._type_atom())
        nullable = False
        if self._peek().text == "?":
            self._next()
            nullable = True
        return self._build_type(atoms, nullable)

    def _type_atom(self) -> _Tok:
        t = self._next()
        if t.kind in ("string", "number", "name"):
            return t
        raise SchemaError(f"expected a type atom at {t.pos}, got {t.text!r}")

    def _build_type(self, atoms: List[_Tok], nullable: bool) -> Any:
        # a single unquoted non-kind identifier is a Ref (to a record or union)
        if (len(atoms) == 1 and atoms[0].kind == "name"
                and atoms[0].text not in _KINDS
                and atoms[0].text not in ("null", "true", "false")):
            if nullable:
                raise SchemaError(
                    f"'?' cannot apply to the reference {atoms[0].text!r}; "
                    "use cardinality [0,1] for an optional field")
            return Ref(atoms[0].text)
        kinds, literals, null = [], [], nullable
        for a in atoms:
            if a.kind == "string":
                literals.append(_unquote(a.text))
            elif a.kind == "number":
                literals.append(float(a.text) if "." in a.text else int(a.text))
            elif a.text == "null":
                null = True
            elif a.text in ("true", "false"):
                literals.append(a.text == "true")
            elif a.text in _KINDS:
                kinds.append(kind_by_name(a.text))
            else:
                raise SchemaError(
                    f"{a.text!r} cannot appear in a value union (a union holds "
                    "kinds, literals, and null — never a record)")
        return Union(kinds=kinds, literals=literals, null=null)

    def _union_def(self) -> Tuple[str, Union]:
        self._expect("name", "union")
        name = self._expect("name").text
        self._expect("punct", "{")
        members: List[_Tok] = []
        while self._peek().text != "}":
            members.append(self._type_atom())
            if self._peek().text == ",":
                self._next()
            else:
                break
        self._expect("punct", "}")
        u = self._build_type(members, False)
        if not isinstance(u, Union):
            raise SchemaError(f"union {name!r} must hold values, not a reference")
        return name, u


def parse_schema(text: str) -> Schema:
    """Parse DSL text into a :class:`~dataspec.canonical.schema.Schema`."""
    if text.count("{") > _MAX_DEPTH:
        raise SchemaError("schema nesting exceeds the maximum depth")
    return _Parser(_tokenize(text)).parse()


# ---------------------------------------------------------------------------
# Serialize a Schema back to DSL text
# ---------------------------------------------------------------------------

def to_dsl(schema: Schema) -> str:
    lines: List[str] = []
    for name, d in schema.env.items():
        if isinstance(d, Union):
            lines.append(f"union {name} {{ {_union_def_body(d)} }}")
        else:
            lines.append(_record(name, d))
    lines.append(f"root {schema.root.name}")
    return "\n".join(lines) + "\n"


def _record(name: str, rec: Record) -> str:
    out = [f"record {name} {{"]
    for f in rec.fields:
        out.append(f"    {_field(f)},")
    out.append("}")
    return "\n".join(out)


def _field(f: Field) -> str:
    card = "" if (f.min, f.max) == (1, 1) else f" {_card(f.min, f.max)}"
    return f'"{f.label}"{card}: {_type(f.type)}'


def _card(lo: int, hi: Optional[int]) -> str:
    if lo == hi:
        return f"[{lo}]"
    return f"[{lo},{'' if hi is None else hi}]"


def _type(t: Any) -> str:
    if isinstance(t, Ref):
        return t.name
    return _union_inline(t)


def _union_inline(u: Union) -> str:
    return " | ".join(_union_parts(u))


def _union_def_body(u: Union) -> str:
    return ", ".join(_union_parts(u))


def _union_parts(u: Union) -> List[str]:
    parts = [k.name for k in sorted(u.kinds, key=lambda k: k.name)]
    parts += [_literal(v) for v in sorted(u.literals, key=repr)]
    if u.null:
        parts.append("null")
    return parts


def _literal(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v.replace('"', '\\"') + '"'
    return str(v)
