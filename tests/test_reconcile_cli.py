"""Tests for the lattice reconcile CLI command."""

from __future__ import annotations

import json
from pathlib import Path

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

    def test_reconcile_llm_flag_errors(self, tmp_path, monkeypatch):
        lattice_root, _ = _setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["reconcile", "--llm"])
        assert result.exit_code == 1
        assert "not yet implemented" in result.output.lower()

    def test_reconcile_no_lattice(self, tmp_path, monkeypatch):
        """Running reconcile without .lattice/ should error."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["reconcile"])
        assert result.exit_code == 1
