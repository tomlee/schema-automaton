"""
Tests reproducing the exact examples from the CIKM 2010 paper:
  "XML Schema Computations: Schema Compatibility Testing and Subschema Extraction"

Sections covered:
  §4.1  DataTree construction (DT 1, DT 2, Quote DT, Order DT)
  §4.2  Schema Automaton (SA 1, SA 2, Figure 5 SA)
  §4.2.1 SA validation of DTs
  §5.1  Schema minimization: SA1 → SA2
  §5.3  Schema equivalence: SA1 ≡ SA2
  §5.3.1 Subschema testing: SA3 ⊆ SA1, SA3 ⊆ SA2
  §5.4  Subschema extraction: SA2 - <Product> → SA3
  §5.2  MakeUsefulSA (Figure 8 example)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from src import (
    DataTree, SchemaAutomaton, HLang, VDom,
    make_useful_sa, minimize_sa, equivalent_sa, subschema_sa, extract_subschema,
)


# ===========================================================================
# Helper builders
# ===========================================================================

def build_dt1() -> DataTree:
    """
    Figure 1 — DT 1:
        n0:"us"  → A → n1:"ny"
                 → A → n2:"ca"
                 → B → n3:"50"
        n1       → C → n4:"sf"
                 → C → n5:"la"
    """
    dt = DataTree(root_id="n0", root_value="us")
    dt.add_node("n1", "ny")
    dt.add_node("n2", "ca")
    dt.add_node("n3", "50")
    dt.add_node("n4", "sf")
    dt.add_node("n5", "la")
    dt.add_edge("n0", "n1", "A")
    dt.add_edge("n0", "n2", "A")
    dt.add_edge("n0", "n3", "B")
    dt.add_edge("n1", "n4", "C")
    dt.add_edge("n1", "n5", "C")
    return dt


def build_dt2() -> DataTree:
    """
    Figure 2 — DT 2:
        n0:ε → A → n1:"cn"
               B → n2:"3.14"
               B → n3:"123"
        n1   → C → n4:"bj"
               C → n5:"hk"
    """
    dt = DataTree(root_id="n0", root_value="")
    dt.add_node("n1", "cn")
    dt.add_node("n2", "3.14")
    dt.add_node("n3", "123")
    dt.add_node("n4", "bj")
    dt.add_node("n5", "hk")
    dt.add_edge("n0", "n1", "A")
    dt.add_edge("n0", "n2", "B")
    dt.add_edge("n0", "n3", "B")
    dt.add_edge("n1", "n4", "C")
    dt.add_edge("n1", "n5", "C")
    return dt


def build_figure5_sa() -> SchemaAutomaton:
    """
    Figure 5 SA:
        States: q0, q1, q2, q3
        Transitions: q0→A→q1, q0→B→q2, q1→C→q3, q3→A→q0
        HLangs: q0=A{2,5}B  q1=C*  q2=ε  q3=A*
        VDoms:  q0=STRS  q1=INTS  q2=INTS  q3=STRS
    """
    sa = SchemaAutomaton("q0")
    sa.add_state("q0", HLang.parse("A{2,5}B"), VDom.strs())
    sa.add_state("q1", HLang.parse("C*"), VDom.strs())
    sa.add_state("q2", HLang.epsilon_lang(), VDom.ints())
    sa.add_state("q3", HLang.parse("A*"), VDom.strs())
    sa.add_transition("q0", "A", "q1")
    sa.add_transition("q0", "B", "q2")
    sa.add_transition("q1", "C", "q3")
    sa.add_transition("q3", "A", "q0")
    return sa


def build_sa1() -> SchemaAutomaton:
    """
    Figure 6 — SA 1 (models XSD 1):
        q0: HLang=<Quote>|<Order>  VDom={ε}
        q1: HLang=<Line>+          VDom={ε}   (Quote branch)
        q2: HLang=<Line>+          VDom={ε}   (Order branch)
        q3: HLang=<Desc><Price>    VDom={ε}
        q4: HLang=<Product><Qty>   VDom={ε}
        q5: HLang=ε                VDom=STRS
        q6: HLang=ε                VDom=DECS
        q7: HLang=<Desc><Price>    VDom={ε}
        q8: HLang=ε                VDom=INTS
    """
    null = VDom.null()
    sa = SchemaAutomaton("q0")
    sa.add_state("q0", HLang.parse("Quote|Order"), null)
    sa.add_state("q1", HLang.parse("Line+"), null)
    sa.add_state("q2", HLang.parse("Line+"), null)
    sa.add_state("q3", HLang.parse("Desc Price"), null)
    sa.add_state("q4", HLang.parse("Product Qty"), null)
    sa.add_state("q5", HLang.epsilon_lang(), VDom.strs())
    sa.add_state("q6", HLang.epsilon_lang(), VDom.decs())
    sa.add_state("q7", HLang.parse("Desc Price"), null)
    sa.add_state("q8", HLang.epsilon_lang(), VDom.ints())
    sa.add_transition("q0", "Quote", "q1")
    sa.add_transition("q0", "Order", "q2")
    sa.add_transition("q1", "Line", "q3")
    sa.add_transition("q2", "Line", "q4")
    sa.add_transition("q3", "Desc", "q5")
    sa.add_transition("q3", "Price", "q6")
    sa.add_transition("q4", "Product", "q7")
    sa.add_transition("q4", "Qty", "q8")
    sa.add_transition("q7", "Desc", "q5")
    sa.add_transition("q7", "Price", "q6")
    return sa


def build_sa2() -> SchemaAutomaton:
    """
    Figure 7 — SA 2 (models XSD 2, the minimal form of XSD 1):
        q0: HLang=Quote|Order   VDom={ε}
        q1: HLang=Line+         VDom={ε}
        q2: HLang=Line+         VDom={ε}
        q4: HLang=Product Qty   VDom={ε}
        q5: HLang=ε             VDom=STRS
        q6: HLang=ε             VDom=DECS
        q8: HLang=ε             VDom=INTS
        q9: HLang=Desc Price    VDom={ε}   (merged q3 and q7 from SA1)
    """
    null = VDom.null()
    sa = SchemaAutomaton("q0")
    sa.add_state("q0", HLang.parse("Quote|Order"), null)
    sa.add_state("q1", HLang.parse("Line+"), null)
    sa.add_state("q2", HLang.parse("Line+"), null)
    sa.add_state("q4", HLang.parse("Product Qty"), null)
    sa.add_state("q5", HLang.epsilon_lang(), VDom.strs())
    sa.add_state("q6", HLang.epsilon_lang(), VDom.decs())
    sa.add_state("q8", HLang.epsilon_lang(), VDom.ints())
    sa.add_state("q9", HLang.parse("Desc Price"), null)
    sa.add_transition("q0", "Quote", "q1")
    sa.add_transition("q0", "Order", "q2")
    sa.add_transition("q1", "Line", "q9")
    sa.add_transition("q2", "Line", "q4")
    sa.add_transition("q9", "Desc", "q5")
    sa.add_transition("q9", "Price", "q6")
    sa.add_transition("q4", "Product", "q9")
    sa.add_transition("q4", "Qty", "q8")
    return sa


def build_sa3() -> SchemaAutomaton:
    """
    Figure 9 — SA 3 (models XSD 3, subschema of XSD 1 and XSD 2 — Quote only):
        q0: HLang=Quote         VDom={ε}
        q1: HLang=Line+         VDom={ε}
        q9: HLang=Desc Price    VDom={ε}
        q5: HLang=ε             VDom=STRS
        q6: HLang=ε             VDom=DECS
    """
    null = VDom.null()
    sa = SchemaAutomaton("q0")
    sa.add_state("q0", HLang.parse("Quote"), null)
    sa.add_state("q1", HLang.parse("Line+"), null)
    sa.add_state("q9", HLang.parse("Desc Price"), null)
    sa.add_state("q5", HLang.epsilon_lang(), VDom.strs())
    sa.add_state("q6", HLang.epsilon_lang(), VDom.decs())
    sa.add_transition("q0", "Quote", "q1")
    sa.add_transition("q1", "Line", "q9")
    sa.add_transition("q9", "Desc", "q5")
    sa.add_transition("q9", "Price", "q6")
    return sa


def build_quote_dt() -> DataTree:
    """Figure 3 — DT for Quote document (Listing 3)."""
    dt = DataTree(root_id="n0", root_value="")
    dt.add_node("n1", "")
    dt.add_node("n2", "")
    dt.add_node("n3", "")
    dt.add_node("n4", "hPhone")
    dt.add_node("n5", "499.9")
    dt.add_node("n6", "iMat")
    dt.add_node("n7", "999.9")
    dt.add_edge("n0", "n1", "Quote")
    dt.add_edge("n1", "n2", "Line")
    dt.add_edge("n1", "n3", "Line")
    dt.add_edge("n2", "n4", "Desc")
    dt.add_edge("n2", "n5", "Price")
    dt.add_edge("n3", "n6", "Desc")
    dt.add_edge("n3", "n7", "Price")
    return dt


def build_order_dt() -> DataTree:
    """Figure 4 — DT for Order document (Listing 4)."""
    dt = DataTree(root_id="n0", root_value="")
    dt.add_node("n1", "")
    dt.add_node("n2", "")
    dt.add_node("n3", "")
    dt.add_node("n4", "2")
    dt.add_node("n5", "hPhone")
    dt.add_node("n6", "499.9")
    dt.add_edge("n0", "n1", "Order")
    dt.add_edge("n1", "n2", "Line")
    dt.add_edge("n2", "n3", "Product")
    dt.add_edge("n2", "n4", "Qty")
    dt.add_edge("n3", "n5", "Desc")
    dt.add_edge("n3", "n6", "Price")
    return dt


# ===========================================================================
# §2  HLang and VDom unit tests
# ===========================================================================

class TestHLang:
    def test_epsilon_accepts_empty(self):
        h = HLang.epsilon_lang()
        assert h.accepts([])
        assert not h.accepts(["A"])

    def test_symbol(self):
        h = HLang.parse("A")
        assert h.accepts(["A"])
        assert not h.accepts([])
        assert not h.accepts(["B"])

    def test_sequence(self):
        h = HLang.parse("A B")
        assert h.accepts(["A", "B"])
        assert not h.accepts(["A"])
        assert not h.accepts(["B", "A"])

    def test_alternation(self):
        h = HLang.parse("A|B")
        assert h.accepts(["A"])
        assert h.accepts(["B"])
        assert not h.accepts(["A", "B"])

    def test_star(self):
        h = HLang.parse("A*")
        assert h.accepts([])
        assert h.accepts(["A"])
        assert h.accepts(["A", "A", "A"])
        assert not h.accepts(["B"])

    def test_plus(self):
        h = HLang.parse("A+")
        assert not h.accepts([])
        assert h.accepts(["A"])
        assert h.accepts(["A", "A"])

    def test_optional(self):
        h = HLang.parse("A?")
        assert h.accepts([])
        assert h.accepts(["A"])
        assert not h.accepts(["A", "A"])

    def test_bounded_repeat(self):
        h = HLang.parse("A{2,4}")
        assert not h.accepts(["A"])
        assert h.accepts(["A", "A"])
        assert h.accepts(["A", "A", "A"])
        assert h.accepts(["A", "A", "A", "A"])
        assert not h.accepts(["A", "A", "A", "A", "A"])

    def test_mandatory_symbol(self):
        h = HLang.parse("A+ B")
        assert h.is_mandatory("A")
        assert h.is_mandatory("B")
        h2 = HLang.parse("A*")
        assert not h2.is_mandatory("A")

    def test_remove_symbol(self):
        h = HLang.parse("A B|C")
        # L = {[A,B], [C]}
        # remove B → {[C]}
        restricted = h.remove_symbol("B")
        assert not restricted.accepts(["A", "B"])
        assert restricted.accepts(["C"])

    def test_subset_of(self):
        h1 = HLang.parse("A")
        h2 = HLang.parse("A|B")
        assert h1.is_subset_of(h2)
        assert not h2.is_subset_of(h1)

    def test_language_equals(self):
        # A+ and A A* should be equal
        h1 = HLang.parse("A+")
        h2 = HLang.parse("A A*")
        assert h1.language_equals(h2)


class TestVDom:
    def test_strs_universal(self):
        v = VDom.strs()
        assert v.contains("hello")
        assert v.contains("")
        assert v.contains("123")

    def test_ints(self):
        v = VDom.ints()
        assert v.contains("42")
        assert v.contains("-7")
        assert not v.contains("3.14")
        assert not v.contains("hello")

    def test_decs(self):
        v = VDom.decs()
        assert v.contains("3.14")
        assert v.contains("42")
        assert not v.contains("abc")

    def test_null(self):
        v = VDom.null()
        assert v.contains("")
        assert not v.contains("hello")

    def test_subset(self):
        # Typed (data-format) semantics: a number is NOT a string, so the only
        # cross-kind subset is integer ⊆ number (an integer is a valid number).
        # This keeps subschema testing consistent with typed validation.
        assert VDom.ints().is_subset_of(VDom.decs())
        assert VDom.ints().is_subset_of(VDom.ints())
        assert VDom.strs().is_subset_of(VDom.strs())
        assert not VDom.ints().is_subset_of(VDom.strs())
        assert not VDom.decs().is_subset_of(VDom.ints())
        assert not VDom.strs().is_subset_of(VDom.ints())
        # a non-nullable domain is not a superset of a nullable one
        assert VDom.strs().is_subset_of(VDom.strs().as_nullable())
        assert not VDom.strs().as_nullable().is_subset_of(VDom.strs())

    def test_union_admits_all_members(self):
        u = VDom.union(VDom.ints(), VDom.strs())   # integer | string
        assert u.admits(VDom.ints())
        assert u.admits(VDom.strs())
        assert not u.admits(VDom.bool_())
        assert u.kinds == {VDom.INTS, VDom.STRS}

    def test_numeric_union_widens_to_decimal(self):
        u = VDom.union(VDom.ints(), VDom.decs())
        assert u.kinds == {VDom.DECS}          # integer subsumed by number
        assert u.admits(VDom.ints())
        assert u.admits(VDom.decs())


# ===========================================================================
# §4.1  DataTree tests
# ===========================================================================

class TestDataTree:
    def test_dt1_structure(self):
        dt = build_dt1()
        assert dt.val("n0") == "us"
        assert dt.child_symbol_sequence("n0") == ["A", "A", "B"]
        assert dt.child_symbol_sequence("n1") == ["C", "C"]
        assert dt.child_symbol_sequence("n3") == []

    def test_dt2_structure(self):
        dt = build_dt2()
        assert dt.val("n1") == "cn"
        assert dt.child_symbol_sequence("n0") == ["A", "B", "B"]

    def test_quote_dt_structure(self):
        dt = build_quote_dt()
        assert dt.child_symbol_sequence("n0") == ["Quote"]
        assert dt.child_symbol_sequence("n1") == ["Line", "Line"]
        assert dt.child_symbol_sequence("n2") == ["Desc", "Price"]
        assert dt.val("n4") == "hPhone"
        assert dt.val("n5") == "499.9"

    def test_order_dt_structure(self):
        dt = build_order_dt()
        assert dt.child_symbol_sequence("n2") == ["Product", "Qty"]
        assert dt.val("n4") == "2"


# ===========================================================================
# §4.2  Schema Automaton validation (Definition 3)
# ===========================================================================

class TestSAValidation:
    def test_figure5_accepts_dt1(self):
        """SA (Fig 5) accepts DT 1 (Fig 1)."""
        sa = build_figure5_sa()
        dt1 = build_dt1()
        assert sa.accepts(dt1)

    def test_figure5_rejects_dt2(self):
        """SA (Fig 5) rejects DT 2 (Fig 2)."""
        sa = build_figure5_sa()
        dt2 = build_dt2()
        assert not sa.accepts(dt2)

    def test_sa1_accepts_quote_dt(self):
        sa1 = build_sa1()
        assert sa1.accepts(build_quote_dt())

    def test_sa1_accepts_order_dt(self):
        sa1 = build_sa1()
        assert sa1.accepts(build_order_dt())

    def test_sa2_accepts_quote_dt(self):
        sa2 = build_sa2()
        assert sa2.accepts(build_quote_dt())

    def test_sa2_accepts_order_dt(self):
        sa2 = build_sa2()
        assert sa2.accepts(build_order_dt())

    def test_sa3_accepts_quote_dt(self):
        """SA3 (Quote-only subschema) accepts Quote document."""
        sa3 = build_sa3()
        assert sa3.accepts(build_quote_dt())

    def test_sa3_rejects_order_dt(self):
        """SA3 rejects Order document (Order is not in its language)."""
        sa3 = build_sa3()
        assert not sa3.accepts(build_order_dt())


# ===========================================================================
# §5.1  Schema minimization
# ===========================================================================

class TestMinimization:
    def test_sa1_minimizes_to_fewer_states(self):
        """SA1 should minimize: q3 and q7 collapse into one state."""
        sa1 = build_sa1()
        min_sa = minimize_sa(sa1)
        # SA1 has 9 states; SA2 has 8 states (q3+q7 merged)
        assert len(min_sa.states) < len(sa1.states)

    def test_minimal_sa_still_accepts_quote(self):
        sa1 = build_sa1()
        min_sa = minimize_sa(sa1)
        assert min_sa.accepts(build_quote_dt())

    def test_minimal_sa_still_accepts_order(self):
        sa1 = build_sa1()
        min_sa = minimize_sa(sa1)
        assert min_sa.accepts(build_order_dt())


# ===========================================================================
# §5.3  Schema equivalence testing
# ===========================================================================

class TestEquivalence:
    def test_sa1_equiv_sa2(self):
        """SA1 ≡ SA2  (Theorem 4, confirmed by paper)."""
        assert equivalent_sa(build_sa1(), build_sa2())

    def test_sa2_equiv_sa1(self):
        assert equivalent_sa(build_sa2(), build_sa1())

    def test_sa3_not_equiv_sa1(self):
        """SA3 (Quote-only) is NOT equivalent to SA1 (Quote + Order)."""
        assert not equivalent_sa(build_sa3(), build_sa1())

    def test_sa_equiv_self(self):
        assert equivalent_sa(build_sa2(), build_sa2())


# ===========================================================================
# §5.3.1  Subschema testing
# ===========================================================================

class TestSubschemaTesting:
    def test_sa3_subschema_of_sa1(self):
        """SA3 is a subschema of SA1."""
        report = subschema_sa(build_sa3(), build_sa1())
        assert report.is_compatible, str(report)

    def test_sa3_subschema_of_sa2(self):
        """SA3 is a subschema of SA2."""
        report = subschema_sa(build_sa3(), build_sa2())
        assert report.is_compatible, str(report)

    def test_sa1_not_subschema_of_sa3(self):
        """SA1 is NOT a subschema of SA3 (SA3 rejects Order docs)."""
        report = subschema_sa(build_sa1(), build_sa3())
        assert not report.is_compatible

    def test_sa1_subschema_of_sa2(self):
        """SA1 ⊆ SA2 (they are equivalent)."""
        report = subschema_sa(build_sa1(), build_sa2())
        assert report.is_compatible, str(report)


# ===========================================================================
# §5.4  Subschema extraction
# ===========================================================================

class TestSubschemaExtraction:
    def test_extract_quote_only(self):
        """
        Extract from SA2 with all symbols except <Product> → should yield
        a schema equivalent to SA3 (Quote-only after losing Order branch).

        Per paper §5.4: removing Product symbol from SA2 collapses the Order
        branch because Product is mandatory in the OrderLineType HLang.
        The result should equal SA3.
        """
        sa2 = build_sa2()
        permitted = {"Quote", "Order", "Line", "Qty", "Desc", "Price"}
        extracted = extract_subschema(sa2, permitted)

        # Must accept Quote documents
        assert extracted.accepts(build_quote_dt())
        # Must NOT accept Order documents (Product was mandatory for Order branch)
        assert not extracted.accepts(build_order_dt())

    def test_extracted_equiv_sa3(self):
        """Extracted subschema ≡ SA3."""
        sa2 = build_sa2()
        permitted = {"Quote", "Order", "Line", "Qty", "Desc", "Price"}
        extracted = extract_subschema(sa2, permitted)
        assert equivalent_sa(extracted, build_sa3())

    def test_extract_preserves_all_symbols(self):
        """Extracting with the full symbol set returns an equivalent schema."""
        sa2 = build_sa2()
        permitted = set(sa2.symbols)
        extracted = extract_subschema(sa2, permitted)
        assert equivalent_sa(extracted, sa2)


# ===========================================================================
# §5.2  MakeUsefulSA / irrational states
# ===========================================================================

class TestMakeUseful:
    def test_remove_inaccessible_states(self):
        """States not reachable from q0 are removed."""
        sa = SchemaAutomaton("q0")
        sa.add_state("q0", HLang.parse("A"), VDom.strs())
        sa.add_state("q_orphan", HLang.epsilon_lang(), VDom.strs())
        sa.add_state("q1", HLang.epsilon_lang(), VDom.strs())
        sa.add_transition("q0", "A", "q1")
        # q_orphan is never reachable
        make_useful_sa(sa)
        assert "q_orphan" not in sa.states
        assert "q0" in sa.states
        assert "q1" in sa.states

    def test_irrational_cycle_removed(self):
        """States on a mandatory-transition cycle are removed.

        q_root reaches the cycle via an *optional* edge (Start?), so q_root
        itself survives; only the irrational q0/q1 are removed.
        """
        # q0 → A(mandatory) → q1 → B(mandatory) → q0 (cycle → both irrational)
        sa = SchemaAutomaton("q_root")
        sa.add_state("q_root", HLang.parse("Start?"), VDom.strs())  # optional → q_root useful
        sa.add_state("q0", HLang.parse("A"), VDom.strs())   # A is mandatory
        sa.add_state("q1", HLang.parse("B"), VDom.strs())   # B is mandatory
        sa.add_transition("q_root", "Start", "q0")
        sa.add_transition("q0", "A", "q1")
        sa.add_transition("q1", "B", "q0")
        make_useful_sa(sa)
        # q0 and q1 form an irrational mandatory cycle → should be removed
        assert "q0" not in sa.states
        assert "q1" not in sa.states
        # q_root survives because its path into the cycle was optional
        assert "q_root" in sa.states

    def test_mandatory_path_to_irrational_makes_initial_useless(self):
        """If the initial state mandatorily requires an irrational state,
        no useful equivalent SA exists (Theorem 1)."""
        sa = SchemaAutomaton("q_root")
        sa.add_state("q_root", HLang.parse("Start"), VDom.strs())  # mandatory
        sa.add_state("q0", HLang.parse("A"), VDom.strs())
        sa.add_state("q1", HLang.parse("B"), VDom.strs())
        sa.add_transition("q_root", "Start", "q0")
        sa.add_transition("q0", "A", "q1")
        sa.add_transition("q1", "B", "q0")
        with pytest.raises(ValueError):
            make_useful_sa(sa)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
