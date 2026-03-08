"""Index building and query tests."""

from __future__ import annotations

from lattice_lens.models import EdgeType, FactStatus
from lattice_lens.store.index import INVERSE_LABELS
from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact


class TestFactIndex:
    def test_index_builds_from_facts(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        assert len(index.all_facts()) == 12

    def test_codes_by_tag(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        arch_codes = index.codes_by_tag("architecture")
        assert "ADR-01" in arch_codes
        assert "DES-01" in arch_codes

    def test_codes_by_layer(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        why_codes = index.codes_by_layer("WHY")
        assert "ADR-01" in why_codes
        assert "ADR-03" in why_codes
        assert "PRD-01" in why_codes
        assert "DES-01" in why_codes

    def test_refs_forward(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        refs = index.refs_from("ADR-01")
        assert "DES-01" in refs
        assert "RISK-03" in refs
        assert "API-01" in refs

    def test_refs_reverse(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        # DES-01 is referenced by ADR-01
        refs_to = index.refs_to("DES-01")
        assert "ADR-01" in refs_to

    def test_get_from_index(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        fact = index.get("ADR-01")
        assert fact is not None
        assert fact.code == "ADR-01"

    def test_empty_index(self, yaml_store: YamlFileStore):
        index = yaml_store.index
        assert len(index.all_facts()) == 0
        assert index.get("ADR-01") is None
        assert index.codes_by_tag("test") == set()


class TestTypedEdges:
    """Tests for typed edge indexing (Phase 2)."""

    def test_edges_from_typed_seed(self, seeded_store: YamlFileStore):
        """Seed data uses typed refs — ADR-01 drives DES-01."""
        index = seeded_store.index
        edges = index.edges_from("ADR-01")
        assert "DES-01" in edges
        assert edges["DES-01"] == EdgeType.DRIVES

    def test_edges_from_typed(self, yaml_store: YamlFileStore):
        """Facts with typed refs produce correct edge types."""
        fact = make_fact(
            code="ADR-01",
            refs=[{"code": "DES-01", "rel": "drives"}, {"code": "RISK-01", "rel": "mitigates"}],
        )
        yaml_store.create(fact)
        yaml_store.invalidate_index()
        index = yaml_store.index
        edges = index.edges_from("ADR-01")
        assert edges["DES-01"] == EdgeType.DRIVES
        assert edges["RISK-01"] == EdgeType.MITIGATES

    def test_edges_to_reverse(self, yaml_store: YamlFileStore):
        """Reverse edge index populated correctly."""
        fact = make_fact(
            code="ADR-01",
            refs=[{"code": "DES-01", "rel": "drives"}],
        )
        yaml_store.create(fact)
        yaml_store.invalidate_index()
        index = yaml_store.index
        edges = index.edges_to("DES-01")
        assert "ADR-01" in edges
        assert edges["ADR-01"] == EdgeType.DRIVES

    def test_edges_from_filter(self, yaml_store: YamlFileStore):
        """edge_types filter limits returned edges."""
        fact = make_fact(
            code="ADR-01",
            refs=[
                {"code": "DES-01", "rel": "drives"},
                {"code": "RISK-01", "rel": "mitigates"},
                {"code": "PRD-01", "rel": "relates"},
            ],
        )
        yaml_store.create(fact)
        yaml_store.invalidate_index()
        index = yaml_store.index
        edges = index.edges_from("ADR-01", edge_types=[EdgeType.DRIVES])
        assert "DES-01" in edges
        assert "RISK-01" not in edges
        assert "PRD-01" not in edges

    def test_edges_to_filter(self, yaml_store: YamlFileStore):
        """edge_types filter on reverse edges."""
        f1 = make_fact(code="ADR-01", refs=[{"code": "DES-01", "rel": "drives"}])
        f2 = make_fact(code="ADR-02", refs=[{"code": "DES-01", "rel": "relates"}])
        yaml_store.create(f1)
        yaml_store.create(f2)
        yaml_store.invalidate_index()
        index = yaml_store.index
        edges = index.edges_to("DES-01", edge_types=[EdgeType.DRIVES])
        assert "ADR-01" in edges
        assert "ADR-02" not in edges

    def test_edges_from_empty(self, yaml_store: YamlFileStore):
        """Fact with no refs returns empty edges."""
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)
        yaml_store.invalidate_index()
        index = yaml_store.index
        assert index.edges_from("ADR-01") == {}

    def test_edges_to_no_inbound(self, yaml_store: YamlFileStore):
        """Fact with no inbound refs returns empty edges."""
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)
        yaml_store.invalidate_index()
        index = yaml_store.index
        assert index.edges_to("ADR-01") == {}


class TestInverseLabels:
    def test_all_edge_types_have_inverse(self):
        for edge_type in EdgeType:
            assert edge_type in INVERSE_LABELS

    def test_inverse_label_format(self):
        assert INVERSE_LABELS[EdgeType.DRIVES] == "driven_by"
        assert INVERSE_LABELS[EdgeType.SUPERSEDES] == "superseded_by"
        assert INVERSE_LABELS[EdgeType.RELATES] == "related_to"


class TestNeighborhood:
    """Tests for BFS neighborhood traversal."""

    def _build_index(self, yaml_store, facts):
        """Helper to create facts and build index."""
        for fact in facts:
            yaml_store.create(fact)
        yaml_store.invalidate_index()
        return yaml_store.index

    def test_depth_0_returns_seeds_only(self, yaml_store: YamlFileStore):
        """Depth 0 means no expansion."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01")
        index = self._build_index(yaml_store, [f1, f2])
        result = index.neighborhood({"ADR-01"}, max_depth=0)
        assert result == {"ADR-01": 0}

    def test_depth_1_finds_direct_neighbors(self, yaml_store: YamlFileStore):
        """Depth 1 finds directly connected facts."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01")
        index = self._build_index(yaml_store, [f1, f2])
        result = index.neighborhood({"ADR-01"}, max_depth=1)
        assert result == {"ADR-01": 0, "DES-01": 1}

    def test_depth_1_traverses_reverse(self, yaml_store: YamlFileStore):
        """Depth 1 also follows reverse edges."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01")
        index = self._build_index(yaml_store, [f1, f2])
        # Starting from DES-01, should find ADR-01 via reverse edge
        result = index.neighborhood({"DES-01"}, max_depth=1)
        assert result == {"DES-01": 0, "ADR-01": 1}

    def test_depth_2_traverses_two_hops(self, yaml_store: YamlFileStore):
        """Depth 2 follows chains: A → B → C."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01", refs=["SP-01"])
        f3 = make_fact(code="SP-01", layer="HOW", type="System Prompt Rule")
        index = self._build_index(yaml_store, [f1, f2, f3])
        result = index.neighborhood({"ADR-01"}, max_depth=2)
        assert result == {"ADR-01": 0, "DES-01": 1, "SP-01": 2}

    def test_depth_1_stops_at_one_hop(self, yaml_store: YamlFileStore):
        """Depth 1 does not reach two-hop neighbors."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01", refs=["SP-01"])
        f3 = make_fact(code="SP-01", layer="HOW", type="System Prompt Rule")
        index = self._build_index(yaml_store, [f1, f2, f3])
        result = index.neighborhood({"ADR-01"}, max_depth=1)
        assert "SP-01" not in result

    def test_unbounded_depth(self, yaml_store: YamlFileStore):
        """Depth -1 traverses entire connected component."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01", refs=["SP-01"])
        f3 = make_fact(code="SP-01", layer="HOW", type="System Prompt Rule")
        index = self._build_index(yaml_store, [f1, f2, f3])
        result = index.neighborhood({"ADR-01"}, max_depth=-1)
        assert set(result.keys()) == {"ADR-01", "DES-01", "SP-01"}

    def test_excluded_statuses_skipped(self, yaml_store: YamlFileStore):
        """Deprecated facts are skipped during traversal."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01", status=FactStatus.DEPRECATED)
        index = self._build_index(yaml_store, [f1, f2])
        result = index.neighborhood(
            {"ADR-01"}, max_depth=1, excluded_statuses={FactStatus.DEPRECATED}
        )
        assert result == {"ADR-01": 0}
        assert "DES-01" not in result

    def test_edge_type_filter(self, yaml_store: YamlFileStore):
        """edge_types filter limits which edges are traversed."""
        f1 = make_fact(
            code="ADR-01",
            refs=[
                {"code": "DES-01", "rel": "drives"},
                {"code": "RISK-01", "rel": "relates"},
            ],
        )
        f2 = make_fact(code="DES-01")
        f3 = make_fact(code="RISK-01", layer="GUARDRAILS", type="Risk Assessment Finding")
        index = self._build_index(yaml_store, [f1, f2, f3])
        # Only follow "drives" edges
        result = index.neighborhood({"ADR-01"}, max_depth=1, edge_types=[EdgeType.DRIVES])
        assert "DES-01" in result
        assert "RISK-01" not in result

    def test_cycle_handling(self, yaml_store: YamlFileStore):
        """Cycles don't cause infinite loops."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01", refs=["ADR-01"])
        index = self._build_index(yaml_store, [f1, f2])
        result = index.neighborhood({"ADR-01"}, max_depth=-1)
        assert set(result.keys()) == {"ADR-01", "DES-01"}

    def test_multiple_seeds(self, yaml_store: YamlFileStore):
        """Multiple seeds expand from all starting points."""
        f1 = make_fact(code="ADR-01", refs=["DES-01"])
        f2 = make_fact(code="DES-01")
        f3 = make_fact(code="ADR-02", refs=["SP-01"])
        f4 = make_fact(code="SP-01", layer="HOW", type="System Prompt Rule")
        index = self._build_index(yaml_store, [f1, f2, f3, f4])
        result = index.neighborhood({"ADR-01", "ADR-02"}, max_depth=1)
        assert set(result.keys()) == {"ADR-01", "ADR-02", "DES-01", "SP-01"}

    def test_nonexistent_ref_target_skipped(self, yaml_store: YamlFileStore):
        """Refs pointing to non-existent facts are skipped gracefully."""
        f1 = make_fact(code="ADR-01", refs=["MISSING-01"])
        index = self._build_index(yaml_store, [f1])
        result = index.neighborhood({"ADR-01"}, max_depth=1)
        assert result == {"ADR-01": 0}
