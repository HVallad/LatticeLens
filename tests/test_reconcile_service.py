"""Tests for reconcile_service — bidirectional reconciliation engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_fact
from lattice_lens.models import FactStatus
from lattice_lens.services.reconcile_service import (
    Finding,
    ReconciliationReport,
    reconcile,
    render_reconciliation_prompt,
)


def _write_file(root: Path, relpath: str, content: str) -> Path:
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _mock_api_response(json_text: str):
    """Create a mock Anthropic client that returns json_text as the response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


class TestReconcileFactsToCode:
    def test_explicit_code_reference_found(self, yaml_store, tmp_path):
        """Comment '# ADR-03' in source detected as confirmed."""
        fact = make_fact(code="ADR-03", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-03: use Typer\nimport typer\n")

        report = reconcile(yaml_store, code_root)
        assert len(report.confirmed) == 1
        assert report.confirmed[0].code == "ADR-03"

    def test_missing_fact_detected(self, yaml_store, tmp_path):
        """Active fact with no code evidence → orphaned."""
        fact = make_fact(code="ADR-05", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# no references here\nx = 1\n")

        report = reconcile(yaml_store, code_root)
        assert len(report.orphaned) == 1
        assert report.orphaned[0].code == "ADR-05"

    def test_multiple_references_increase_confidence(self, yaml_store, tmp_path):
        """Multiple references to same fact should give higher confidence."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(
            code_root,
            "main.py",
            "# ADR-01\n# See ADR-01 for details\n# Per ADR-01\n",
        )

        report = reconcile(yaml_store, code_root)
        assert len(report.confirmed) == 1
        assert report.confirmed[0].confidence > 0.5

    def test_non_active_facts_excluded(self, yaml_store, tmp_path):
        """Only active facts are checked — draft/deprecated are skipped."""
        fact = make_fact(code="ADR-10", status=FactStatus.DRAFT)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-10\n")

        report = reconcile(yaml_store, code_root)
        # Draft fact not in active list, so not checked
        assert len(report.confirmed) == 0
        assert len(report.orphaned) == 0


class TestReconcileCodeToFacts:
    def test_untracked_pattern_detected(self, yaml_store, tmp_path):
        """Import without ADR → untracked finding."""
        # No facts in store covering frameworks
        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "import flask\napp = flask.Flask(__name__)\n")

        report = reconcile(yaml_store, code_root)
        assert len(report.untracked) >= 1
        untracked_descs = [f.description.lower() for f in report.untracked]
        assert any("framework" in d for d in untracked_descs)

    def test_covered_pattern_not_flagged(self, yaml_store, tmp_path):
        """Pattern covered by existing fact should not be flagged."""
        fact = make_fact(
            code="ADR-01",
            status=FactStatus.ACTIVE,
            type="Architecture Decision Record",
            tags=["architecture", "cli"],
        )
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "import typer\n")

        report = reconcile(yaml_store, code_root)
        framework_untracked = [f for f in report.untracked if "framework" in f.description.lower()]
        assert len(framework_untracked) == 0


class TestReconciliationReport:
    def test_report_summary_counts(self, yaml_store, tmp_path):
        """Summary dict has correct counts."""
        f1 = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        f2 = make_fact(code="ADR-02", status=FactStatus.ACTIVE, layer="WHY")
        yaml_store.create(f1)
        yaml_store.create(f2)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-01 referenced\n")

        report = reconcile(yaml_store, code_root)
        summary = report.summary()
        assert summary["confirmed"] == 1
        assert summary["orphaned"] == 1
        assert "coverage_pct" in summary

    def test_coverage_calculation(self):
        """coverage_pct = confirmed / total_checked * 100."""
        report = ReconciliationReport()
        report.confirmed = [Finding("confirmed", "A-1", "ok", "f.py", 1, 0.8, "x")] * 3
        report.orphaned = [Finding("orphaned", "B-1", "missing", None, None, 0.6, "y")]
        # 3 confirmed, 1 orphaned = 3/4 = 75%
        assert report.coverage_pct == 75.0
        assert report.summary()["coverage_pct"] == 75.0

    def test_empty_report(self):
        """Empty report has 0 coverage."""
        report = ReconciliationReport()
        assert report.coverage_pct == 0.0
        assert report.total_facts_checked == 0

    def test_exclude_patterns_respected(self, yaml_store, tmp_path):
        """Files matching exclude globs are skipped."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "project"
        code_root.mkdir()
        _write_file(code_root, "src/main.py", "# no refs\n")
        _write_file(code_root, "vendor/lib.py", "# ADR-01\n")

        report = reconcile(
            yaml_store,
            code_root,
            exclude_patterns=["**/vendor/**"],
        )
        # ADR-01 reference is in excluded vendor dir
        assert len(report.confirmed) == 0


class TestLlmReconcile:
    def test_use_llm_requires_api_key(self, yaml_store, tmp_path):
        """use_llm=True without api_key should raise ValueError."""
        code_root = tmp_path / "src"
        code_root.mkdir()
        with pytest.raises(ValueError, match="API key"):
            reconcile(yaml_store, code_root, use_llm=True)

    def test_llm_reconcile_enriches_findings(self, yaml_store, tmp_path):
        """LLM call should update finding categories and confidence."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# uses Typer framework\nimport typer\n")

        llm_response = json.dumps(
            [
                {
                    "original_category": "orphaned",
                    "revised_category": "confirmed",
                    "code": "ADR-01",
                    "confidence": 0.9,
                    "reasoning": "The code imports typer which implements this ADR.",
                    "file": "main.py",
                    "line": 2,
                }
            ]
        )

        mock_client = _mock_api_response(llm_response)
        with patch("anthropic.Anthropic", return_value=mock_client):
            report = reconcile(
                yaml_store,
                code_root,
                use_llm=True,
                api_key="test-key",
            )

        assert len(report.confirmed) >= 1
        confirmed_with_reasoning = [f for f in report.confirmed if f.llm_reasoning]
        assert len(confirmed_with_reasoning) >= 1
        assert "typer" in confirmed_with_reasoning[0].llm_reasoning.lower()

    def test_llm_reconcile_fallback_on_bad_json(self, yaml_store, tmp_path):
        """If LLM returns invalid JSON, fall back to rule-based report."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-01\n")

        mock_client = _mock_api_response("not valid json at all")
        with patch("anthropic.Anthropic", return_value=mock_client):
            report = reconcile(
                yaml_store,
                code_root,
                use_llm=True,
                api_key="test-key",
            )

        # Should fall back to the rule-based result
        assert len(report.confirmed) == 1
        assert report.confirmed[0].code == "ADR-01"

    def test_llm_reconcile_with_code_fences(self, yaml_store, tmp_path):
        """LLM response wrapped in code fences should be parsed correctly."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-01\n")

        inner_json = json.dumps(
            [
                {
                    "original_category": "confirmed",
                    "revised_category": "confirmed",
                    "code": "ADR-01",
                    "confidence": 0.95,
                    "reasoning": "Explicit reference found.",
                    "file": "main.py",
                    "line": 1,
                }
            ]
        )
        fenced = f"```json\n{inner_json}\n```"

        mock_client = _mock_api_response(fenced)
        with patch("anthropic.Anthropic", return_value=mock_client):
            report = reconcile(
                yaml_store,
                code_root,
                use_llm=True,
                api_key="test-key",
            )

        assert len(report.confirmed) == 1
        assert report.confirmed[0].confidence == 0.95

    def test_llm_reconcile_non_array_fallback(self, yaml_store, tmp_path):
        """If LLM returns valid JSON but not an array, fall back."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-01\n")

        mock_client = _mock_api_response('{"error": "unexpected format"}')
        with patch("anthropic.Anthropic", return_value=mock_client):
            report = reconcile(
                yaml_store,
                code_root,
                use_llm=True,
                api_key="test-key",
            )

        # Should fall back to the rule-based result
        assert len(report.confirmed) == 1


