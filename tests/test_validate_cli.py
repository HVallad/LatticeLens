"""CLI tests for `lattice validate` and `lattice reindex` commands."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, LATTICE_DIR
from tests.conftest import make_fact

runner = CliRunner()
yaml_rw = YAML()
yaml_rw.default_flow_style = False


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


def _write_fact(facts_dir: Path, fact):
    """Write a fact to the facts directory as YAML."""
    with open(facts_dir / f"{fact.code}.yaml", "w") as f:
        yaml_rw.dump(fact.model_dump(mode="json"), f)


class TestValidateCommand:
    def test_validate_clean_lattice(self, seeded_dir: Path):
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0

    def test_validate_empty_lattice(self, initialized_dir: Path):
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "No fact files" in result.output or "All checks passed" in result.output

    def test_validate_with_parse_error(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        bad_path = facts_dir / "BAD-01.yaml"
        bad_path.write_text("{{invalid yaml: [", encoding="utf-8")

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 1
        assert "error" in result.output.lower()

    def test_validate_duplicate_code(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-10")
        _write_fact(facts_dir, fact)

        # Write a duplicate with different filename
        with open(facts_dir / "ADR-10-copy.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 1
        assert "Duplicate code" in result.output

    def test_validate_stale_warning(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-10", review_by=date.today() - timedelta(days=1))
        _write_fact(facts_dir, fact)

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "stale" in result.output.lower() or "warning" in result.output.lower()

    def test_validate_broken_ref_warning(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-10", refs=["NOPE-99"])
        _write_fact(facts_dir, fact)

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "NOPE-99" in result.output

    def test_validate_fix_tags(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR

        # Write raw YAML with unsorted, mixed-case tags (bypass Pydantic normalization)
        raw = make_fact(code="ADR-10").model_dump(mode="json")
        raw["tags"] = ["Zebra", "apple"]
        with open(facts_dir / "ADR-10.yaml", "w") as f:
            yaml_rw.dump(raw, f)

        result = runner.invoke(app, ["validate", "--fix"])
        assert result.exit_code == 0
        assert "Fixed" in result.output or "Auto-fixed" in result.output

    def test_validate_warnings_count(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-10", refs=["NOPE-99"])
        _write_fact(facts_dir, fact)

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()

    def test_validate_type_mismatch_warning(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(
            code="RISK-01",
            layer="GUARDRAILS",
            type="Risk Assessment Finding",
            tags=["risk", "test"],
        )
        _write_fact(facts_dir, fact)

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "canonical" in result.output.lower() or "RISK-01" in result.output

    def test_validate_no_errors_with_warnings(self, initialized_dir: Path):
        """Warnings alone don't cause non-zero exit."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-10", refs=["MISS-01"])
        _write_fact(facts_dir, fact)

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "No errors" in result.output or "warning" in result.output.lower()


class TestReindexCommand:
    def test_reindex_creates_index(self, seeded_dir: Path):
        result = runner.invoke(app, ["reindex"])
        assert result.exit_code == 0
        assert "Rebuilt" in result.output

        index_path = seeded_dir / LATTICE_DIR / "index.yaml"
        assert index_path.exists()

    def test_reindex_empty_lattice(self, initialized_dir: Path):
        result = runner.invoke(app, ["reindex"])
        assert result.exit_code == 0
        assert "0 facts" in result.output

    def test_reindex_counts_facts(self, seeded_dir: Path):
        result = runner.invoke(app, ["reindex"])
        assert result.exit_code == 0
        assert "facts indexed" in result.output
        # Seed creates 12+ facts; verify a non-zero count is reported
        assert "0 facts" not in result.output
