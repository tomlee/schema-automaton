"""Horizontal Language — regular language over sequences of element-name symbols.

Syntax supported in HLang.parse():
  epsilon          → {ε}
  Sym / <Sym>      → single symbol
  a b              → concatenation (space or adjacent tokens)
  a|b              → alternation
  a*  a+  a?       → Kleene star / plus / optional
  a{n,m}           → bounded repetition (m can be * for unbounded)
  (...)            → grouping
"""

from __future__ import annotations
from typing import List, Optional, Set, Tuple

from .nfa import (
    NFA, DFA,
    nfa_symbol, nfa_epsilon, nfa_union, nfa_concat,
    nfa_star, nfa_plus, nfa_optional, nfa_repeat,
)
from .content_model import ContentModel, KIND_SEQUENCE


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_SPECIAL = set("|()*+?{},")


def _tokenize(pattern: str) -> List[str]:
    tokens: List[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c in " \t":
            i += 1
        elif c == "<":
            j = pattern.index(">", i)
            tokens.append(pattern[i + 1: j])  # strip < >
            i = j + 1
        elif c in _SPECIAL:
            tokens.append(c)
            i += 1
        elif c.isdigit():
            j = i
            while j < len(pattern) and pattern[j].isdigit():
                j += 1
            tokens.append(pattern[i:j])
            i = j
        else:
            # identifier / keyword
            j = i
            while j < len(pattern) and pattern[j] not in _SPECIAL and pattern[j] not in " \t":
                j += 1
            tokens.append(pattern[i:j])
            i = j
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser  (produces NFA)
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: List[str]) -> None:
        self._tok = tokens
        self._pos = 0

    def _peek(self) -> Optional[str]:
        return self._tok[self._pos] if self._pos < len(self._tok) else None

    def _consume(self) -> str:
        t = self._tok[self._pos]
        self._pos += 1
        return t

    def parse(self) -> NFA:
        n = self._alternation()
        return n

    def _alternation(self) -> NFA:
        left = self._concatenation()
        while self._peek() == "|":
            self._consume()
            right = self._concatenation()
            left = nfa_union(left, right)
        return left

    def _concatenation(self) -> NFA:
        result: Optional[NFA] = None
        while self._peek() not in (None, "|", ")"):
            atom = self._quantified()
            result = atom if result is None else nfa_concat(result, atom)
        return result if result is not None else nfa_epsilon()

    def _quantified(self) -> NFA:
        atom = self._atom()
        q = self._peek()
        if q == "*":
            self._consume()
            return nfa_star(atom)
        if q == "+":
            self._consume()
            return nfa_plus(atom)
        if q == "?":
            self._consume()
            return nfa_optional(atom)
        if q == "{":
            self._consume()          # {
            lo_tok = self._consume() # n
            self._consume()          # ,
            hi_tok = self._consume() # m or *
            self._consume()          # }
            lo = int(lo_tok)
            hi = None if hi_tok == "*" else int(hi_tok)
            return nfa_repeat(atom, lo, hi)
        return atom

    def _atom(self) -> NFA:
        t = self._peek()
        if t == "(":
            self._consume()
            n = self._alternation()
            self._consume()  # )
            return n
        if t is not None and t not in _SPECIAL and not t.lstrip("-").isdigit():
            self._consume()
            if t.lower() in ("epsilon", "ε", "eps"):
                return nfa_epsilon()
            return nfa_symbol(t)
        # fallback: treat as epsilon
        return nfa_epsilon()


# ---------------------------------------------------------------------------
# HLang class
# ---------------------------------------------------------------------------

