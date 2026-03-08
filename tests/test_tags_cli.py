"""CLI tests for `lattice tags` command."""

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


class TestTagsCommand:
    def test_tags_table_output(self, seeded_dir: Path):
        result = runner.invoke(app, ["tags"])
        assert result.exit_code == 0
        assert "Tag Registry" in result.output

    def test_tags_json_output(self, seeded_dir: Path):
        result = runner.invoke(app, ["tags", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "tag" in data[0]
        assert "count" in data[0]
        assert "category" in data[0]

    def test_tags_rebuild(self, seeded_dir: Path):
        result = runner.invoke(app, ["tags", "--rebuild"])
        assert result.exit_code == 0
        assert "Rebuilt" in result.output
        # Verify tags.yaml was created
        tags_path = seeded_dir / ".lattice" / "tags.yaml"
        assert tags_path.exists()

    def test_tags_empty_lattice(self, initialized_dir: Path):
        result = runner.invoke(app, ["tags"])
        assert result.exit_code == 0
        assert "No tags found" in result.output

    def test_tags_frequent_free_warning(self, initialized_dir: Path):
        """Free tags appearing 3+ times trigger a DG-07 warning."""
        from lattice_lens.config import FACTS_DIR, LATTICE_DIR
        from ruamel.yaml import YAML
        from tests.conftest import make_fact

        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        yaml_rw = YAML()
        yaml_rw.default_flow_style = False

        # Create 3 facts with same free tag
        for i in range(1, 4):
            fact = make_fact(code=f"ADR-{i:02d}", tags=["architecture", "my-custom-tag"])
            with open(facts_dir / f"ADR-{i:02d}.yaml", "w") as f:
                yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["tags"])
        assert result.exit_code == 0
        assert "my-custom-tag" in result.output
        assert "DG-07" in result.output

    # --- New tests ---

    def test_tags_no_lattice_errors(self, cli_dir: Path):
        """Without .lattice/, tags should exit with error."""
        result = runner.invoke(app, ["tags"])
        assert result.exit_code != 0

    def test_tags_rebuild_json(self, seeded_dir: Path):
        """--rebuild --json: rebuild the registry then output JSON."""
        result = runner.invoke(app, ["tags", "--rebuild", "--json"])
        assert result.exit_code == 0
        assert "Rebuilt" in result.output
        # Extract the JSON array from output (follows the "Rebuilt" Rich line)
        json_start = result.output.index("[")
        data = json.loads(result.output[json_start:])
        assert isinstance(data, list)
        # Verify tags.yaml was also created
        tags_path = seeded_dir / ".lattice" / "tags.yaml"
        assert tags_path.exists()

    def test_tags_controlled_category(self, initialized_dir: Path):
        """Tags from the controlled vocabulary are categorized correctly."""
        from lattice_lens.config import FACTS_DIR, LATTICE_DIR
        from ruamel.yaml import YAML
        from tests.conftest import make_fact

        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        yaml_rw = YAML()
        yaml_rw.default_flow_style = False

        # "architecture" is in the controlled vocabulary (domain category)
        # Pydantic requires at least 2 tags
        fact = make_fact(code="ADR-01", tags=["architecture", "design"])
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["tags", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        arch_entry = [e for e in data if e["tag"] == "architecture"]
        assert len(arch_entry) == 1
        assert arch_entry[0]["category"] == "domain"

    def test_tags_below_threshold_no_warning(self, initialized_dir: Path):
        """Free tags with fewer than 3 uses should NOT trigger DG-07 warning."""
        from lattice_lens.config import FACTS_DIR, LATTICE_DIR
        from ruamel.yaml import YAML
        from tests.conftest import make_fact

        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        yaml_rw = YAML()
        yaml_rw.default_flow_style = False

        # Only 2 facts with same free tag — below the 3-use threshold
        for i in range(1, 3):
            fact = make_fact(code=f"ADR-{i:02d}", tags=["architecture", "my-custom-tag"])
            with open(facts_dir / f"ADR-{i:02d}.yaml", "w") as f:
                yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["tags"])
        assert result.exit_code == 0
        assert "my-custom-tag" in result.output
        assert "DG-07" not in result.output
