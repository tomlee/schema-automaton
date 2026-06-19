"""The schema DSL — a compact text language for writing schemas.

    type Line = { sku: string, qty: integer, price: number }
    root {
        id:     string,
        status: "open" | "shipped" | "cancelled",
        lines:  [Line]+,
        note?:  string,
        when:   datetime,
    }

Forms:
  scalars : string integer number boolean date time datetime null
  object  : { field: T, optional?: T, ... }      ("..." = open object)
  array   : [T]   [T]+   [T]{m,n}   [T]{n}   [T]{m,}   [T]{,n}
  nullable: T?            (T or null)
  union   : integer | string         enum: "a" | "b"
  named   : type Name = T            recursion allowed; reference by name
  root    : root T
  comments: # to end of line
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .errors import SchemaError
from .schema import (
    Schema, Type, ScalarType, ArrayType, ObjectType, Field, RefType,
    STRING, INTEGER, NUMBER, BOOLEAN, DATE, TIME, DATETIME, SCALAR_KINDS,
)

_KEYWORD_KIND = {
    "string": STRING, "integer": INTEGER, "number": NUMBER, "boolean": BOOLEAN,
    "date": DATE, "time": TIME, "datetime": DATETIME,
}
_PUNCT = set("{}[]():,|?+*=")


# ===========================================================================
# Tokenizer
# ===========================================================================

class _Tok:
    __slots__ = ("kind", "text", "pos")

    def __init__(self, kind, text, pos):
        self.kind, self.text, self.pos = kind, text, pos


def _tokenize(s: str) -> List[_Tok]:
    toks, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
        elif c == "#":
            while i < n and s[i] != "\n":
                i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and s[j] != '"':
                if s[j] == "\\" and j + 1 < n:
                    buf.append(s[j + 1]); j += 2
                else:
                    buf.append(s[j]); j += 1
            if j >= n:
                raise SchemaError(f"unterminated string at {i}")
            toks.append(_Tok("STR", "".join(buf), i)); i = j + 1
        elif c == "." and s[i:i + 3] == "...":
            toks.append(_Tok("...", "...", i)); i += 3
        elif c in _PUNCT:
            toks.append(_Tok("P", c, i)); i += 1
        elif c.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            toks.append(_Tok("INT", s[i:j], i)); i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            toks.append(_Tok("ID", s[i:j], i)); i = j
        else:
            raise SchemaError(f"unexpected character {c!r} at {i}")
    toks.append(_Tok("EOF", "", n))
    return toks


# ===========================================================================
# Tiny AST (built then lowered to Types)
# ===========================================================================

class _N: pass
class _Scalar(_N):
    def __init__(self, kind): self.kind = kind
class _Null(_N): pass
class _Lit(_N):
    def __init__(self, value): self.value = value
class _Obj(_N):
    def __init__(self, fields, open): self.fields = fields; self.open = open
class _Arr(_N):
    def __init__(self, item, lo, hi): self.item = item; self.lo = lo; self.hi = hi
class _Ref(_N):
    def __init__(self, name): self.name = name
class _Union(_N):
    def __init__(self, alts): self.alts = alts
class _Opt(_N):
    def __init__(self, inner): self.inner = inner


class _Parser:
    def __init__(self, toks): self.t = toks; self.i = 0

    def _peek(self): return self.t[self.i]
    def _next(self): tok = self.t[self.i]; self.i += 1; return tok
    def _is(self, ch): t = self._peek(); return t.kind == "P" and t.text == ch
    def _expect(self, ch):
        t = self._next()
        if not (t.kind == "P" and t.text == ch):
            raise SchemaError(f"expected {ch!r} but got {t.text!r} at {t.pos}")

    def parse(self) -> Tuple[Dict[str, _N], _N]:
        typedefs, root = {}, None
        while self._peek().kind != "EOF":
            t = self._peek()
            if t.kind == "ID" and t.text == "type":
                self._next()
                name = self._next()
                if name.kind != "ID":
                    raise SchemaError(f"expected type name at {name.pos}")
                self._expect("=")
                if name.text in typedefs:
                    raise SchemaError(f"duplicate type {name.text!r}")
                typedefs[name.text] = self._type()
            elif t.kind == "ID" and t.text == "root":
                self._next()
                if root is not None:
                    raise SchemaError("multiple 'root' declarations")
                root = self._type()
            else:
                raise SchemaError(f"expected 'type' or 'root', got {t.text!r} at {t.pos}")
        if root is None:
            raise SchemaError("schema has no 'root'")
        return typedefs, root

    def _type(self): return self._union()

    def _union(self):
        alts = [self._postfix()]
        while self._is("|"):
            self._next(); alts.append(self._postfix())
        return alts[0] if len(alts) == 1 else _Union(alts)

    def _postfix(self):
        node = self._atom()
        while self._is("?"):
            self._next(); node = _Opt(node)
        return node

    def _atom(self):
        t = self._peek()
        if t.kind == "STR":
            self._next(); return _Lit(t.text)
        if self._is("("):
            self._next(); node = self._type(); self._expect(")"); return node
        if self._is("{"):
            return self._object()
        if self._is("["):
            return self._array()
        if t.kind == "ID":
            self._next()
            if t.text in _KEYWORD_KIND:
                return _Scalar(_KEYWORD_KIND[t.text])
            if t.text == "null":
                return _Null()
            return _Ref(t.text)
        raise SchemaError(f"unexpected token {t.text!r} at {t.pos}")

    def _object(self):
        self._expect("{")
        fields, is_open = [], False
        while not self._is("}"):
            if self._peek().kind == "...":
                self._next(); is_open = True
                if self._is(","):
                    self._next()
                break
            name = self._next()
            if name.kind not in ("ID", "STR"):
                raise SchemaError(f"expected field name at {name.pos}")
            optional = False
            if self._is("?"):
                self._next(); optional = True
            self._expect(":")
            fields.append((name.text, optional, self._type()))
            if self._is(","):
                self._next()
            else:
                break
        self._expect("}")
        return _Obj(fields, is_open)

    def _array(self):
        self._expect("[")
        item = self._type()
        self._expect("]")
        lo, hi = 0, None
        if self._is("+"):
            self._next(); lo = 1
        elif self._is("*"):
            self._next()
        elif self._is("{"):
            self._next()
            lo, hi = self._arity_body()
            self._expect("}")
        return _Arr(item, lo, hi)

    def _arity_body(self):
        # forms: {n} | {m,} | {,n} | {m,n}
        first = None
        if self._peek().kind == "INT":
            first = int(self._next().text)
        if self._is(","):
            self._next()
            second = None
            if self._peek().kind == "INT":
                second = int(self._next().text)
            return (first or 0), second
        # {n}
        if first is None:
            raise SchemaError("empty arity {}")
        return first, first


# ===========================================================================
# Lower AST -> Schema
# ===========================================================================

def _flatten(node: _N):
    alts, nullable = [], False
    def rec(n):
        nonlocal nullable
        if isinstance(n, _Union):
            for a in n.alts: rec(a)
        elif isinstance(n, _Opt):
            nullable = True; rec(n.inner)
        elif isinstance(n, _Null):
            nullable = True
        else:
            alts.append(n)
    rec(node)
    return alts, nullable


def _build(node: _N) -> Type:
    alts, nullable = _flatten(node)
    if not alts:  # only null
        return ScalarType(set(), nullable=True)
    if all(isinstance(a, (_Scalar, _Lit)) for a in alts):
        return _build_scalar(alts, nullable)
    if len(alts) != 1:
        raise SchemaError("union of structural types is not supported "
                          "(only 'T | null' / 'T?' is allowed)")
    a = alts[0]
    if isinstance(a, _Ref):
        return RefType(a.name, nullable)
    if isinstance(a, _Obj):
        fields = {name: Field(_build(ty), not opt) for name, opt, ty in a.fields}
        return ObjectType(fields, a.open, nullable)
    if isinstance(a, _Arr):
        return ArrayType(_build(a.item), a.lo, a.hi, nullable)
    raise SchemaError(f"cannot build type from {a!r}")


def _build_scalar(alts, nullable) -> ScalarType:
    kinds, enum, has_kind = set(), set(), False
    for a in alts:
        if isinstance(a, _Scalar):
            kinds.add(a.kind); has_kind = True
        else:
            enum.add(a.value)
    if enum and not has_kind:
        return ScalarType({STRING}, nullable, enum)
    if enum:
        kinds.add(STRING)
    if NUMBER in kinds:
        kinds.discard(INTEGER)
    return ScalarType(kinds, nullable)


def parse_schema(text: str) -> Schema:
    """Parse DSL text into a :class:`Schema`."""
    typedefs, root = _Parser(_tokenize(text)).parse()
    types = {name: _build(node) for name, node in typedefs.items()}
    return Schema(_build(root), types)


# ===========================================================================
# Schema -> DSL text
# ===========================================================================

def to_dsl(schema: Schema) -> str:
    lines = []
    for name, t in schema.types.items():
        lines.append(f"type {name} = {_emit(t)}")
    lines.append(f"root {_emit(schema.root)}")
    return "\n".join(lines) + "\n"


def _emit(t: Type) -> str:
    s = _emit_bare(t)
    if t.nullable:
        return f"({s})?" if (isinstance(t, ScalarType) and len(t.kinds) > 1) else f"{s}?"
    return s


def _emit_bare(t: Type) -> str:
    if isinstance(t, RefType):
        return t.name
    if isinstance(t, ScalarType):
        if t.enum is not None:
            return " | ".join('"' + v.replace('"', '\\"') + '"' for v in sorted(t.enum))
        if not t.kinds:
            return "null"
        return " | ".join(sorted(t.kinds))
    if isinstance(t, ArrayType):
        inner = _emit(t.item)
        if t.min == 0 and t.max is None:
            return f"[{inner}]"
        if t.min == 1 and t.max is None:
            return f"[{inner}]+"
        if t.max is not None and t.min == t.max:
            return f"[{inner}]{{{t.min}}}"
        hi = "" if t.max is None else t.max
        return f"[{inner}]{{{t.min},{hi}}}"
    if isinstance(t, ObjectType):
        parts = []
        for k, f in t.fields.items():
            key = k if k.isidentifier() else '"' + k + '"'
            parts.append(f"{key}{'' if f.required else '?'}: {_emit(f.type)}")
        if t.open:
            parts.append("...")
        return "{ " + ", ".join(parts) + " }" if parts else "{}"
    return "?"