class HLang(ContentModel):
    """
    Horizontal language — the ordered ``SequenceModel`` content model.

    Wraps an NFA/DFA so it can decide regular languages over child-edge symbols.
    This is the content model used for XML element sequences and ordered
    JSON/YAML array content.
    """

    kind = KIND_SEQUENCE

    def __init__(self, nfa: NFA, description: str = "") -> None:
        self._nfa = nfa
        self._dfa: Optional[DFA] = None
        self.description = description

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _get_dfa(self) -> DFA:
        if self._dfa is None:
            self._dfa = self._nfa.to_dfa()
        return self._dfa

    def accepts(self, word: List[str]) -> bool:
        return self._get_dfa().accepts(word)

    def accepts_empty(self) -> bool:
        return self.accepts([])

    def is_subset_of(self, other: "ContentModel") -> bool:
        if not isinstance(other, HLang):
            # an ordered language is a subset of a map/scalar model only if it is
            # the empty language
            return self.is_empty()
        # Literal-equality short-circuit (paper §6): identical regular-expression
        # text denotes the same language, so the cheap string compare avoids the
        # PSPACE DFA inclusion test in the common case.
        if self.description and self.description == other.description:
            return True
        return self._get_dfa().is_subset_of(other._get_dfa())

    def language_equals(self, other: "ContentModel") -> bool:
        """Full DFA-based language equality test (with a literal short-circuit)."""
        if not isinstance(other, HLang):
            return self.is_empty() and other.is_empty()
        if self.description and self.description == other.description:
            return True
        return self._get_dfa().language_equals(other._get_dfa())

    def canonical_key(self) -> tuple:
        """Hashable canonical form — equal keys iff languages are equal."""
        return (KIND_SEQUENCE,) + self._get_dfa().canonical_key()

    def is_empty(self) -> bool:
        return self._get_dfa().is_empty()

    # ------------------------------------------------------------------
    # Symbol-level queries
    # ------------------------------------------------------------------

    def alphabet_set(self) -> Set[str]:
        """All symbols known to this language.

        Consults both the NFA and any derived DFA so the result stays correct
        even after operations like ``remove_symbol`` replace the NFA.
        """
        alpha: Set[str] = set(self._nfa.alphabet)
        if self._dfa is not None:
            alpha |= set(self._dfa.alphabet)
        return alpha

    def symbols(self) -> Set[str]:
        return self.alphabet_set()

    def _restrictor_dfa(self, excluded_sym: str) -> DFA:
        """DFA for (Σ - {excluded_sym})* over this language's alphabet."""
        alpha = self.alphabet_set() | {excluded_sym}
        restrictor = NFA()
        s = restrictor.new_state()
        restrictor.start = s
        restrictor.accept = {s}
        for sym in alpha:
            if sym != excluded_sym:
                restrictor.add_trans(s, sym, s)
        return restrictor.to_dfa()

    def is_mandatory(self, symbol: str) -> bool:
        """True if *symbol* appears in every word of this language."""
        # mandatory iff L ∩ (Σ-{symbol})* = ∅
        restricted = self._get_dfa().intersection(self._restrictor_dfa(symbol))
        return restricted.is_empty()

    def mandatory_symbols(self) -> Set[str]:
        return {a for a in self.alphabet_set() if self.is_mandatory(a)}

    def remove_symbol(self, symbol: str) -> "HLang":
        """Return L ∩ (Σ - {symbol})* — strings in this language not containing symbol."""
        result_dfa = self._get_dfa().intersection(self._restrictor_dfa(symbol))
        h = HLang(NFA(), f"({self.description}) \\ {{{symbol}}}")
        h._dfa = result_dfa
        return h

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @staticmethod
    def parse(pattern: str) -> "HLang":
        tokens = _tokenize(pattern)
        nfa = _Parser(tokens).parse()
        return HLang(nfa, pattern)

    @staticmethod
    def epsilon_lang() -> "HLang":
        """Language {ε} — accepts only the empty sequence."""
        return HLang(nfa_epsilon(), "epsilon")

    @staticmethod
    def empty_lang() -> "HLang":
        """Empty language — accepts nothing."""
        n = NFA()
        n.new_state()
        return HLang(n, "∅")

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"HLang({self.description!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HLang):
            return False
        # fast path: literal description match
        if self.description == other.description:
            return True
        return self.language_equals(other)

    def __hash__(self) -> int:
        return hash(self.canonical_key())