class TestRenderReconciliationPrompt:
    def test_prompt_contains_system_instructions(self, yaml_store, tmp_path):
        """Prompt should include the system instructions."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-01\n")

        report = reconcile(yaml_store, code_root)
        active_facts = yaml_store.list_facts(status=["Active"])
        prompt = render_reconciliation_prompt(report, active_facts)

        assert "reconciliation" in prompt.lower()
        assert "VALIDATE" in prompt
        assert "RESCUE" in prompt

    def test_prompt_contains_findings(self, yaml_store, tmp_path):
        """Prompt should include fact codes and finding categories."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-01\n")

        report = reconcile(yaml_store, code_root)
        active_facts = yaml_store.list_facts(status=["Active"])
        prompt = render_reconciliation_prompt(report, active_facts)

        assert "ADR-01" in prompt
        assert "confirmed" in prompt.lower()

    def test_prompt_contains_fact_text(self, yaml_store, tmp_path):
        """Full fact text should appear in the prompt."""
        fact = make_fact(
            code="RISK-01",
            status=FactStatus.ACTIVE,
            layer="GUARDRAILS",
            type="Risk Register Entry",
            fact="Prompt injection via uploaded docs is a high severity risk.",
            tags=["security", "prompt-injection"],
        )
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# no refs\n")

        report = reconcile(yaml_store, code_root)
        active_facts = yaml_store.list_facts(status=["Active"])
        prompt = render_reconciliation_prompt(report, active_facts)

        assert "Prompt injection via uploaded docs" in prompt
        assert "RISK-01" in prompt
        assert "security" in prompt

    def test_prompt_with_no_facts(self, yaml_store, tmp_path):
        """Prompt should handle empty lattice gracefully."""
        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "x = 1\n")

        report = reconcile(yaml_store, code_root)
        active_facts = yaml_store.list_facts(status=["Active"])
        prompt = render_reconciliation_prompt(report, active_facts)

        assert "No active facts" in prompt

    def test_prompt_contains_usage_hint(self, yaml_store, tmp_path):
        """Prompt should include usage instructions for the developer."""
        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "x = 1\n")

        report = reconcile(yaml_store, code_root)
        active_facts = yaml_store.list_facts(status=["Active"])
        prompt = render_reconciliation_prompt(report, active_facts)

        assert "agent" in prompt.lower()
        assert "JSON" in prompt


class TestFindingLlmReasoning:
    def test_finding_default_no_reasoning(self):
        """Finding should default to no LLM reasoning."""
        f = Finding("confirmed", "ADR-01", "ok", "f.py", 1, 0.8, "evidence")
        assert f.llm_reasoning is None

    def test_finding_with_reasoning(self):
        """Finding should accept LLM reasoning."""
        f = Finding(
            "confirmed",
            "ADR-01",
            "ok",
            "f.py",
            1,
            0.8,
            "evidence",
            llm_reasoning="This code clearly implements the ADR.",
        )
        assert f.llm_reasoning == "This code clearly implements the ADR."
