"""CLI tests for `lattice types` command."""

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


class TestTypesCommand:
    def test_types_table_output(self, initialized_dir: Path):
        result = runner.invoke(app, ["types"])
        assert result.exit_code == 0
        assert "Type Registry" in result.output
        assert "ADR" in result.output
        assert "WHY" in result.output

    def test_types_json_output(self, initialized_dir: Path):
        result = runner.invoke(app, ["types", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "WHY" in data
        assert "GUARDRAILS" in data
        assert "HOW" in data

    def test_types_audit_clean(self, initialized_dir: Path):
        """An empty lattice has no mismatches."""
        result = runner.invoke(app, ["types", "--audit"])
        assert result.exit_code == 0
        assert "All facts use canonical types" in result.output

    def test_types_audit_with_mismatch(self, initialized_dir: Path):
        from lattice_lens.config import FACTS_DIR, LATTICE_DIR
        from ruamel.yaml import YAML
        from tests.conftest import make_fact

        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        yaml_rw = YAML()
        yaml_rw.default_flow_style = False

        # Create a fact with non-canonical type
        fact = make_fact(
            code="RISK-01",
            layer="GUARDRAILS",
            type="Risk Assessment Finding",
            tags=["risk", "test"],
        )
        with open(facts_dir / "RISK-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["types", "--audit"])
        assert result.exit_code == 0
        assert "Type Mismatches" in result.output
        assert "RISK-01" in result.output
        assert "non-canonical" in result.output

    def test_types_audit_json(self, seeded_dir: Path):
        result = runner.invoke(app, ["types", "--audit", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    # --- New tests ---

    def test_types_no_lattice_errors(self, cli_dir: Path):
        """Without .lattice/, types should exit with error."""
        result = runner.invoke(app, ["types"])
        assert result.exit_code != 0

    def test_types_audit_json_empty(self, initialized_dir: Path):
        """--audit --json on a clean lattice returns an empty list."""
        result = runner.invoke(app, ["types", "--audit", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_types_descriptions_shown(self, initialized_dir: Path):
        """Table output includes the Description column."""
        result = runner.invoke(app, ["types"])
        assert result.exit_code == 0
        assert "Description" in result.output

    def test_types_all_layers_present(self, initialized_dir: Path):
        """All three layers appear in the default type registry output."""
        result = runner.invoke(app, ["types"])
        assert result.exit_code == 0
        assert "WHY" in result.output
        assert "GUARDRAILS" in result.output
        assert "HOW" in result.output
