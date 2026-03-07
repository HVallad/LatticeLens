"""CLI integration tests for lattice context command."""

from __future__ import annotations

import json
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
    import shutil

    seed_src = Path(__file__).resolve().parent.parent / "seed"
    seed_dst = initialized_dir / "seed"
    if seed_src.exists():
        shutil.copytree(seed_src, seed_dst, dirs_exist_ok=True)

    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    return initialized_dir


class TestContextCommand:
    def test_context_basic(self, seeded_dir):
        result = runner.invoke(app, ["context", "planning"])
        assert result.exit_code == 0
        assert "Planning Agent" in result.output
        assert "Facts loaded" in result.output

    def test_context_json(self, seeded_dir):
        result = runner.invoke(app, ["context", "planning", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["role"] == "planning"
        assert "facts" in data
        assert isinstance(data["facts"], list)
        assert "ref_pointers" in data

    def test_context_with_budget(self, seeded_dir):
        result = runner.invoke(app, ["context", "planning", "--budget", "300"])
        assert result.exit_code == 0
        assert "Budget" in result.output or "budget" in result.output.lower()

    def test_context_json_with_budget(self, seeded_dir):
        result = runner.invoke(app, ["context", "planning", "--budget", "300", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["budget"] == 300
        assert data["total_tokens"] <= 300

    def test_context_invalid_role(self, seeded_dir):
        result = runner.invoke(app, ["context", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_context_architecture_role(self, seeded_dir):
        result = runner.invoke(app, ["context", "architecture", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["role"] == "architecture"
        assert data["facts_loaded"] > 0

    def test_context_no_draft_in_output(self, seeded_dir):
        """Draft facts should never appear in context assembly."""
        result = runner.invoke(app, ["context", "planning", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for fact in data["facts"]:
            assert fact["status"] != "Draft"

    def test_context_no_deprecated_in_output(self, seeded_dir):
        """Deprecated facts should not appear in context."""
        # First deprecate a fact
        runner.invoke(app, ["fact", "deprecate", "ADR-01", "--reason", "testing"])

        result = runner.invoke(app, ["context", "planning", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        codes = [f["code"] for f in data["facts"]]
        assert "ADR-01" not in codes

    def test_context_confirmed_before_provisional(self, seeded_dir):
        """Confirmed facts should be listed before Provisional."""
        result = runner.invoke(app, ["context", "planning", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)

        seen_provisional = False
        for fact in data["facts"]:
            if fact["confidence"] == "Provisional":
                seen_provisional = True
            if fact["confidence"] == "Confirmed" and seen_provisional:
                pytest.fail("Confirmed fact appeared after Provisional")

    def test_context_ref_pointers_present(self, seeded_dir):
        """With budget, ref_pointers should include excluded facts."""
        result = runner.invoke(app, ["context", "planning", "--budget", "200", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Small budget should leave some facts unloaded
        if data["budget_exhausted"]:
            assert len(data["ref_pointers"]) > 0

    def test_context_json_includes_version(self, seeded_dir):
        """Gap 4: Every fact in JSON output must include version for audit (DES-08)."""
        result = runner.invoke(app, ["context", "planning", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for fact in data["facts"]:
            assert "version" in fact
            assert isinstance(fact["version"], int)
            assert fact["version"] >= 1
