"""XML Schema Computation Algorithms — Section 5 of the paper.

Implements:
    Algorithm 1  MakeUsefulSA      — remove useless states
    Algorithm 2  MinimizeSA        — merge equivalent states → minimal SA
    Algorithm 3  EquivalentSA      — test schema equivalence
    Algorithm 4  SubschemaSA       — test subschema relationship
    Algorithm 5  ExtractSubschema  — extract subschema for a symbol subset
"""

from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from .hlang import HLang
from .vdom import VDom
from .schema_automaton import SchemaAutomaton


# ============================================================
# Incompatibility report (returned by SubschemaSA on failure)
# ============================================================

class IncompatibilityReport:
    def __init__(self) -> None:
        self.vdom_issues: List[Tuple[Any, Any]] = []       # (state_A, state_B)
        self.content_issues: List[Tuple[Any, Any]] = []      # (state_A, state_B)
        self.transition_issues: List[Tuple[Any, str]] = [] # (state_A, symbol)

    @property
    def is_compatible(self) -> bool:
        return not (self.vdom_issues or self.content_issues or self.transition_issues)

    def __str__(self) -> str:
        if self.is_compatible:
            return "Compatible (no issues found)"
        lines = ["Incompatibility detected:"]
        for a, b in self.vdom_issues:
            lines.append(f"  VDom mismatch: VDom({a}) ⊄ VDom({b})")
        for a, b in self.content_issues:
            lines.append(f"  Content mismatch: Content({a}) ⊄ Content({b})")
        for a, sym in self.transition_issues:
            lines.append(f"  Transition missing in B: δ({a}, {sym!r}) exists in A but not in B")
        return "\n".join(lines)


# ============================================================
# Algorithm 1 — MakeUsefulSA
# ============================================================

def make_useful_sa(sa: SchemaAutomaton) -> None:
    """
    Modify *sa* in-place to remove all useless states.

    A state is useless if it is:
      (1) inaccessible from q0, or
      (2) irrational (on a mandatory-transition cycle), or
      (3) has a mandatory path to an irrational state, or
      (4) reachable only through useless states.

    Raises ValueError if q0 itself becomes useless.
    """

    # ----- Step 1: find all mandatory transitions -----
    # mandatory_trans[q] = set of symbols a where transition q->a is mandatory
    def _mandatory_syms(q: Any) -> Set[str]:
        return sa.get_content(q).mandatory_symbols()

    # ----- Step 2: find irrational states (cycles of mandatory transitions) -----
    useless: Set[Any] = set()

    # Build mandatory-transition graph
    mand_graph: Dict[Any, Set[Any]] = {}
    for q in sa.states:
        mand_graph[q] = set()
        for sym in _mandatory_syms(q):
            dst = sa.transition(q, sym)
            if dst is not None:
                mand_graph[q].add(dst)

    # Tarjan SCC to find states on cycles (irrational = on a non-trivial SCC
    # that is reachable via only mandatory edges)
    index_counter = [0]
    stack: List[Any] = []
    on_stack: Set[Any] = set()
    index: Dict[Any, int] = {}
    lowlink: Dict[Any, int] = {}
    irrational: Set[Any] = set()

    def strongconnect(v: Any) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in mand_graph.get(v, set()):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: Set[Any] = set()
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.add(w)
                if w == v:
                    break
            # SCC of size > 1 → all members are irrational
            # SCC of size 1 with self-loop on mandatory edge → irrational
            if len(scc) > 1:
                irrational.update(scc)
            elif len(scc) == 1:
                lone = next(iter(scc))
                if lone in mand_graph.get(lone, set()):
                    irrational.add(lone)

    for q in list(sa.states):
        if q not in index:
            strongconnect(q)

    useless |= irrational

    # ----- Step 3: propagate uselessness backwards via mandatory transitions -----
    # A state q is useless if it has a mandatory transition to a useless state.
    changed = True
    while changed:
        changed = False
        for q in sa.states - useless:
            for sym in _mandatory_syms(q):
                dst = sa.transition(q, sym)
                if dst in useless:
                    useless.add(q)
                    changed = True
                    break

    # Check if q0 itself is useless
    if sa.initial in useless:
        raise ValueError("No useful SA equivalent exists: initial state is useless.")

    # ----- Step 4: find inaccessible states -----
    accessible: Set[Any] = set()
    stack2: List[Any] = [sa.initial]
    while stack2:
        q = stack2.pop()
        if q in accessible:
            continue
        accessible.add(q)
        for sym, dst in sa.delta.get(q, {}).items():
            if dst is not None and dst not in accessible:
                stack2.append(dst)

    inaccessible = sa.states - accessible
    useless |= inaccessible

    # ----- Step 5: modify HLangs to exclude transitions to useless states -----
    for q in sa.states - useless:
        bad_syms = {
            sym for sym, dst in sa.delta.get(q, {}).items()
            if dst in useless
        }
        if bad_syms:
            h = sa.get_content(q)
            for sym in bad_syms:
                h = h.remove_symbol(sym)
            sa.set_content(q, h)

    # ----- Step 6: remove useless states and their transitions -----
    for q in useless:
        sa.states.discard(q)
        sa.content.pop(q, None)
        sa.vdom.pop(q, None)
        sa.delta.pop(q, None)
        sa.nullable_struct.pop(q, None)

    # Remove transitions pointing to useless states
    for q in list(sa.delta.keys()):
        if q in useless:
            continue
        sa.delta[q] = {
            sym: dst
            for sym, dst in sa.delta[q].items()
            if dst not in useless
        }

    # Recompute symbol set
    sa.symbols = {sym for d in sa.delta.values() for sym in d}


