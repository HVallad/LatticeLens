"""CLI integration tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, LATTICE_DIR, ROLES_DIR

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
    # Copy seed file to expected location
    import shutil
    seed_src = Path(__file__).resolve().parent.parent / "seed"
    seed_dst = initialized_dir / "seed"
    if seed_src.exists():
        shutil.copytree(seed_src, seed_dst, dirs_exist_ok=True)

    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    return initialized_dir


class TestInitCommand:
    def test_init_creates_structure(self, cli_dir: Path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0

        lattice = cli_dir / LATTICE_DIR
        assert lattice.is_dir()
        assert (lattice / FACTS_DIR).is_dir()
        assert (lattice / ROLES_DIR).is_dir()
        assert (lattice / "config.yaml").is_file()
        assert (lattice / ".gitignore").is_file()

    def test_init_already_exists(self, initialized_dir: Path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code != 0
        assert "already exists" in result.output


class TestSeedCommand:
    def test_seed_loads_facts(self, seeded_dir: Path):
        facts_dir = seeded_dir / LATTICE_DIR / FACTS_DIR
        yaml_files = list(facts_dir.glob("*.yaml"))
        assert len(yaml_files) >= 12  # 12 seed + placeholders


class TestFactGetCommand:
    def test_fact_get_json(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "get", "ADR-01", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["code"] == "ADR-01"
        assert data["layer"] == "WHY"

    def test_fact_get_panel(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "get", "ADR-01"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output

    def test_fact_get_not_found(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "get", "NOPE-99"])
        assert result.exit_code != 0


class TestFactLsCommand:
    def test_fact_ls_all(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "ls"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output

    def test_fact_ls_filter_layer(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "ls", "--layer", "WHY"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output
        # HOW facts shouldn't appear
        assert "RUN-01" not in result.output

    def test_fact_ls_json(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "ls", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0


class TestFactDeprecateCommand:
    def test_deprecate(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "deprecate", "ADR-01", "--reason", "test"])
        assert result.exit_code == 0
        assert "Deprecated" in result.output

    def test_deprecate_not_found(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "deprecate", "NOPE-99", "--reason", "test"])
        assert result.exit_code != 0


class TestStatusCommand:
    def test_status_output(self, seeded_dir: Path):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "yaml" in result.output.lower()
        assert "Total facts" in result.output or "total" in result.output.lower()


class TestValidateCommand:
    def test_validate_seeded(self, seeded_dir: Path):
        result = runner.invoke(app, ["validate"])
        # Should pass (no errors), may have warnings for missing refs
        assert result.exit_code == 0


class TestReindexCommand:
    def test_reindex(self, seeded_dir: Path):
        result = runner.invoke(app, ["reindex"])
        assert result.exit_code == 0
        assert "Rebuilt" in result.output
        index_file = seeded_dir / LATTICE_DIR / "index.yaml"
        assert index_file.is_file()
