"""Schema DSL — a textual language for defining Schema Automata.

A compact, readable way to author the canonical schema model by hand and parse
it into a :class:`SchemaAutomaton`.  The reverse direction (``schema_to_dsl``)
renders a Schema Automaton back to DSL text, so inferred schemas can be printed
and round-tripped.

Grammar (EBNF)::

    program   = statement* ;
    statement = "type" IDENT "=" type        (* named, reusable / recursive type *)
              | "root" type ;                 (* the document's top-level type    *)
    type      = union ;
    union     = postfix ( "|" postfix )* ;    (* alternatives                     *)
    postfix   = atom "?"* ;                    (* "?" = nullable (… | null)        *)
    atom      = "string" | "int" | "number" | "bool" | "null"
              | STRING                         (* enum member, e.g. "active"       *)
              | "{" fields? "}"                (* object (unordered map)           *)
              | "[" type? "]" "+"?             (* array; "+" = non-empty; [] empty *)
              | "(" type ")"                   (* grouping                         *)
              | IDENT ;                        (* reference to a named type        *)
    fields    = ( field ( "," field )* ( "," "..." )? | "..." ) ","? ;
    field     = IDENT "?"? ":" type ;          (* "?" after the name = optional    *)

Notes:

* ``string`` / ``int`` / ``number`` / ``bool`` map to the scalar value domains
  STRS / INTS / DECS / BOOL.  ``null`` is the null value.
* ``int | string`` is a scalar **union**; ``"a" | "b"`` is an **enumeration**.
* ``T?`` makes ``T`` nullable: ``string?``, ``{...}?`` (nullable object),
  ``[int]?`` (nullable array).
* ``{ name: string, age?: int }`` — ``age`` is optional. A trailing ``...``
  makes the object **open** (additional keys allowed): ``{ id: int, ... }``.
* ``[T]`` is zero-or-more; ``[T]+`` is one-or-more; ``[]`` is the empty array.
* Named types enable reuse and **recursion**:
  ``type Tree = { value: int, kids: [Tree] }``.
* Comments start with ``#`` and run to end of line.

Example::

    # an order document
    type Money = number
    type Line  = { sku: string, qty: int, price: Money }
    root {
        id: string,
        status: "open" | "shipped" | "cancelled",
        lines: [Line]+,
        note: string?,
    }
"""

from __future__ import annotations
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .schema_automaton import SchemaAutomaton
from .content_model import MapModel, ScalarModel, KIND_MAP, KIND_SEQUENCE
from .hlang import HLang
from .vdom import VDom
from .formats import ITEM, _seq_model


# ===========================================================================
# Tokenizer
# ===========================================================================

_PUNCT = {"{", "}", "[", "]", "(", ")", ":", ",", "|", "?", "+", "="}
_SCALARS = {"string": VDom.STRS, "int": VDom.INTS, "number": VDom.DECS, "bool": VDom.BOOL}


class _Token:
    __slots__ = ("kind", "text", "pos")

    def __init__(self, kind: str, text: str, pos: int) -> None:
        self.kind = kind    # IDENT | STRING | PUNCT | ELLIPSIS | EOF
        self.text = text
        self.pos = pos

    def __repr__(self) -> str:
        return f"{self.kind}({self.text!r})"


class SchemaSyntaxError(ValueError):
    """Raised when DSL text cannot be parsed."""


