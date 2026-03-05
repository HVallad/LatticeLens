"""Tests for governance evaluation service."""

from __future__ import annotations

from pathlib import Path

import pytest

from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus
from lattice_lens.services.evaluate_service import (
    EvaluationResult,
    HookInput,
    evaluate_governance,
    parse_hook_input,
)
from tests.conftest import make_fact


# ---------------------------------------------------------------------------
# parse_hook_input
# ---------------------------------------------------------------------------


class TestParseHookInput:
    def test_valid_json(self):
        data = (
            '{"session_id": "abc", "cwd": "/tmp/proj", '
            '"hook_event_name": "UserPromptSubmit", "prompt": "fix bug"}'
        )
        result = parse_hook_input(data)
        assert result is not None
        assert result.session_id == "abc"
        assert result.cwd == "/tmp/proj"
        assert result.hook_event_name == "UserPromptSubmit"
        assert result.prompt == "fix bug"

    def test_empty_string(self):
        assert parse_hook_input("") is None

    def test_whitespace_only(self):
        assert parse_hook_input("   \n  ") is None

    def test_invalid_json(self):
        assert parse_hook_input("not json at all") is None

    def test_partial_fields(self):
        result = parse_hook_input('{"cwd": "/tmp"}')
        assert result is not None
        assert result.cwd == "/tmp"
        assert result.session_id == ""
        assert result.prompt == ""

    def test_none_input(self):
        assert parse_hook_input(None) is None


# ---------------------------------------------------------------------------
# evaluate_governance
# ---------------------------------------------------------------------------


class TestEvaluateGovernance:
    def test_no_lattice_returns_empty(self, tmp_path: Path):
        result = evaluate_governance(start_path=tmp_path)
        assert result.lattice_found is False
        assert result.guardrails == []
        assert result.has_governance is False
        assert result.knowledge_summary == {}
        assert result.available_roles == []

    def test_empty_lattice_returns_no_facts(self, tmp_lattice: Path):
        result = evaluate_governance(start_path=tmp_lattice.parent)
        assert result.lattice_found is True
        assert result.guardrails == []
        assert result.has_governance is False

    def test_loads_active_guardrails(self, yaml_store):
        aup = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            tags=["policy", "test"],
        )
        dg = make_fact(
            code="DG-01",
            layer=FactLayer.GUARDRAILS,
            type="Data Governance Rule",
            status=FactStatus.ACTIVE,
            tags=["governance", "test"],
        )
        yaml_store.create(aup)
        yaml_store.create(dg)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert result.lattice_found is True
        assert result.has_governance is True
        assert len(result.guardrails) == 2

    def test_excludes_draft_guardrails(self, yaml_store):
        active = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            tags=["policy", "test"],
        )
        draft = make_fact(
            code="AUP-02",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.DRAFT,
            tags=["policy", "test"],
        )
        yaml_store.create(active)
        yaml_store.create(draft)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert len(result.guardrails) == 1
        assert result.guardrails[0].code == "AUP-01"

    def test_excludes_deprecated_guardrails(self, yaml_store):
        active = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            tags=["policy", "test"],
        )
        deprecated = make_fact(
            code="AUP-02",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.DEPRECATED,
            tags=["policy", "test"],
        )
        yaml_store.create(active)
        yaml_store.create(deprecated)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert len(result.guardrails) == 1

    def test_excludes_non_guardrails_from_rules(self, yaml_store):
        aup = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            tags=["policy", "test"],
        )
        adr = make_fact(
            code="ADR-01",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            status=FactStatus.ACTIVE,
            tags=["architecture", "test"],
        )
        yaml_store.create(aup)
        yaml_store.create(adr)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        # Only GUARDRAILS in the rules list
        assert len(result.guardrails) == 1
        assert result.guardrails[0].code == "AUP-01"

    def test_confirmed_before_provisional(self, yaml_store):
        provisional = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.PROVISIONAL,
            tags=["policy", "test"],
        )
        confirmed = make_fact(
            code="AUP-02",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            tags=["policy", "test"],
        )
        yaml_store.create(provisional)
        yaml_store.create(confirmed)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert result.guardrails[0].code == "AUP-02"  # Confirmed first
        assert result.guardrails[1].code == "AUP-01"

    def test_token_estimation_positive(self, yaml_store):
        aup = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            tags=["policy", "test"],
        )
        yaml_store.create(aup)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert result.total_tokens > 0

    def test_knowledge_summary_counts_why_how(self, yaml_store):
        """WHY and HOW facts should appear in knowledge_summary."""
        adr = make_fact(
            code="ADR-01",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            status=FactStatus.ACTIVE,
            tags=["architecture", "test"],
        )
        sp = make_fact(
            code="SP-01",
            layer=FactLayer.HOW,
            type="Solution Pattern",
            status=FactStatus.ACTIVE,
            tags=["pattern", "test"],
        )
        yaml_store.create(adr)
        yaml_store.create(sp)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert "WHY" in result.knowledge_summary
        assert result.knowledge_summary["WHY"]["Architecture Decision Record"] == 1
        assert "HOW" in result.knowledge_summary
        assert result.knowledge_summary["HOW"]["Solution Pattern"] == 1

    def test_knowledge_summary_excludes_draft_facts(self, yaml_store):
        """Draft WHY/HOW facts should not be counted in the summary."""
        active_adr = make_fact(
            code="ADR-01",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            status=FactStatus.ACTIVE,
            tags=["architecture", "test"],
        )
        draft_adr = make_fact(
            code="ADR-02",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            status=FactStatus.DRAFT,
            tags=["architecture", "test"],
        )
        yaml_store.create(active_adr)
        yaml_store.create(draft_adr)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert result.knowledge_summary["WHY"]["Architecture Decision Record"] == 1

    def test_knowledge_summary_excludes_guardrails(self, yaml_store):
        """GUARDRAILS facts should NOT appear in knowledge_summary."""
        aup = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            tags=["policy", "test"],
        )
        yaml_store.create(aup)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert "GUARDRAILS" not in result.knowledge_summary

    def test_available_roles_populated(self, yaml_store):
        """Roles from .lattice/roles/ should appear in the result."""
        from ruamel.yaml import YAML

        yaml_rw = YAML()
        roles_dir = yaml_store.root / "roles"
        roles_dir.mkdir(exist_ok=True)
        with open(roles_dir / "planning.yaml", "w") as f:
            yaml_rw.dump(
                {
                    "name": "Planning Agent",
                    "description": "Test",
                    "query": {
                        "layers": ["WHY"],
                        "types": [],
                        "tags": [],
                        "max_facts": 10,
                        "extra": [],
                    },
                },
                f,
            )

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert "planning" in result.available_roles

    def test_available_roles_empty_when_no_roles_dir(self, yaml_store):
        """No roles directory should yield an empty roles list."""
        import shutil

        roles_dir = yaml_store.root / "roles"
        if roles_dir.exists():
            shutil.rmtree(roles_dir)

        result = evaluate_governance(start_path=yaml_store.root.parent)
        assert result.available_roles == []


