"""Tests for context assembly service."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lattice_lens.models import FactConfidence, FactLayer, FactStatus
from lattice_lens.services.context_service import (
    ContextResult,
    assemble_context,
    estimate_fact_tokens,
    estimate_tokens,
)
from lattice_lens.store.index import FactIndex
from tests.conftest import make_fact


def _build_index(facts: list) -> FactIndex:
    """Build a FactIndex from a list of facts without writing to disk."""
    idx = FactIndex()
    for f in facts:
        idx._add(f)
    return idx


class TestTokenEstimation:
    def test_estimate_tokens_basic(self):
        # ~4 chars per token
        assert estimate_tokens("a" * 100) == 25
        assert estimate_tokens("a" * 4) == 1
        assert estimate_tokens("") == 1  # min 1

    def test_estimate_fact_tokens(self):
        fact = make_fact(fact="x" * 400)
        tokens = estimate_fact_tokens(fact)
        assert tokens > 100  # 400 chars of text alone = 100 tokens
        assert tokens < 200  # metadata adds some, but not too much


class TestContextAssembly:
    """Test the assemble_context function."""

    def _make_role_template(self, **overrides):
        defaults = {
            "name": "Test Agent",
            "description": "Test role",
            "query": {
                "layers": ["WHY"],
                "types": ["Architecture Decision Record"],
                "tags": ["architecture"],
                "max_facts": 50,
                "extra": [],
            },
        }
        defaults.update(overrides)
        return defaults

    def test_basic_assembly(self):
        """Facts matching role query are loaded."""
        facts = [
            make_fact(code="ADR-01", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
            make_fact(code="ADR-02", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 2

    def test_draft_excluded(self):
        """Draft facts are never included in context assembly."""
        facts = [
            make_fact(code="ADR-01", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
            make_fact(code="ADR-02", status=FactStatus.DRAFT, tags=["architecture", "test"]),
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 1
        assert result.loaded_facts[0].code == "ADR-01"

    def test_deprecated_excluded(self):
        """Deprecated facts are never included."""
        facts = [
            make_fact(code="ADR-01", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
            make_fact(code="ADR-02", status=FactStatus.DEPRECATED, tags=["architecture", "test"]),
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 1

    def test_superseded_excluded(self):
        """Superseded facts are never included."""
        facts = [
            make_fact(code="ADR-01", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
            make_fact(
                code="ADR-02",
                status=FactStatus.SUPERSEDED,
                superseded_by="ADR-03",
                tags=["architecture", "test"],
            ),
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 1

    def test_under_review_included_as_provisional(self):
        """Under Review facts are included with Provisional confidence."""
        facts = [
            make_fact(
                code="ADR-01",
                status=FactStatus.UNDER_REVIEW,
                confidence=FactConfidence.PROVISIONAL,
                tags=["architecture", "test"],
            ),
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 1
        assert result.loaded_facts[0].confidence == FactConfidence.PROVISIONAL

    def test_priority_loading_confirmed_first(self):
        """Confirmed facts load before Provisional facts."""
        facts = [
            make_fact(
                code="ADR-01",
                status=FactStatus.ACTIVE,
                confidence=FactConfidence.PROVISIONAL,
                tags=["architecture", "test"],
            ),
            make_fact(
                code="ADR-02",
                status=FactStatus.ACTIVE,
                confidence=FactConfidence.CONFIRMED,
                tags=["architecture", "test"],
            ),
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 2
        # Confirmed should come first
        assert result.loaded_facts[0].confidence == FactConfidence.CONFIRMED
        assert result.loaded_facts[1].confidence == FactConfidence.PROVISIONAL

    def test_tag_match_score_sorting(self):
        """Within same confidence tier, facts with more tag matches rank higher."""
        facts = [
            make_fact(
                code="ADR-01",
                status=FactStatus.ACTIVE,
                tags=["scaling", "test"],  # no match with role tags
            ),
            make_fact(
                code="ADR-02",
                status=FactStatus.ACTIVE,
                tags=["architecture", "test"],  # 1 match
            ),
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert result.loaded_facts[0].code == "ADR-02"  # higher tag match
        assert result.loaded_facts[1].code == "ADR-01"

    def test_token_budget_respected(self):
        """Budget limits how many facts are loaded."""
        facts = [
            make_fact(code=f"ADR-{i:02d}", status=FactStatus.ACTIVE, tags=["architecture", "test"])
            for i in range(1, 11)
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        # Very small budget — should only load a few facts
        result = assemble_context(index, "test", template, budget=200)
        assert len(result.loaded_facts) < 10
        assert result.budget_exhausted is True
        assert result.total_tokens <= 200

    def test_no_budget_loads_all(self):
        """Without budget, all matching facts are loaded."""
        facts = [
            make_fact(code=f"ADR-{i:02d}", status=FactStatus.ACTIVE, tags=["architecture", "test"])
            for i in range(1, 6)
        ]
        index = _build_index(facts)
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 5
        assert result.budget_exhausted is False

    def test_max_facts_from_template(self):
        """max_facts in role template limits fact count."""
        facts = [
            make_fact(code=f"ADR-{i:02d}", status=FactStatus.ACTIVE, tags=["architecture", "test"])
            for i in range(1, 11)
        ]
        index = _build_index(facts)
        template = self._make_role_template(
            query={
                "layers": ["WHY"],
                "types": ["Architecture Decision Record"],
                "tags": ["architecture"],
                "max_facts": 3,
                "extra": [],
            }
        )

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 3

    def test_ref_pointers_for_excluded(self):
        """Facts cut by budget appear in ref_pointers."""
        facts = [
            make_fact(code="ADR-01", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
            make_fact(code="ADR-02", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
            make_fact(code="ADR-03", status=FactStatus.ACTIVE, tags=["architecture", "test"]),
        ]
        index = _build_index(facts)
        template = self._make_role_template(
            query={
                "layers": ["WHY"],
                "types": ["Architecture Decision Record"],
                "tags": ["architecture"],
                "max_facts": 1,
                "extra": [],
            }
        )

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 1
        assert len(result.ref_pointers) == 2  # 2 excluded facts

    def test_ref_pointers_from_loaded_refs(self):
        """Refs from loaded facts that point outside loaded set appear in pointers."""
        risk_fact = make_fact(
            code="RISK-01",
            layer=FactLayer.GUARDRAILS,
            type="Risk Assessment Finding",
            status=FactStatus.ACTIVE,
            tags=["risk", "test"],
        )
        adr_fact = make_fact(
            code="ADR-01",
            status=FactStatus.ACTIVE,
            tags=["architecture", "test"],
            refs=["RISK-01"],
        )
        index = _build_index([risk_fact, adr_fact])
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        # Only ADR-01 should be loaded (RISK-01 doesn't match WHY/ADR query)
        assert len(result.loaded_facts) == 1
        assert result.loaded_facts[0].code == "ADR-01"
        # RISK-01 should appear in ref_pointers
        assert any("RISK-01" in ptr for ptr in result.ref_pointers)

    def test_extra_rules_in_template(self):
        """Extra rules in role template expand the query."""
        adr_fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE, tags=["architecture", "test"])
        aup_fact = make_fact(
            code="AUP-01",
            layer=FactLayer.GUARDRAILS,
            type="Acceptable Use Policy Rule",
            status=FactStatus.ACTIVE,
            tags=["governance", "test"],
        )
        index = _build_index([adr_fact, aup_fact])
        template = self._make_role_template(
            query={
                "layers": ["WHY"],
                "types": ["Architecture Decision Record"],
                "tags": ["architecture"],
                "max_facts": 50,
                "extra": [{"layer": "GUARDRAILS", "types": ["Acceptable Use Policy Rule"]}],
            }
        )

        result = assemble_context(index, "test", template)
        codes = [f.code for f in result.loaded_facts]
        assert "ADR-01" in codes
        assert "AUP-01" in codes

    def test_layer_mismatch_excluded(self):
        """Facts that don't match the role's layer query are excluded."""
        run_fact = make_fact(
            code="RUN-01",
            layer=FactLayer.HOW,
            type="Runbook Procedure",
            status=FactStatus.ACTIVE,
            tags=["operations", "test"],
        )
        index = _build_index([run_fact])
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 0

    def test_empty_index(self):
        """Empty index yields empty context."""
        index = _build_index([])
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 0
        assert result.total_tokens == 0


class TestContextResult:
    """Test ContextResult rendering."""

    def test_render_text(self):
        fact = make_fact(code="ADR-01", tags=["architecture", "test"])
        result = ContextResult(
            role="test",
            loaded_facts=[fact],
            total_tokens=100,
        )
        text = result.render_text()
        assert "# Context for role: test" in text
        assert "ADR-01" in text
        assert fact.fact in text

    def test_render_text_with_pointers(self):
        result = ContextResult(
            role="test",
            ref_pointers=["RISK-01 (GUARDRAILS/Risk Assessment Finding)"],
        )
        text = result.render_text()
        assert "Additional facts" in text
        assert "RISK-01" in text

    def test_to_dict(self):
        fact = make_fact(code="ADR-01", tags=["architecture", "test"])
        result = ContextResult(
            role="test",
            loaded_facts=[fact],
            total_tokens=100,
            budget=500,
        )
        d = result.to_dict()
        assert d["role"] == "test"
        assert d["facts_loaded"] == 1
        assert d["total_tokens"] == 100
        assert d["budget"] == 500
        assert len(d["facts"]) == 1
        assert d["facts"][0]["code"] == "ADR-01"
        assert "tokens" in d["facts"][0]

    def test_to_dict_includes_version(self):
        """Gap 4: version field must be present for audit reproducibility (DES-08)."""
        fact = make_fact(code="ADR-01", tags=["architecture", "test"], version=3)
        result = ContextResult(
            role="test",
            loaded_facts=[fact],
            total_tokens=100,
        )
        d = result.to_dict()
        assert d["facts"][0]["version"] == 3

    def test_render_text_includes_version(self):
        """Version should appear in text rendering too."""
        fact = make_fact(code="ADR-01", tags=["architecture", "test"], version=5)
        result = ContextResult(role="test", loaded_facts=[fact], total_tokens=100)
        text = result.render_text()
        assert "ADR-01 v5" in text


class TestStaleDowngrade:
    """Gap 3: Stale facts (past review_by) downgraded to Provisional tier per DG-06."""

    def _make_role_template(self):
        return {
            "name": "Test Agent",
            "query": {
                "layers": ["WHY"],
                "types": ["Architecture Decision Record"],
                "tags": ["architecture"],
                "max_facts": 50,
                "extra": [],
            },
        }

    def test_stale_confirmed_demoted_to_provisional_tier(self):
        """A stale Confirmed fact should load after non-stale Confirmed facts."""
        stale = make_fact(
            code="ADR-01",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            tags=["architecture", "test"],
            review_by=date(2024, 1, 1),  # Well past
        )
        fresh = make_fact(
            code="ADR-02",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            tags=["architecture", "test"],
        )
        index = _build_index([stale, fresh])
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 2
        # Fresh Confirmed should come first, stale should be demoted to Provisional tier
        assert result.loaded_facts[0].code == "ADR-02"
        assert result.loaded_facts[1].code == "ADR-01"

    def test_stale_fact_behind_fresh_provisional(self):
        """A stale Confirmed fact loads in the Provisional tier, alongside Provisional facts."""
        stale_confirmed = make_fact(
            code="ADR-01",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            tags=["architecture", "test"],
            review_by=date(2024, 1, 1),
        )
        fresh_provisional = make_fact(
            code="ADR-02",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.PROVISIONAL,
            tags=["architecture", "test"],
        )
        fresh_confirmed = make_fact(
            code="ADR-03",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            tags=["architecture", "test"],
        )
        index = _build_index([stale_confirmed, fresh_provisional, fresh_confirmed])
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        codes = [f.code for f in result.loaded_facts]
        # Fresh Confirmed first, then Provisional tier (stale + provisional)
        assert codes[0] == "ADR-03"
        assert "ADR-01" in codes[1:]
        assert "ADR-02" in codes[1:]

    def test_non_stale_fact_not_demoted(self):
        """Facts with future review_by stay in Confirmed tier."""
        fresh = make_fact(
            code="ADR-01",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            tags=["architecture", "test"],
            review_by=date(2099, 12, 31),
        )
        index = _build_index([fresh])
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 1
        # Still treated as Confirmed (not demoted)
        assert result.loaded_facts[0].confidence == FactConfidence.CONFIRMED

    def test_stale_still_loads_not_excluded(self):
        """Stale facts are demoted, not excluded. They still appear in context."""
        stale = make_fact(
            code="ADR-01",
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            tags=["architecture", "test"],
            review_by=date(2024, 1, 1),
        )
        index = _build_index([stale])
        template = self._make_role_template()

        result = assemble_context(index, "test", template)
        assert len(result.loaded_facts) == 1  # Still loaded, just in lower tier