def _tokenize(text: str) -> List[_Token]:
    tokens: List[_Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            if j >= n:
                raise SchemaSyntaxError(f"Unterminated string literal at {i}")
            tokens.append(_Token("STRING", "".join(buf), i))
            i = j + 1
        elif c == "." and text[i:i + 3] == "...":
            tokens.append(_Token("ELLIPSIS", "...", i))
            i += 3
        elif c in _PUNCT:
            tokens.append(_Token("PUNCT", c, i))
            i += 1
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(_Token("IDENT", text[i:j], i))
            i = j
        else:
            raise SchemaSyntaxError(f"Unexpected character {c!r} at position {i}")
    tokens.append(_Token("EOF", "", n))
    return tokens


# ===========================================================================
# AST
# ===========================================================================

class _Node:
    pass


class _Scalar(_Node):
    def __init__(self, kind: str) -> None:
        self.kind = kind            # VDom.STRS / INTS / DECS / BOOL


class _Null(_Node):
    pass


class _Literal(_Node):
    def __init__(self, value: str) -> None:
        self.value = value


class _Object(_Node):
    def __init__(self, fields: List[Tuple[str, bool, _Node]], open: bool) -> None:
        self.fields = fields        # (name, optional, type)
        self.open = open


class _Array(_Node):
    def __init__(self, item: Optional[_Node], nonempty: bool) -> None:
        self.item = item            # None => empty-array-only
        self.nonempty = nonempty


class _Ref(_Node):
    def __init__(self, name: str) -> None:
        self.name = name


class _Union(_Node):
    def __init__(self, alts: List[_Node]) -> None:
        self.alts = alts


class _Optional(_Node):
    def __init__(self, inner: _Node) -> None:
        self.inner = inner


# ===========================================================================
# Parser (recursive descent)
# ===========================================================================

class _Parser:
    def __init__(self, tokens: List[_Token]) -> None:
        self._tok = tokens
        self._i = 0

    def _peek(self) -> _Token:
        return self._tok[self._i]

    def _next(self) -> _Token:
        t = self._tok[self._i]
        self._i += 1
        return t

    def _expect_punct(self, ch: str) -> None:
        t = self._next()
        if not (t.kind == "PUNCT" and t.text == ch):
            raise SchemaSyntaxError(f"Expected {ch!r} but got {t.text!r} at {t.pos}")

    def _is_punct(self, ch: str) -> bool:
        t = self._peek()
        return t.kind == "PUNCT" and t.text == ch

    # -- top level -----------------------------------------------------
    def parse_program(self) -> Tuple[Dict[str, _Node], _Node]:
        typedefs: Dict[str, _Node] = {}
        root: Optional[_Node] = None
        while self._peek().kind != "EOF":
            t = self._peek()
            if t.kind == "IDENT" and t.text == "type":
                self._next()
                name_tok = self._next()
                if name_tok.kind != "IDENT":
                    raise SchemaSyntaxError(f"Expected type name at {name_tok.pos}")
                self._expect_punct("=")
                if name_tok.text in typedefs:
                    raise SchemaSyntaxError(f"Duplicate type {name_tok.text!r}")
                typedefs[name_tok.text] = self._type()
            elif t.kind == "IDENT" and t.text == "root":
                self._next()
                if root is not None:
                    raise SchemaSyntaxError("Multiple 'root' declarations")
                root = self._type()
            else:
                raise SchemaSyntaxError(
                    f"Expected 'type' or 'root' but got {t.text!r} at {t.pos}")
        if root is None:
            raise SchemaSyntaxError("Schema has no 'root' declaration")
        return typedefs, root

    # -- types ---------------------------------------------------------
    def _type(self) -> _Node:
        return self._union()

    def _union(self) -> _Node:
        alts = [self._postfix()]
        while self._is_punct("|"):
            self._next()
            alts.append(self._postfix())
        return alts[0] if len(alts) == 1 else _Union(alts)

    def _postfix(self) -> _Node:
        node = self._atom()
        while self._is_punct("?"):
            self._next()
            node = _Optional(node)
        return node

    def _atom(self) -> _Node:
        t = self._peek()
        if t.kind == "STRING":
            self._next()
            return _Literal(t.text)
        if self._is_punct("("):
            self._next()
            node = self._type()
            self._expect_punct(")")
            return node
        if self._is_punct("{"):
            return self._object()
        if self._is_punct("["):
            return self._array()
        if t.kind == "IDENT":
            self._next()
            if t.text in _SCALARS:
                return _Scalar(_SCALARS[t.text])
            if t.text == "null":
                return _Null()
            return _Ref(t.text)
        raise SchemaSyntaxError(f"Unexpected token {t.text!r} at {t.pos}")

    def _object(self) -> _Object:
        self._expect_punct("{")
        fields: List[Tuple[str, bool, _Node]] = []
        is_open = False
        while not self._is_punct("}"):
            if self._peek().kind == "ELLIPSIS":
                self._next()
                is_open = True
                if self._is_punct(","):
                    self._next()
                break
            name_tok = self._next()
            if name_tok.kind != "IDENT" and name_tok.kind != "STRING":
                raise SchemaSyntaxError(f"Expected field name at {name_tok.pos}")
            optional = False
            if self._is_punct("?"):
                self._next()
                optional = True
            self._expect_punct(":")
            ftype = self._type()
            fields.append((name_tok.text, optional, ftype))
            if self._is_punct(","):
                self._next()
            else:
                break
        self._expect_punct("}")
        return _Object(fields, is_open)

    def _array(self) -> _Array:
        self._expect_punct("[")
        if self._is_punct("]"):
            self._next()
            return _Array(None, False)
        item = self._type()
        self._expect_punct("]")
        nonempty = False
        if self._is_punct("+"):
            self._next()
            nonempty = True
        return _Array(item, nonempty)


# ===========================================================================
# Builder:  AST  ->  SchemaAutomaton
# ===========================================================================

def _flatten(node: _Node) -> Tuple[List[_Node], bool]:
    """Flatten unions/optionals into (non-null alternatives, nullable?)."""
    alts: List[_Node] = []
    nullable = False

    def rec(n: _Node) -> None:
        nonlocal nullable
        if isinstance(n, _Union):
            for a in n.alts:
                rec(a)
        elif isinstance(n, _Optional):
            nullable = True
            rec(n.inner)
        elif isinstance(n, _Null):
            nullable = True
        else:
            alts.append(n)

    rec(node)
    return alts, nullable


class _Builder:
    def __init__(self, typedefs: Dict[str, _Node]) -> None:
        self.typedefs = typedefs
        self._counter = 0
        self.name_ids: Dict[str, int] = {}
        self.sa: Optional[SchemaAutomaton] = None

    def _new_id(self) -> int:
        i = self._counter
        self._counter += 1
        return i

    def build(self, root: _Node) -> SchemaAutomaton:
        # Pre-allocate a state id for every named type (forward refs + recursion).
        for name in self.typedefs:
            self.name_ids[name] = self._new_id()

        if isinstance(root, _Ref):
            self._require_name(root.name)
            root_id = self.name_ids[root.name]
        else:
            root_id = self._new_id()

        self.sa = SchemaAutomaton(root_id)
        for name, ast in self.typedefs.items():
            self._emit(ast, self.name_ids[name])
        if not isinstance(root, _Ref):
            self._emit(root, root_id)
        return self.sa

    def _require_name(self, name: str) -> None:
        if name not in self.name_ids:
            raise SchemaSyntaxError(f"Reference to undefined type {name!r}")

    def _resolve(self, node: _Node) -> int:
        """Return the state id for a type used as a child/item position."""
        # a *pure* reference shares the named state; anything else gets a state
        if isinstance(node, _Ref):
            self._require_name(node.name)
            return self.name_ids[node.name]
        sid = self._new_id()
        self._emit(node, sid)
        return sid

    def _emit(self, node: _Node, target: int) -> None:
        alts, nullable = _flatten(node)
        assert self.sa is not None

        if not alts:                       # only null
            self.sa.add_state(target, ScalarModel(), VDom.null())
            return

        # all scalar-ish?  -> a (possibly union/enum/nullable) scalar value domain
        if all(isinstance(a, (_Scalar, _Literal)) for a in alts):
            self.sa.add_state(target, ScalarModel(), _combine_scalars(alts, nullable))
            return

        if len(alts) != 1:
            raise SchemaSyntaxError(
                "Cannot represent a union of structural types "
                "(only 'T | null' nullable structures are supported)")

        atom = alts[0]
        if isinstance(atom, _Ref):
            # nullable reference: duplicate the named type's structure here, made
            # nullable (so the shared named state itself stays non-nullable)
            self._require_name(atom.name)
            self._emit(self.typedefs[atom.name], target)
            if nullable:
                self.sa.set_struct_nullable(target, True)
        elif isinstance(atom, _Object):
            self._emit_object(atom, target, nullable)
        elif isinstance(atom, _Array):
            self._emit_array(atom, target, nullable)
        else:
            raise SchemaSyntaxError(f"Unsupported type node {atom!r}")

    def _emit_object(self, node: _Object, target: int, nullable: bool) -> None:
        assert self.sa is not None
        fields = {name: (not optional) for name, optional, _ in node.fields}
        self.sa.add_state(target, MapModel(fields, open=node.open), VDom.null())
        if nullable:
            self.sa.set_struct_nullable(target, True)
        for name, _optional, ftype in node.fields:
            self.sa.add_transition(target, name, self._resolve(ftype))

    def _emit_array(self, node: _Array, target: int, nullable: bool) -> None:
        assert self.sa is not None
        if node.item is None:
            self.sa.add_state(target, HLang.epsilon_lang(), VDom.null())
            if nullable:
                self.sa.set_struct_nullable(target, True)
            return
        self.sa.add_state(target, _seq_model(ITEM, plus=node.nonempty), VDom.null())
        if nullable:
            self.sa.set_struct_nullable(target, True)
        self.sa.add_transition(target, ITEM, self._resolve(node.item))


def _combine_scalars(alts: List[_Node], nullable: bool) -> VDom:
    kinds = set()
    enum = set()
    has_kind = False
    for a in alts:
        if isinstance(a, _Scalar):
            kinds.add(a.kind)
            has_kind = True
        elif isinstance(a, _Literal):
            enum.add(a.value)
    if enum and not has_kind:
        return VDom({VDom.STRS}, nullable=nullable, enum=enum)
    if enum and has_kind:
        # mixing a literal with a kind broadens to that kind set (+ string)
        kinds.add(VDom.STRS)
    if VDom.DECS in kinds and VDom.INTS in kinds:
        kinds.discard(VDom.INTS)
    return VDom(kinds, nullable=nullable)


def parse_schema(text: str) -> SchemaAutomaton:
    """Parse Schema-DSL ``text`` into a :class:`SchemaAutomaton`."""
    typedefs, root = _Parser(_tokenize(text)).parse_program()
    return _Builder(typedefs).build(root)


# ===========================================================================
# Serializer:  SchemaAutomaton  ->  DSL text
# ===========================================================================

def schema_to_dsl(sa: SchemaAutomaton) -> str:
    """Render a Schema Automaton back to Schema-DSL text.

    Structural states that are shared (referenced more than once) or recursive
    are emitted as named ``type`` declarations; everything else is inlined.
    """
    # discover reachable states, in-degrees and cycle members via DFS
    indeg: Counter = Counter()
    color: Dict[Any, int] = {}
    on_cycle = set()
    order: List[Any] = []

    def dfs(s: Any) -> None:
        color[s] = 1
        order.append(s)
        for sym in sorted(sa.delta.get(s, {}), key=str):
            dst = sa.delta[s][sym]
            indeg[dst] += 1
            c = color.get(dst, 0)
            if c == 1:
                on_cycle.add(dst)
            elif c == 0:
                dfs(dst)
        color[s] = 2

    dfs(sa.initial)

    def is_structural(s: Any) -> bool:
        return sa.get_content(s).kind in (KIND_MAP, KIND_SEQUENCE)

    named: Dict[Any, str] = {}
    counter = [0]
    for s in order:
        if is_structural(s) and (s in on_cycle or indeg[s] > 1):
            named[s] = f"T{counter[0]}"
            counter[0] += 1

    def expr(s: Any, inline_ok: bool = True) -> str:
        if s in named and inline_ok:
            return named[s]
        return _body(s)

    def _body(s: Any) -> str:
        content = sa.get_content(s)
        nullable = sa.is_struct_nullable(s)
        if content.kind == KIND_MAP:
            parts = []
            required = content.mandatory_symbols()
            for key in sorted(content.symbols()):
                dst = sa.transition(s, key)
                child = expr(dst) if dst is not None else "null"
                opt = "" if key in required else "?"
                parts.append(f"{_field_name(key)}{opt}: {child}")
            if getattr(content, "open", False):
                parts.append("...")
            inner = "{ " + ", ".join(parts) + " }" if parts else "{}"
            return _wrap_nullable(inner, nullable)
        if content.kind == KIND_SEQUENCE:
            if not content.symbols():
                return _wrap_nullable("[]", nullable)
            dst = sa.transition(s, ITEM)
            child = expr(dst) if dst is not None else "null"
            plus = "+" if content.is_mandatory(ITEM) else ""
            return _wrap_nullable(f"[{child}]{plus}", nullable)
        # scalar
        return _vdom_expr(sa.get_vdom(s))

    # Emit named types first (in discovery order), then the root.
    lines: List[str] = []
    for s in order:
        if s in named:
            lines.append(f"type {named[s]} = {_body(s)}")
    root_expr = named[sa.initial] if sa.initial in named else _body(sa.initial)
    lines.append(f"root {root_expr}")
    return "\n".join(lines) + "\n"


_IDENT_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _field_name(key: str) -> str:
    if key and key[0].isalpha() and all(c in _IDENT_OK for c in key):
        return key
    return '"' + key.replace('"', '\\"') + '"'


def _wrap_nullable(expr: str, nullable: bool) -> str:
    return f"{expr}?" if nullable else expr


_KIND_KEYWORD = {VDom.STRS: "string", VDom.INTS: "int", VDom.DECS: "number", VDom.BOOL: "bool"}


def _vdom_expr(vd: VDom) -> str:
    if vd.enum is not None:
        parts = ['"' + v.replace('"', '\\"') + '"' for v in sorted(vd.enum)]
        if vd.nullable:
            parts.append("null")
        return " | ".join(parts) if parts else "null"
    parts = [_KIND_KEYWORD[k] for k in sorted(vd.kinds)]
    if not parts:
        return "null"
    if vd.nullable:
        parts.append("null")
    return " | ".join(parts)
