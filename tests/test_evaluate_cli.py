"""CLI integration tests for lattice evaluate command."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app

runner = CliRunner()


@pytest.fixture
def cli_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def initialized_dir(cli_dir: Path):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    return cli_dir


@pytest.fixture
def seeded_dir(initialized_dir: Path):
    seed_src = Path(__file__).resolve().parent.parent / "seed"
    seed_dst = initialized_dir / "seed"
    if seed_src.exists():
        shutil.copytree(seed_src, seed_dst, dirs_exist_ok=True)
    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    return initialized_dir


class TestEvaluateCommand:
    def test_evaluate_no_lattice_silent(self, cli_dir: Path):
        """No .lattice/ directory = silent no-op (exit 0, no output)."""
        result = runner.invoke(app, ["evaluate"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_evaluate_with_lattice_produces_briefing(self, seeded_dir: Path):
        """With seeded lattice, should output governance briefing."""
        result = runner.invoke(app, ["evaluate"])
        assert result.exit_code == 0
        assert "Governance Briefing" in result.output
        assert "Mandatory Rules" in result.output

    def test_evaluate_includes_guardrail_codes(self, seeded_dir: Path):
        """Active GUARDRAILS facts should appear in the briefing."""
        result = runner.invoke(app, ["evaluate"])
        assert result.exit_code == 0
        # Seeded lattice has AUP-* and DG-* facts
        assert "AUP-" in result.output

    def test_evaluate_includes_knowledge_section(self, seeded_dir: Path):
        """The knowledge discovery section should list available facts."""
        result = runner.invoke(app, ["evaluate"])
        assert result.exit_code == 0
        assert "Project Knowledge Available" in result.output
        assert "WHY layer" in result.output

    def test_evaluate_includes_role_commands(self, seeded_dir: Path):
        """Role context commands should be suggested."""
        result = runner.invoke(app, ["evaluate"])
        assert result.exit_code == 0
        assert "lattice context" in result.output

    def test_evaluate_json_output(self, seeded_dir: Path):
        """JSON output should have all expected fields."""
        result = runner.invoke(app, ["evaluate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["lattice_found"] is True
        assert data["guardrails_count"] > 0
        assert isinstance(data["guardrails"], list)
        assert isinstance(data["knowledge_summary"], dict)
        assert isinstance(data["available_roles"], list)

    def test_evaluate_json_no_lattice(self, cli_dir: Path):
        """JSON output without lattice should indicate not found."""
        result = runner.invoke(app, ["evaluate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["lattice_found"] is False
        assert data["guardrails_count"] == 0

    def test_evaluate_only_guardrails_in_rules(self, seeded_dir: Path):
        """Only GUARDRAILS-layer facts in the guardrails list."""
        result = runner.invoke(app, ["evaluate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        guardrail_prefixes = {"AUP", "DG", "RISK", "MC", "COMP"}
        for fact in data["guardrails"]:
            prefix = fact["code"].split("-")[0]
            assert prefix in guardrail_prefixes, (
                f"Non-GUARDRAILS fact {fact['code']} in guardrails list"
            )

    def test_evaluate_no_draft_in_output(self, seeded_dir: Path):
        """Draft guardrails should not appear."""
        result = runner.invoke(app, ["evaluate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # All guardrails should be Active (list_facts filters by status)
        for fact in data["guardrails"]:
            assert fact.get("confidence") in ("Confirmed", "Provisional", "Assumed")

    def test_evaluate_knowledge_summary_has_layers(self, seeded_dir: Path):
        """knowledge_summary should count WHY and HOW facts by type."""
        result = runner.invoke(app, ["evaluate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ks = data["knowledge_summary"]
        # Seeded lattice has WHY-layer facts (ADRs, PRDs, etc.)
        assert "WHY" in ks
        assert sum(ks["WHY"].values()) > 0

    def test_evaluate_available_roles_populated(self, seeded_dir: Path):
        """available_roles should list role template names."""
        result = runner.invoke(app, ["evaluate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["available_roles"]) > 0
        # Seeded lattice has planning, architecture, implementation, qa, deploy
        assert "planning" in data["available_roles"]

    def test_evaluate_with_path_flag(self, seeded_dir: Path):
        """--path flag overrides cwd discovery."""
        result = runner.invoke(app, ["evaluate", "--path", str(seeded_dir), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["lattice_found"] is True

    def test_evaluate_json_guardrails_have_version(self, seeded_dir: Path):
        """Each guardrail in JSON output must include version."""
        result = runner.invoke(app, ["evaluate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for fact in data["guardrails"]:
            assert "version" in fact
            assert isinstance(fact["version"], int)

    def test_evaluate_footer_in_text_output(self, seeded_dir: Path):
        """Text output should include a summary footer."""
        result = runner.invoke(app, ["evaluate"])
        assert result.exit_code == 0
        assert "Source: .lattice/" in result.output
