"""Tests for the lattice reconcile CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR
from tests.conftest import make_fact

runner = CliRunner()


def _setup_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal lattice + codebase for reconcile testing."""
    # Set up .lattice directory
    lattice_root = tmp_path / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)

    # Write config
    (lattice_root / "config.yaml").write_text("version: 0.4.0\nbackend: yaml\n")

    # Create a source file with fact reference
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("# ADR-01: use Typer framework\nimport typer\n")

    return lattice_root, tmp_path


def _add_fact(lattice_root: Path, fact):
    """Write a fact YAML file directly."""
    from lattice_lens.store.yaml_store import YamlFileStore

    store = YamlFileStore(lattice_root)
    store.create(fact)


def _mock_api_response(json_text: str):
    """Create a mock Anthropic client that returns json_text as the response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


class TestReconcileCli:
    def test_reconcile_runs(self, tmp_path, monkeypatch):
        lattice_root, project_root = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["reconcile", "--path", str(tmp_path / "src")])
        assert result.exit_code == 0
        assert "Reconciliation Report" in result.output

    def test_reconcile_json_output(self, tmp_path, monkeypatch):
        lattice_root, project_root = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app, ["reconcile", "--path", str(tmp_path / "src"), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "confirmed" in data
        assert "coverage_pct" in data

    def test_reconcile_verbose(self, tmp_path, monkeypatch):
        lattice_root, project_root = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app, ["reconcile", "--path", str(tmp_path / "src"), "--verbose"]
        )
        assert result.exit_code == 0
        assert "Confirmed" in result.output or "Orphaned" in result.output

    def test_reconcile_no_lattice(self, tmp_path, monkeypatch):
        """Running reconcile without .lattice/ should error."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["reconcile"])
        assert result.exit_code == 1


class TestReconcileLlmCli:
    def test_reconcile_llm_requires_api_key(self, tmp_path, monkeypatch):
        """--llm without API key should error."""
        lattice_root, _ = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LATTICE_ANTHROPIC_API_KEY", raising=False)
        result = runner.invoke(app, ["reconcile", "--llm"])
        assert result.exit_code == 1
        assert "api key" in result.output.lower()

    def test_reconcile_llm_and_prompt_exclusive(self, tmp_path, monkeypatch):
        """--llm and --llm-prompt together should error."""
        lattice_root, _ = _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["reconcile", "--llm", "--llm-prompt"])
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output.lower()

    def test_reconcile_llm_prompt_outputs_text(self, tmp_path, monkeypatch):
        """--llm-prompt should print structured prompt to stdout."""
        lattice_root, _ = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app, ["reconcile", "--llm-prompt", "--path", str(tmp_path / "src")]
        )
        assert result.exit_code == 0
        assert "reconciliation" in result.output.lower()
        assert "ADR-01" in result.output

    def test_reconcile_llm_prompt_contains_fact_text(self, tmp_path, monkeypatch):
        """--llm-prompt output should include full fact text."""
        lattice_root, _ = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(
            code="RISK-01",
            layer="GUARDRAILS",
            type="Risk Register Entry",
            fact="Prompt injection via user-uploaded documents is high severity.",
            tags=["security", "prompt-injection"],
        ))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app, ["reconcile", "--llm-prompt", "--path", str(tmp_path / "src")]
        )
        assert result.exit_code == 0
        assert "Prompt injection" in result.output
        assert "RISK-01" in result.output

    def test_reconcile_llm_with_mock_api(self, tmp_path, monkeypatch):
        """--llm with mocked API should produce enriched output."""
        lattice_root, _ = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))
        monkeypatch.chdir(tmp_path)

        llm_response = json.dumps([
            {
                "original_category": "confirmed",
                "revised_category": "confirmed",
                "code": "ADR-01",
                "confidence": 0.95,
                "reasoning": "Explicit code reference found.",
                "file": "main.py",
                "line": 1,
            }
        ])

        mock_client = _mock_api_response(llm_response)
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = runner.invoke(
                app,
                [
                    "reconcile", "--llm",
                    "--api-key", "test-key",
                    "--path", str(tmp_path / "src"),
                ],
            )
        assert result.exit_code == 0
        assert "Reconciliation Report" in result.output

    def test_reconcile_llm_json_with_reasoning(self, tmp_path, monkeypatch):
        """--llm --json should include llm_reasoning in output."""
        lattice_root, _ = _setup_project(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))
        monkeypatch.chdir(tmp_path)

        llm_response = json.dumps([
            {
                "original_category": "confirmed",
                "revised_category": "confirmed",
                "code": "ADR-01",
                "confidence": 0.95,
                "reasoning": "Explicit reference in comment.",
                "file": "main.py",
                "line": 1,
            }
        ])

        mock_client = _mock_api_response(llm_response)
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = runner.invoke(
                app,
                [
                    "reconcile", "--llm", "--json",
                    "--api-key", "test-key",
                    "--path", str(tmp_path / "src"),
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        confirmed = data["findings"]["confirmed"]
        assert len(confirmed) >= 1
        assert "llm_reasoning" in confirmed[0]