# ============================================================
# Algorithm 2 — MinimizeSA
# ============================================================

def minimize_sa(sa: SchemaAutomaton) -> SchemaAutomaton:
    """
    Return a new minimal SA equivalent to *sa*.

    First makes *sa* useful, then merges equivalent states via
    partition refinement (Theorem 2).
    """
    working = deepcopy(sa)
    make_useful_sa(working)

    if not working.states:
        return working

    # Initial partition: group states by (content language, VDom, struct nullability)
    def _key(q: Any) -> tuple:
        return (working.get_content(q).canonical_key(), working.get_vdom(q),
                working.is_struct_nullable(q))

    blocks: Dict[tuple, Set[Any]] = {}
    for q in working.states:
        k = _key(q)
        blocks.setdefault(k, set()).add(q)

    # Map each state to its block representative (a frozenset)
    partition: List[FrozenSet[Any]] = [frozenset(b) for b in blocks.values()]

    def _block_of(q: Any) -> Optional[FrozenSet[Any]]:
        for b in partition:
            if q in b:
                return b
        return None

    # Iterative refinement
    changed = True
    while changed:
        changed = False
        new_partition: List[FrozenSet[Any]] = []
        for block in partition:
            # Try to split block: two states q1,q2 are in different sub-blocks if
            # there exists a symbol a where δ(q1,a) and δ(q2,a) land in different blocks.
            sub_groups: Dict[tuple, Set[Any]] = {}
            for q in block:
                sig: List[Optional[FrozenSet[Any]]] = []
                for sym in sorted(working.symbols):
                    dst = working.transition(q, sym)
                    sig.append(_block_of(dst) if dst is not None else None)
                key = tuple(id(b) if b is not None else -1 for b in sig)
                sub_groups.setdefault(key, set()).add(q)

            if len(sub_groups) > 1:
                changed = True
                for sub in sub_groups.values():
                    new_partition.append(frozenset(sub))
            else:
                new_partition.append(block)
        partition = new_partition

    # Build the new minimized SA using block representatives as states
    block_id: Dict[FrozenSet[Any], int] = {b: i for i, b in enumerate(partition)}

    def _block_for(q: Optional[Any]) -> Optional[int]:
        if q is None:
            return None
        b = _block_of(q)
        return block_id[b] if b is not None else None

    init_block = _block_of(working.initial)
    new_initial = block_id[init_block]

    result = SchemaAutomaton(new_initial)
    for block in partition:
        bid = block_id[block]
        rep = next(iter(block))
        result.add_state(bid, working.get_content(rep), working.get_vdom(rep))
        if working.is_struct_nullable(rep):
            result.set_struct_nullable(bid, True)
        for sym, dst in working.delta.get(rep, {}).items():
            dst_bid = _block_for(dst)
            if dst_bid is not None:
                result.add_transition(bid, sym, dst_bid)

    return result


# ============================================================
# Algorithm 3 — EquivalentSA
# ============================================================

def equivalent_sa(sa_a: SchemaAutomaton, sa_b: SchemaAutomaton) -> bool:
    """
    Return True iff L(sa_a) = L(sa_b)  (schema equivalence).

    Both SAs are minimized then checked for isomorphism by
    parallel BFS from their initial states (Theorem 4).
    """
    a = minimize_sa(sa_a)
    b = minimize_sa(sa_b)

    # Parallel BFS
    visited: Set[Tuple[Any, Any]] = set()
    queue: List[Tuple[Any, Any]] = [(a.initial, b.initial)]
    visited.add((a.initial, b.initial))

    while queue:
        qa, qb = queue.pop(0)

        if a.get_vdom(qa) != b.get_vdom(qb):
            return False
        if a.is_struct_nullable(qa) != b.is_struct_nullable(qb):
            return False
        if not a.get_content(qa).language_equals(b.get_content(qb)):
            return False

        all_syms = a.symbols | b.symbols
        for sym in all_syms:
            na = a.transition(qa, sym)
            nb = b.transition(qb, sym)
            if (na is None) != (nb is None):
                return False
            if na is not None and nb is not None:
                pair = (na, nb)
                if pair not in visited:
                    visited.add(pair)
                    queue.append(pair)

    return True