# ---------------------------------------------------------------------------
# EvaluationResult rendering
# ---------------------------------------------------------------------------


class TestEvaluationResultRendering:
    def test_render_briefing_with_guardrails(self):
        fact = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            tags=["policy", "test"],
        )
        result = EvaluationResult(
            lattice_found=True,
            guardrails=[fact],
            total_tokens=50,
        )
        text = result.render_briefing()
        assert "Governance Briefing" in text
        assert "AUP-01" in text
        assert "You MUST follow" in text
        assert "Mandatory Rules" in text

    def test_render_briefing_includes_conflict_directive(self):
        """The briefing must tell the agent to raise conflicts before proceeding."""
        fact = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            tags=["policy", "test"],
        )
        result = EvaluationResult(
            lattice_found=True,
            guardrails=[fact],
            total_tokens=50,
        )
        text = result.render_briefing()
        assert "raise the conflict" in text
        assert "cite the specific rule code" in text
        assert "Ask the user" in text

    def test_render_briefing_includes_knowledge_section(self):
        result = EvaluationResult(
            lattice_found=True,
            guardrails=[],
            knowledge_summary={
                "WHY": {"Architecture Decision Record": 3},
                "HOW": {"Solution Pattern": 2},
            },
            available_roles=["planning", "implementation"],
        )
        text = result.render_briefing()
        assert "Project Knowledge Available" in text
        assert "3 Architecture Decision Records" in text
        assert "2 Solution Patterns" in text
        assert "lattice context planning" in text
        assert "lattice context implementation" in text

    def test_render_briefing_includes_role_hints(self):
        result = EvaluationResult(
            lattice_found=True,
            guardrails=[],
            knowledge_summary={"WHY": {"Product Requirement": 1}},
            available_roles=["architecture", "qa", "deploy"],
        )
        text = result.render_briefing()
        assert "design decisions" in text
        assert "testing/QA" in text
        assert "deployment" in text

    def test_render_briefing_empty_when_no_lattice(self):
        result = EvaluationResult(lattice_found=False)
        assert result.render_briefing() == ""

    def test_render_briefing_empty_when_no_content(self):
        result = EvaluationResult(lattice_found=True)
        assert result.render_briefing() == ""

    def test_render_briefing_singular_count(self):
        result = EvaluationResult(
            lattice_found=True,
            knowledge_summary={"WHY": {"Product Requirement": 1}},
        )
        text = result.render_briefing()
        assert "1 Product Requirement" in text
        # Should NOT have trailing 's' for count=1
        assert "1 Product Requirements" not in text

    def test_to_dict_structure(self):
        fact = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            tags=["policy", "test"],
        )
        result = EvaluationResult(
            lattice_found=True,
            guardrails=[fact],
            total_tokens=50,
            lattice_root="/tmp/.lattice",
            knowledge_summary={"WHY": {"Architecture Decision Record": 2}},
            available_roles=["planning"],
        )
        d = result.to_dict()
        assert d["lattice_found"] is True
        assert d["guardrails_count"] == 1
        assert d["guardrails"][0]["code"] == "AUP-01"
        assert "version" in d["guardrails"][0]
        assert d["knowledge_summary"]["WHY"]["Architecture Decision Record"] == 2
        assert d["available_roles"] == ["planning"]

    def test_to_dict_no_lattice(self):
        result = EvaluationResult()
        d = result.to_dict()
        assert d["lattice_found"] is False
        assert d["guardrails_count"] == 0
        assert d["guardrails"] == []
        assert d["knowledge_summary"] == {}
        assert d["available_roles"] == []

    def test_footer_includes_counts(self):
        result = EvaluationResult(
            lattice_found=True,
            guardrails=[
                make_fact(
                    code="AUP-01",
                    layer=FactLayer.GUARDRAILS,
                    type="Acceptable Use Policy Rule",
                    tags=["policy", "test"],
                )
            ],
            knowledge_summary={
                "WHY": {"Architecture Decision Record": 5},
                "HOW": {"Solution Pattern": 3},
            },
            available_roles=["planning", "implementation"],
        )
        text = result.render_briefing()
        assert "1 guardrails" in text
        assert "5 WHY facts" in text
        assert "3 HOW facts" in text
        assert "2 roles" in text
