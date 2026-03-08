"""Tests for MCP tool logic functions (no MCP server dependency)."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from tests.conftest import make_fact
from lattice_lens.config import ROLES_DIR
from lattice_lens.mcp.tools import (
    tool_all_codes,
    tool_context_assemble,
    tool_fact_create,
    tool_fact_deprecate,
    tool_fact_exists,
    tool_fact_get,
    tool_fact_list,
    tool_fact_promote,
    tool_fact_query,
    tool_fact_update,
    tool_graph_contradictions,
    tool_graph_impact,
    tool_graph_orphans,
    tool_lattice_status,
    tool_lattice_validate,
)
from lattice_lens.models import FactStatus

yaml_rw = YAML()
yaml_rw.default_flow_style = False


def _write_role_templates(roles_dir: Path):
    """Write standard role templates for testing."""
    roles_dir.mkdir(parents=True, exist_ok=True)
    templates = {
        "planning": {
            "name": "Planning Agent",
            "query": {
                "layers": ["WHY"],
                "types": ["Architecture Decision Record", "Product Requirement"],
                "tags": ["architecture"],
                "extra": [
                    {"layer": "GUARDRAILS", "types": ["Acceptable Use Policy Rule"]},
                ],
            },
        },
        "implementation": {
            "name": "Implementation Agent",
            "query": {
                "layers": ["HOW", "GUARDRAILS"],
                "types": ["API Specification", "System Prompt Rule", "Data Governance Rule"],
                "tags": ["api"],
                "extra": [],
            },
        },
    }
    for name, data in templates.items():
        with open(roles_dir / f"{name}.yaml", "w") as f:
            yaml_rw.dump(data, f)


class TestFactGet:
    def test_existing(self, seeded_store):
        result = tool_fact_get(seeded_store, "ADR-01")
        assert result["code"] == "ADR-01"
        assert result["layer"] == "WHY"
        assert "error" not in result

    def test_missing(self, seeded_store):
        result = tool_fact_get(seeded_store, "NOPE-99")
        assert "error" in result
        assert "not found" in result["error"]


class TestFactQuery:
    def test_by_layer(self, seeded_store):
        results = tool_fact_query(seeded_store, layer="WHY")
        assert len(results) > 0
        for r in results:
            assert r["layer"] == "WHY"

    def test_by_tags(self, seeded_store):
        results = tool_fact_query(seeded_store, tags=["architecture"])
        assert len(results) > 0
        for r in results:
            assert "architecture" in r["tags"]

    def test_empty_result(self, seeded_store):
        results = tool_fact_query(seeded_store, tags=["nonexistent-tag-xyz"])
        assert results == []


class TestFactList:
    def test_default_excludes_deprecated(self, yaml_store):
        active = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        deprecated = make_fact(code="ADR-02", status=FactStatus.DEPRECATED)
        yaml_store.create(active)
        yaml_store.create(deprecated)

        results = tool_fact_list(yaml_store)
        codes = [r["code"] for r in results]
        assert "ADR-01" in codes
        assert "ADR-02" not in codes

    def test_filter_by_layer(self, seeded_store):
        results = tool_fact_list(seeded_store, layer="GUARDRAILS")
        for r in results:
            assert r["layer"] == "GUARDRAILS"

    def test_summary_fields(self, seeded_store):
        results = tool_fact_list(seeded_store)
        assert len(results) > 0
        for r in results:
            assert "code" in r
            assert "layer" in r
            assert "type" in r
            assert "status" in r
            assert "tags" in r
            assert "version" in r


class TestContextAssemble:
    def test_planning_role(self, seeded_store):
        roles_dir = seeded_store.root / ROLES_DIR
        _write_role_templates(roles_dir)
        result = tool_context_assemble(seeded_store, roles_dir, "planning")

        assert result["role"] == "planning"
        assert len(result["facts"]) > 0
        assert "budget" in result
        assert "error" not in result

    def test_with_budget(self, seeded_store):
        roles_dir = seeded_store.root / ROLES_DIR
        _write_role_templates(roles_dir)

        # Very small budget should limit results
        result = tool_context_assemble(seeded_store, roles_dir, "planning", budget=50)
        # With a budget of 50 tokens, we should get fewer facts than unlimited
        unlimited = tool_context_assemble(seeded_store, roles_dir, "planning", budget=40_000)
        assert len(result["facts"]) <= len(unlimited["facts"])

    def test_unknown_role(self, seeded_store):
        roles_dir = seeded_store.root / ROLES_DIR
        _write_role_templates(roles_dir)
        result = tool_context_assemble(seeded_store, roles_dir, "nonexistent")
        assert "error" in result


class TestGraphImpact:
    def test_returns_affected(self, seeded_store):
        roles_dir = seeded_store.root / ROLES_DIR
        _write_role_templates(roles_dir)
        result = tool_graph_impact(seeded_store, roles_dir, "ADR-03")

        assert result["source"] == "ADR-03"
        assert isinstance(result["directly_affected"], list)
        assert "error" not in result

    def test_nonexistent_code(self, seeded_store):
        roles_dir = seeded_store.root / ROLES_DIR
        result = tool_graph_impact(seeded_store, roles_dir, "NOPE-99")
        assert "error" in result


class TestGraphOrphans:
    def test_returns_codes(self, yaml_store):
        orphan = make_fact(code="ADR-01", refs=[])
        yaml_store.create(orphan)
        result = tool_graph_orphans(yaml_store)
        assert "ADR-01" in result


class TestLatticeStatus:
    def test_returns_counts(self, seeded_store):
        result = tool_lattice_status(seeded_store)
        assert "total" in result
        assert result["total"] > 0
        assert "by_layer" in result
        assert "by_status" in result
        assert "stale" in result
        assert "backend" in result


class TestWriteTools:
    def test_fact_create(self, yaml_store):
        data = {
            "code": "ADR-01",
            "layer": "WHY",
            "type": "Architecture Decision Record",
            "fact": "This is a test fact for creation via MCP tool.",
            "tags": ["test", "mcp"],
            "owner": "test-team",
        }
        result = tool_fact_create(yaml_store, data)
        assert result["code"] == "ADR-01"
        assert "error" not in result
        # Verify it's persisted
        assert yaml_store.exists("ADR-01")

    def test_fact_create_duplicate(self, yaml_store):
        data = {
            "code": "ADR-01",
            "layer": "WHY",
            "type": "Architecture Decision Record",
            "fact": "This is a test fact for creation.",
            "tags": ["test", "mcp"],
            "owner": "test-team",
        }
        tool_fact_create(yaml_store, data)
        result = tool_fact_create(yaml_store, data)
        assert "error" in result

    def test_fact_update(self, yaml_store):
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)

        result = tool_fact_update(
            yaml_store, "ADR-01", {"fact": "Updated fact text for testing."}, "test update"
        )
        assert result["fact"] == "Updated fact text for testing."
        assert result["version"] == 2
        assert "error" not in result

    def test_fact_deprecate(self, yaml_store):
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)

        result = tool_fact_deprecate(yaml_store, "ADR-01", "no longer needed")
        assert result["status"] == "Deprecated"
        assert "error" not in result


class TestFactPromote:
    def test_draft_to_under_review(self, yaml_store):
        fact = make_fact(code="ADR-01", status=FactStatus.DRAFT)
        yaml_store.create(fact)

        result = tool_fact_promote(yaml_store, "ADR-01", "ready for review")
        assert result["status"] == "Under Review"
        assert result["confidence"] == "Provisional"
        assert "error" not in result

    def test_under_review_to_active(self, yaml_store):
        fact = make_fact(code="ADR-01", status=FactStatus.UNDER_REVIEW)
        yaml_store.create(fact)

        result = tool_fact_promote(yaml_store, "ADR-01", "approved")
        assert result["status"] == "Active"
        assert result["confidence"] == "Confirmed"
        assert "error" not in result

    def test_already_active(self, yaml_store):
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        result = tool_fact_promote(yaml_store, "ADR-01", "try again")
        assert "error" in result

    def test_nonexistent(self, yaml_store):
        result = tool_fact_promote(yaml_store, "NOPE-99", "ghost")
        assert "error" in result


class TestGraphContradictions:
    def test_finds_pairs(self, yaml_store):
        # Two facts in different layers sharing tags → contradiction candidate
        f1 = make_fact(
            code="ADR-01", layer="WHY", tags=["security", "validation"], status=FactStatus.ACTIVE
        )
        f2 = make_fact(
            code="AUP-01",
            layer="GUARDRAILS",
            tags=["security", "validation"],
            status=FactStatus.ACTIVE,
        )
        yaml_store.create(f1)
        yaml_store.create(f2)

        results = tool_graph_contradictions(yaml_store, min_shared_tags=2)
        assert len(results) > 0
        pair = results[0]
        assert "fact_a" in pair
        assert "fact_b" in pair
        assert "shared_tags" in pair

    def test_empty_when_no_overlaps(self, yaml_store):
        f1 = make_fact(code="ADR-01", layer="WHY", tags=["alpha", "beta"])
        f2 = make_fact(code="AUP-01", layer="GUARDRAILS", tags=["gamma", "delta"])
        yaml_store.create(f1)
        yaml_store.create(f2)

        results = tool_graph_contradictions(yaml_store, min_shared_tags=2)
        assert results == []


class TestLatticeValidate:
    def test_clean_lattice(self, seeded_store):
        result = tool_lattice_validate(seeded_store)
        assert result["ok"] is True
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)

    def test_missing_facts_dir(self, yaml_store):
        # Point at a non-existent facts dir
        import shutil

        shutil.rmtree(yaml_store.facts_dir)
        result = tool_lattice_validate(yaml_store)
        assert result["ok"] is False
        assert len(result["errors"]) > 0


class TestFactExists:
    def test_found(self, seeded_store):
        result = tool_fact_exists(seeded_store, "ADR-01")
        assert result["code"] == "ADR-01"
        assert result["exists"] is True

    def test_missing(self, seeded_store):
        result = tool_fact_exists(seeded_store, "ZZZ-99")
        assert result["code"] == "ZZZ-99"
        assert result["exists"] is False


class TestAllCodes:
    def test_returns_all(self, seeded_store):
        result = tool_all_codes(seeded_store)
        assert isinstance(result, list)
        assert len(result) > 0
        assert "ADR-01" in result

    def test_empty_store(self, yaml_store):
        result = tool_all_codes(yaml_store)
        assert result == []
