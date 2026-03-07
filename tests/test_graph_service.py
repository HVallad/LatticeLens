"""Tests for graph_service — impact analysis, orphan detection, contradictions."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.models import Fact, FactLayer, FactStatus
from lattice_lens.services.graph_service import (
    find_contradiction_candidates,
    find_orphans,
    impact_analysis,
    load_role_templates,
)
from lattice_lens.store.index import FactIndex

from conftest import make_fact

yaml_rw = YAML()
yaml_rw.default_flow_style = False


def _build_index_from_facts(facts: list[Fact], tmp_path: Path) -> FactIndex:
    """Write facts to a temp dir and build an index."""
    facts_dir = tmp_path / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    for fact in facts:
        with open(facts_dir / f"{fact.code}.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)
    return FactIndex.build(facts_dir)


class TestImpactAnalysis:
    def test_impact_direct(self, seeded_store):
        """Changing ADR-03 should surface MC-01 and RISK-07 (they ref ADR-03)."""
        index = FactIndex.build(seeded_store.root / "facts")
        result = impact_analysis(index, "ADR-03")

        assert "MC-01" in result.directly_affected
        assert "RISK-07" in result.directly_affected
        assert "ADR-03" not in result.directly_affected

    def test_impact_transitive(self, seeded_store):
        """Changing ADR-01 should find transitive facts beyond direct refs."""
        index = FactIndex.build(seeded_store.root / "facts")
        result = impact_analysis(index, "ADR-01", max_depth=3)

        # Direct: PRD-01, DES-01, API-01 (they reference ADR-01)
        assert "PRD-01" in result.directly_affected
        assert "DES-01" in result.directly_affected
        assert "API-01" in result.directly_affected

        # Transitive: facts that reference the direct ones
        # ADR-03 refs PRD-01, so ADR-03 is transitive from PRD-01
        # MON-01 refs PRD-01, so MON-01 is transitive
        # RUN-01 refs DES-01, so RUN-01 is transitive
        assert len(result.transitively_affected) > 0
        assert len(result.all_affected) > len(result.directly_affected)

    def test_impact_respects_max_depth(self, seeded_store):
        """depth=1 should return only direct, no transitive."""
        index = FactIndex.build(seeded_store.root / "facts")
        result = impact_analysis(index, "ADR-01", max_depth=1)

        assert len(result.directly_affected) > 0
        assert len(result.transitively_affected) == 0
        assert result.depth_reached == 1

    def test_impact_no_self_reference(self, seeded_store):
        """Source code should not appear in its own affected list."""
        index = FactIndex.build(seeded_store.root / "facts")
        result = impact_analysis(index, "ADR-01")

        assert "ADR-01" not in result.directly_affected
        assert "ADR-01" not in result.transitively_affected
        assert "ADR-01" not in result.all_affected

    def test_impact_cycle_safe(self, tmp_path):
        """Circular refs should not cause infinite loop."""
        facts = [
            make_fact(code="ADR-01", refs=["ADR-02"]),
            make_fact(code="ADR-02", refs=["ADR-03"]),
            make_fact(
                code="ADR-03",
                refs=["ADR-01"],  # creates a cycle
            ),
        ]
        index = _build_index_from_facts(facts, tmp_path)
        # Should complete without hanging
        result = impact_analysis(index, "ADR-01", max_depth=10)
        assert result.source_code == "ADR-01"

    def test_impact_nonexistent_code(self, seeded_store):
        """Impact analysis on a code with no reverse refs returns empty."""
        index = FactIndex.build(seeded_store.root / "facts")
        result = impact_analysis(index, "SP-01")
        # SP-01 is not referenced by any seed fact
        assert len(result.directly_affected) == 0

    def test_affected_roles(self, seeded_store):
        """Changing a WHY/ADR fact should show planning and architecture roles affected."""
        index = FactIndex.build(seeded_store.root / "facts")
        role_templates = {
            "planning": {
                "name": "Planning Agent",
                "query": {
                    "layers": ["WHY"],
                    "types": ["Architecture Decision Record", "Product Requirement"],
                    "extra": [],
                },
            },
            "architecture": {
                "name": "Architecture Agent",
                "query": {
                    "layers": ["WHY", "GUARDRAILS"],
                    "types": [
                        "Architecture Decision Record",
                        "Design Proposal Decision",
                        "Risk Assessment Finding",
                    ],
                    "extra": [],
                },
            },
            "deploy": {
                "name": "Deploy Agent",
                "query": {
                    "layers": ["HOW"],
                    "types": ["Runbook Procedure"],
                    "extra": [],
                },
            },
        }
        result = impact_analysis(index, "ADR-03", role_templates=role_templates)

        # ADR-03 is WHY/ADR, MC-01 is GUARDRAILS/Model Card, RISK-07 is GUARDRAILS/Risk
        # planning matches ADR-03 (WHY + ADR type)
        assert "planning" in result.affected_roles
        # architecture matches ADR-03 (WHY) and RISK-07 (GUARDRAILS + Risk Assessment)
        assert "architecture" in result.affected_roles


class TestFindOrphans:
    def test_orphan_detection(self, tmp_path):
        """Facts with no refs in or out should be detected as orphans."""
        facts = [
            make_fact(code="ADR-01", refs=["ADR-02"]),
            make_fact(code="ADR-02", refs=[]),  # has inbound from ADR-01
            make_fact(code="ADR-03", refs=[]),  # no inbound, no outbound → orphan
        ]
        index = _build_index_from_facts(facts, tmp_path)
        orphans = find_orphans(index)

        assert "ADR-03" in orphans
        assert "ADR-01" not in orphans  # has outbound
        assert "ADR-02" not in orphans  # has inbound

    def test_orphan_excludes_connected(self, seeded_store):
        """Seed facts all have refs, so none should be orphans."""
        index = FactIndex.build(seeded_store.root / "facts")
        orphans = find_orphans(index)

        # All 12 seed facts have outbound refs
        assert len(orphans) == 0

    def test_orphan_empty_index(self, tmp_path):
        """Empty index returns no orphans."""
        facts_dir = tmp_path / "facts"
        facts_dir.mkdir(parents=True)
        index = FactIndex.build(facts_dir)
        assert find_orphans(index) == []


class TestContradictionCandidates:
    def test_contradiction_candidates(self, tmp_path):
        """Two active facts sharing 2+ tags in different layers should be flagged."""
        facts = [
            make_fact(
                code="ADR-01",
                layer=FactLayer.WHY,
                tags=["security", "compliance"],
                owner="team-a",
            ),
            make_fact(
                code="RISK-01",
                layer=FactLayer.GUARDRAILS,
                type="Risk Assessment Finding",
                tags=["security", "compliance"],
                owner="team-b",
            ),
        ]
        index = _build_index_from_facts(facts, tmp_path)
        candidates = find_contradiction_candidates(index)

        assert len(candidates) == 1
        a, b, shared = candidates[0]
        assert {a, b} == {"ADR-01", "RISK-01"}
        assert "security" in shared
        assert "compliance" in shared

    def test_no_contradictions_same_layer_and_owner(self, tmp_path):
        """Facts in the same layer with same owner should not be flagged."""
        facts = [
            make_fact(
                code="ADR-01",
                tags=["security", "compliance"],
                owner="team-a",
            ),
            make_fact(
                code="ADR-02",
                tags=["security", "compliance"],
                owner="team-a",
            ),
        ]
        index = _build_index_from_facts(facts, tmp_path)
        candidates = find_contradiction_candidates(index)
        assert len(candidates) == 0

    def test_contradiction_respects_min_tags(self, tmp_path):
        """Should not flag pairs with fewer shared tags than min_shared_tags."""
        facts = [
            make_fact(
                code="ADR-01",
                layer=FactLayer.WHY,
                tags=["security", "other"],
                owner="team-a",
            ),
            make_fact(
                code="RISK-01",
                layer=FactLayer.GUARDRAILS,
                type="Risk Assessment Finding",
                tags=["security", "different"],
                owner="team-b",
            ),
        ]
        index = _build_index_from_facts(facts, tmp_path)

        # min_shared_tags=2: only 1 shared tag ("security"), should not flag
        candidates = find_contradiction_candidates(index, min_shared_tags=2)
        assert len(candidates) == 0

        # min_shared_tags=1: should flag
        candidates = find_contradiction_candidates(index, min_shared_tags=1)
        assert len(candidates) == 1

    def test_contradiction_ignores_non_active(self, tmp_path):
        """Only Active facts should be considered."""
        facts = [
            make_fact(
                code="ADR-01",
                layer=FactLayer.WHY,
                tags=["security", "compliance"],
                status=FactStatus.DEPRECATED,
            ),
            make_fact(
                code="RISK-01",
                layer=FactLayer.GUARDRAILS,
                type="Risk Assessment Finding",
                tags=["security", "compliance"],
            ),
        ]
        index = _build_index_from_facts(facts, tmp_path)
        candidates = find_contradiction_candidates(index)
        assert len(candidates) == 0


class TestLoadRoleTemplates:
    def test_load_new_format(self, tmp_path):
        """Should load Phase 2 nested query format."""
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        template = {
            "name": "Test Agent",
            "description": "Test",
            "query": {
                "layers": ["WHY"],
                "types": ["Architecture Decision Record"],
                "extra": [],
            },
        }
        with open(roles_dir / "test.yaml", "w") as f:
            yaml_rw.dump(template, f)

        templates = load_role_templates(roles_dir)
        assert "test" in templates
        assert "query" in templates["test"]

    def test_load_old_format_warns(self, tmp_path, capsys):
        """Should emit a warning for Phase 1 flat format."""
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        template = {
            "name": "Test Agent",
            "layers": ["WHY"],
            "tags": ["architecture"],
            "max_facts": 20,
        }
        with open(roles_dir / "test.yaml", "w") as f:
            yaml_rw.dump(template, f)

        templates = load_role_templates(roles_dir)
        assert "test" in templates
        captured = capsys.readouterr()
        assert "v0.1.0 format" in captured.err

    def test_load_empty_dir(self, tmp_path):
        """Empty roles dir returns empty dict."""
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        assert load_role_templates(roles_dir) == {}

    def test_load_nonexistent_dir(self, tmp_path):
        """Nonexistent dir returns empty dict."""
        assert load_role_templates(tmp_path / "nope") == {}