# ============================================================
# Algorithm 4 — SubschemaSA
# ============================================================

def subschema_sa(
    sa_a: SchemaAutomaton,
    sa_b: SchemaAutomaton,
) -> IncompatibilityReport:
    """
    Test whether L(sa_a) ⊆ L(sa_b)  (sa_a is a subschema of sa_b).

    Returns an IncompatibilityReport; call .is_compatible to get a bool.
    """
    report = IncompatibilityReport()

    working_a = deepcopy(sa_a)
    make_useful_sa(working_a)

    visited: Set[Tuple[Any, Any]] = set()
    queue: List[Tuple[Any, Any]] = [(working_a.initial, sa_b.initial)]
    visited.add((working_a.initial, sa_b.initial))

    while queue:
        qa, qb = queue.pop(0)

        if not working_a.get_vdom(qa).is_subset_of(sa_b.get_vdom(qb)):
            report.vdom_issues.append((qa, qb))

        # If A admits a null here but B does not, A is not a subschema of B.
        if working_a.is_struct_nullable(qa) and not sa_b.is_struct_nullable(qb):
            report.vdom_issues.append((qa, qb))

        if not working_a.get_content(qa).is_subset_of(sa_b.get_content(qb)):
            report.content_issues.append((qa, qb))

        for sym in working_a.symbols:
            na = working_a.transition(qa, sym)
            if na is None:
                continue
            nb = sa_b.transition(qb, sym)
            if nb is None:
                report.transition_issues.append((qa, sym))
            else:
                pair = (na, nb)
                if pair not in visited:
                    visited.add(pair)
                    queue.append(pair)

    return report


# ============================================================
# Algorithm 5 — ExtractSubschema
# ============================================================

def extract_subschema(
    sa: SchemaAutomaton,
    permitted_symbols: Set[str],
) -> SchemaAutomaton:
    """
    Extract a subschema that accepts only instances whose d-edge symbols
    are all in *permitted_symbols*.

    Returns a new minimized SA.  Raises ValueError if no valid subschema
    exists (e.g., the initial state has a mandatory transition on a
    forbidden symbol).
    """
    result = deepcopy(sa)

    # Step 1: collect all (state, symbol) pairs where symbol is not permitted
    pending: List[Tuple[Any, str]] = [
        (q, sym)
        for q in result.states
        for sym in list(result.delta.get(q, {}).keys())
        if sym not in permitted_symbols
    ]

    in_pending: Set[Tuple[Any, str]] = set(pending)

    while pending:
        q, sym = pending.pop()
        if (q, sym) not in in_pending:
            continue
        in_pending.discard((q, sym))

        # Delete this transition
        result.delta.get(q, {}).pop(sym, None)

        # Step 13: update HLang to exclude strings containing sym
        result.set_content(q, result.get_content(q).remove_symbol(sym))

        # Step 5: if this was a mandatory transition, q itself must be removed
        # We detect "was mandatory" by checking the *original* HLang before
        # deletion — but we already modified it. We rely on whether the sym
        # was mandatory in the HLang at the time we pull it off the list.
        # The paper's intent: check if (q, sym) was mandatory when queued.
        # Approximation: check if sym still appeared in every string in HLang
        # before we removed it — here we use the pre-removal check by
        # inspecting whether removing sym empties the language entirely for q.
        # Simpler: sym is mandatory iff it was in mandatory_symbols() before removal.
        # We track this by checking the CURRENT HLang accepts ε (step 5 check).

        # After removal: if q's new HLang doesn't accept what it needs to,
        # propagate: remove all transitions INTO q.
        # Per the algorithm: if (q,sym) was a mandatory transition, q must go.
        # We detect this: after deleting sym from HLang(q), if the original
        # HLang required sym in every string, the language was non-empty before
        # and becomes restricted. We check: does the updated HLang still have
        # any valid strings?  If q cannot accept any subtree, remove it.
        # (The algorithm checks at the time of queuing; we approximate here.)
        # The most correct check: see if the deletion of sym was mandatory.
        # We do this by checking: is (q, sym) such that sym was in every string
        # of the PREVIOUS HLang? We note the prev HLang had sym removed to get
        # current — if the "remove_symbol" produced an empty language, sym was
        # mandatory before.

        current_content = result.get_content(q)
        # If removing sym made the content model empty, sym was mandatory → remove q
        if current_content.is_empty():
            if q == result.initial:
                raise ValueError(
                    f"No valid subschema: initial state {q!r} requires "
                    f"mandatory symbol {sym!r} which is not permitted."
                )
            # Queue all transitions leading into q for deletion
            for src in list(result.states):
                for s, dst in list(result.delta.get(src, {}).items()):
                    if dst == q:
                        pair = (src, s)
                        if pair not in in_pending:
                            in_pending.add(pair)
                            pending.append(pair)

    # Step 15-16: MakeUsefulSA then MinimizeSA
    make_useful_sa(result)
    return minimize_sa(result)
