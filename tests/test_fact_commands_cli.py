"""Extended CLI tests for `lattice fact` commands — add, ls filters, promote, get display."""

from __future__ import annotations

import json
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


def _write_fact_file(base_dir: Path, fact_data: dict) -> Path:
    """Write a fact dict as YAML to the facts directory."""
    facts_dir = base_dir / LATTICE_DIR / FACTS_DIR
    path = facts_dir / f"{fact_data['code']}.yaml"
    with open(path, "w") as f:
        yaml_rw.dump(fact_data, f)
    return path


# -- fact add --from tests ---------------------------------------------------


class TestFactAddFromFile:
    def test_add_from_valid_file(self, initialized_dir: Path):
        fact = make_fact(code="ADR-01", status="Draft")
        fact_file = initialized_dir / "new_fact.yaml"
        with open(fact_file, "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "add", "--from", str(fact_file)])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "ADR-01" in result.output

    def test_add_from_file_not_found(self, initialized_dir: Path):
        result = runner.invoke(app, ["fact", "add", "--from", "nonexistent.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_add_from_file_validation_error(self, initialized_dir: Path):
        bad_file = initialized_dir / "bad_fact.yaml"
        with open(bad_file, "w") as f:
            yaml_rw.dump(
                {
                    "code": "bad-code",
                    "layer": "WHY",
                    "type": "Test",
                    "fact": "x",
                    "tags": [],
                    "owner": "test",
                },
                f,
            )

        result = runner.invoke(app, ["fact", "add", "--from", str(bad_file)])
        assert result.exit_code == 1
        assert "Validation error" in result.output

    def test_add_from_file_duplicate(self, seeded_dir: Path):
        """Adding a fact with an existing code raises an error."""
        fact = make_fact(code="ADR-01")
        fact_file = seeded_dir / "dup.yaml"
        with open(fact_file, "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "add", "--from", str(fact_file)])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_add_from_file_non_draft_warning(self, initialized_dir: Path):
        """AUP-08: warn when importing a fact that isn't Draft."""
        fact = make_fact(code="ADR-01", status="Active")
        fact_file = initialized_dir / "active_fact.yaml"
        with open(fact_file, "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "add", "--from", str(fact_file)])
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "Draft" in result.output

    def test_add_from_file_with_broken_refs(self, initialized_dir: Path):
        """Refs to non-existent codes produce warnings but still create."""
        fact = make_fact(code="ADR-01", status="Draft", refs=["NOPE-99"])
        fact_file = initialized_dir / "ref_fact.yaml"
        with open(fact_file, "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "add", "--from", str(fact_file)])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "Warning" in result.output
        assert "NOPE-99" in result.output


# -- fact ls filter tests ----------------------------------------------------


class TestFactLsFilters:
    def test_ls_filter_by_tag(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "ls", "--tag", "security"])
        assert result.exit_code == 0
        assert "RISK-07" in result.output

    def test_ls_filter_by_status(self, seeded_dir: Path):
        # First deprecate a fact
        runner.invoke(app, ["fact", "deprecate", "ADR-01", "--reason", "test"])

        # Default ls should not show deprecated
        result = runner.invoke(app, ["fact", "ls"])
        assert result.exit_code == 0
        assert "ADR-01" not in result.output

        # Explicit status filter shows deprecated
        result = runner.invoke(app, ["fact", "ls", "--status", "Deprecated"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output

    def test_ls_filter_by_type(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "ls", "--type", "Runbook Procedure", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # All returned facts should have the matching type
        for fact in data:
            assert fact["type"] == "Runbook Procedure"

    def test_ls_empty_results(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "ls", "--tag", "nonexistent-tag-xyz"])
        assert result.exit_code == 0
        assert "No facts found" in result.output

    def test_ls_filter_by_project(self, initialized_dir: Path):
        """Project filter narrows results to project-scoped facts."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        # Create a project-scoped fact
        fact = make_fact(code="ADR-01", status="Active", projects=["my-proj"])
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        # Create a global fact
        fact2 = make_fact(code="ADR-02", status="Active", projects=[])
        with open(facts_dir / "ADR-02.yaml", "w") as f:
            yaml_rw.dump(fact2.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "ls", "--project", "my-proj", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        codes = {f["code"] for f in data}
        assert "ADR-01" in codes

    def test_ls_combined_filters(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "ls", "--layer", "GUARDRAILS", "--tag", "security"])
        assert result.exit_code == 0
        assert "RISK-07" in result.output


# -- fact promote tests ------------------------------------------------------


class TestFactPromoteCommand:
    def test_promote_draft_to_under_review(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Draft")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "promote", "ADR-01", "--reason", "Ready for review"])
        assert result.exit_code == 0
        assert "Promoted" in result.output
        assert "Under Review" in result.output

    def test_promote_under_review_to_active(self, initialized_dir: Path):
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Under Review", confidence="Provisional")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(
            app, ["fact", "promote", "ADR-01", "--reason", "Reviewed and approved"]
        )
        assert result.exit_code == 0
        assert "Promoted" in result.output
        assert "Active" in result.output

    def test_promote_not_found(self, initialized_dir: Path):
        result = runner.invoke(app, ["fact", "promote", "NOPE-99", "--reason", "test"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_promote_already_active(self, seeded_dir: Path):
        """Active facts cannot be promoted further."""
        result = runner.invoke(app, ["fact", "promote", "ADR-01", "--reason", "try again"])
        assert result.exit_code == 1
        assert "Error" in result.output
        assert "not promotable" in result.output

    def test_promote_deprecated_fails(self, seeded_dir: Path):
        """Deprecated facts cannot be promoted."""
        runner.invoke(app, ["fact", "deprecate", "ADR-01", "--reason", "old"])
        result = runner.invoke(app, ["fact", "promote", "ADR-01", "--reason", "revive"])
        assert result.exit_code == 1
        assert "not promotable" in result.output


# -- fact get display tests --------------------------------------------------


class TestFactGetDisplay:
    def test_get_panel_shows_details(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "get", "ADR-01"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output
        assert "WHY" in result.output
        assert "Active" in result.output

    def test_get_stale_fact_warning(self, initialized_dir: Path):
        """Stale facts show a warning in panel display."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", review_by=date.today() - timedelta(days=1))
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "get", "ADR-01"])
        assert result.exit_code == 0
        assert "STALE" in result.output

    def test_get_json_includes_all_fields(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "get", "ADR-01", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "code" in data
        assert "layer" in data
        assert "type" in data
        assert "fact" in data
        assert "tags" in data
        assert "status" in data
        assert "confidence" in data
        assert "version" in data
        assert "owner" in data
        assert "refs" in data
        assert "projects" in data
