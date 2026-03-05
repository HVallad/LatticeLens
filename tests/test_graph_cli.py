"""CLI integration tests for graph commands."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import LATTICE_DIR

runner = CliRunner()


@pytest.fixture
def cli_dir(tmp_path: Path, monkeypatch):
    """Set cwd to tmp_path for CLI tests."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def initialized_dir(cli_dir: Path):
    """Run lattice init and return the dir."""
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    return cli_dir


@pytest.fixture
def seeded_dir(initialized_dir: Path):
    """Run lattice init + seed and return the dir."""
    seed_src = Path(__file__).resolve().parent.parent / "seed"
    seed_dst = initialized_dir / "seed"
    if seed_src.exists():
        shutil.copytree(seed_src, seed_dst, dirs_exist_ok=True)

    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    return initialized_dir


class TestGraphImpact:
    def test_impact_output(self, seeded_dir: Path):
        """lattice graph impact ADR-03 prints direct and transitive sections."""
        result = runner.invoke(app, ["graph", "impact", "ADR-03"])
        assert result.exit_code == 0
        assert "Directly affected" in result.output
        assert "MC-01" in result.output
        assert "RISK-07" in result.output

    def test_impact_json(self, seeded_dir: Path):
        """--json returns valid JSON with expected keys."""
        result = runner.invoke(app, ["graph", "impact", "ADR-03", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "source_code" in data
        assert data["source_code"] == "ADR-03"
        assert "directly_affected" in data
        assert "transitively_affected" in data
        assert "all_affected" in data
        assert "affected_roles" in data
        assert "depth_reached" in data

    def test_impact_depth_1(self, seeded_dir: Path):
        """--depth 1 should limit to direct only."""
        result = runner.invoke(app, ["graph", "impact", "ADR-01", "--depth", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["transitively_affected"]) == 0
        assert len(data["directly_affected"]) > 0

    def test_impact_not_found(self, seeded_dir: Path):
        """Impact on nonexistent code shows error."""
        result = runner.invoke(app, ["graph", "impact", "NOPE-99"])
        assert result.exit_code != 0

    def test_impact_with_roles(self, seeded_dir: Path):
        """Impact should include affected roles from role templates."""
        result = runner.invoke(app, ["graph", "impact", "ADR-03", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # With default role templates, planning and architecture should be affected
        assert len(data["affected_roles"]) > 0


class TestGraphOrphans:
    def test_orphans_output(self, seeded_dir: Path):
        """lattice graph orphans lists disconnected facts (or shows none)."""
        result = runner.invoke(app, ["graph", "orphans"])
        assert result.exit_code == 0
        # All seed facts have refs, so either "No orphaned" or table with placeholders
        assert result.output.strip() != ""

    def test_orphans_json(self, seeded_dir: Path):
        """--json returns valid JSON list."""
        result = runner.invoke(app, ["graph", "orphans", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_orphans_no_lattice(self, cli_dir: Path):
        """Should error if no .lattice/ exists."""
        result = runner.invoke(app, ["graph", "orphans"])
        assert result.exit_code != 0


class TestGraphContradictions:
    def test_contradictions_output(self, seeded_dir: Path):
        """lattice graph contradictions produces output."""
        result = runner.invoke(app, ["graph", "contradictions"])
        assert result.exit_code == 0
        # Seed data has facts across layers sharing tags, so should find candidates
        assert result.output.strip() != ""

    def test_contradictions_json(self, seeded_dir: Path):
        """--json returns valid JSON list."""
        result = runner.invoke(app, ["graph", "contradictions", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_contradictions_min_tags(self, seeded_dir: Path):
        """--min-tags controls sensitivity."""
        # Very high min-tags should return fewer/no results
        result = runner.invoke(app, ["graph", "contradictions", "--min-tags", "10", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 0
