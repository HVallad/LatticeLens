"""Extended CLI tests for `lattice fact` commands — add, ls filters, promote, get display, edit."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

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

    def test_get_not_found(self, initialized_dir: Path):
        result = runner.invoke(app, ["fact", "get", "NOPE-99"])
        assert result.exit_code == 1

    def test_get_shows_refs(self, initialized_dir: Path):
        """Panel display shows ref codes."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        target = make_fact(code="ADR-01")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(target.model_dump(mode="json"), f)

        referrer = make_fact(code="ADR-02", refs=["ADR-01"])
        with open(facts_dir / "ADR-02.yaml", "w") as f:
            yaml_rw.dump(referrer.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "get", "ADR-02"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output

    def test_get_shows_projects(self, initialized_dir: Path):
        """Panel display shows project names."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", projects=["my-proj"])
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        result = runner.invoke(app, ["fact", "get", "ADR-01"])
        assert result.exit_code == 0
        assert "my-proj" in result.output


# -- fact add interactive tests -----------------------------------------------


def _interactive_input(*lines: str) -> str:
    """Build input string for typer.prompt() calls. Adds trailing newline."""
    return "\n".join(lines) + "\n"


class TestFactAddInteractive:
    """Tests for `lattice fact add` (interactive mode — no --from flag)."""

    def test_basic_interactive_add(self, initialized_dir: Path):
        """Happy path: interactive add with all required prompts."""
        inp = _interactive_input(
            "ADR",  # prefix
            "Architecture Decision Record",  # type
            "We decided to use YAML for storage of all facts.",  # fact text
            "architecture, storage",  # tags
            "platform-team",  # owner
            "Draft",  # status
            "Confirmed",  # confidence
            "",  # refs (empty)
            "",  # review_by (empty)
            "",  # projects (empty)
        )
        result = runner.invoke(app, ["fact", "add"], input=inp)
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "ADR-01" in result.output

    def test_interactive_add_with_refs(self, initialized_dir: Path):
        """Interactive add with ref to another fact."""
        # First create a fact to reference
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        target = make_fact(code="ADR-01", status="Draft")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(target.model_dump(mode="json"), f)

        inp = _interactive_input(
            "ADR",
            "Architecture Decision Record",
            "Follow-on decision about YAML storage layout.",
            "architecture, storage",
            "platform-team",
            "Draft",
            "Confirmed",
            "ADR-01",  # refs
            "",  # review_by
            "",  # projects
        )
        result = runner.invoke(app, ["fact", "add"], input=inp)
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "ADR-02" in result.output  # auto-incremented

    def test_interactive_add_with_broken_ref(self, initialized_dir: Path):
        """Interactive add with ref to non-existent code produces warning."""
        inp = _interactive_input(
            "ADR",
            "Architecture Decision Record",
            "Decision referencing something that does not exist.",
            "architecture, test",
            "platform-team",
            "Draft",
            "Confirmed",
            "NOPE-99",  # broken ref
            "",
            "",
        )
        result = runner.invoke(app, ["fact", "add"], input=inp)
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "Warning" in result.output
        assert "NOPE-99" in result.output

    def test_interactive_add_unknown_prefix(self, initialized_dir: Path):
        """Unknown prefix exits with error."""
        inp = _interactive_input(
            "ZZZ",  # unknown prefix
        )
        result = runner.invoke(app, ["fact", "add"], input=inp)
        assert result.exit_code == 1

    def test_interactive_add_validation_error(self, initialized_dir: Path):
        """Validation error (e.g., fact text too short) exits with error."""
        inp = _interactive_input(
            "ADR",
            "Architecture Decision Record",
            "short",  # too short (< 10 chars)
            "test, example",
            "team",
            "Draft",
            "Confirmed",
            "",
            "",
            "",
        )
        result = runner.invoke(app, ["fact", "add"], input=inp)
        assert result.exit_code == 1

    def test_interactive_add_with_review_by(self, initialized_dir: Path):
        """Interactive add with review_by date."""
        future = (date.today() + timedelta(days=90)).isoformat()
        inp = _interactive_input(
            "ADR",
            "Architecture Decision Record",
            "Decision with a review-by date set for the future.",
            "architecture, review",
            "platform-team",
            "Draft",
            "Confirmed",
            "",
            future,  # review_by
            "",
        )
        result = runner.invoke(app, ["fact", "add"], input=inp)
        assert result.exit_code == 0
        assert "Created" in result.output

    def test_interactive_add_with_projects(self, initialized_dir: Path):
        """Interactive add with project scoping."""
        inp = _interactive_input(
            "ADR",
            "Architecture Decision Record",
            "Decision scoped to a specific project for isolation.",
            "architecture, scoping",
            "platform-team",
            "Draft",
            "Confirmed",
            "",
            "",
            "my-project",  # projects
        )
        result = runner.invoke(app, ["fact", "add"], input=inp)
        assert result.exit_code == 0
        assert "Created" in result.output

    def test_interactive_add_auto_increments_code(self, initialized_dir: Path):
        """Two successive adds auto-increment the code."""
        base_inp = _interactive_input(
            "ADR",
            "Architecture Decision Record",
            "First decision about YAML storage and format.",
            "architecture, test",
            "team",
            "Draft",
            "Confirmed",
            "",
            "",
            "",
        )
        result1 = runner.invoke(app, ["fact", "add"], input=base_inp)
        assert result1.exit_code == 0
        assert "ADR-01" in result1.output

        result2 = runner.invoke(app, ["fact", "add"], input=base_inp)
        assert result2.exit_code == 0
        assert "ADR-02" in result2.output


# -- fact edit tests ----------------------------------------------------------


def _mock_editor(changes: dict):
    """Return a callable that simulates $EDITOR by modifying the temp YAML file."""

    def fake_run(cmd, **kwargs):
        tmp_path = cmd[-1]  # last arg is the temp file path
        if not changes:
            return MagicMock(returncode=0)
        from ruamel.yaml import YAML as _YAML

        y = _YAML()
        y.default_flow_style = False
        with open(tmp_path) as f:
            data = y.load(f)
        data.update(changes)
        with open(tmp_path, "w") as f:
            y.dump(data, f)
        return MagicMock(returncode=0)

    return fake_run


class TestFactEdit:
    """Tests for `lattice fact edit CODE` — opens $EDITOR on a temp YAML file."""

    def test_successful_change(self, initialized_dir: Path, monkeypatch):
        """Edit updates fact text successfully."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Active")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        monkeypatch.setattr(
            "subprocess.run",
            _mock_editor({"fact": "Updated fact text with at least ten characters."}),
        )
        result = runner.invoke(app, ["fact", "edit", "ADR-01"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_edit_not_found(self, initialized_dir: Path):
        """Editing a nonexistent fact exits with error."""
        result = runner.invoke(app, ["fact", "edit", "NOPE-99"])
        assert result.exit_code == 1

    def test_edit_no_changes(self, initialized_dir: Path, monkeypatch):
        """No changes detected → exits cleanly."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Active")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        monkeypatch.setattr("subprocess.run", _mock_editor({}))
        result = runner.invoke(app, ["fact", "edit", "ADR-01"])
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_code_change_rejected(self, initialized_dir: Path, monkeypatch):
        """Changing the code is blocked; user declines re-edit."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Active")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        monkeypatch.setattr("subprocess.run", _mock_editor({"code": "ADR-99"}))
        # "n" declines re-edit → aborted
        result = runner.invoke(app, ["fact", "edit", "ADR-01"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_validation_error_then_abort(self, initialized_dir: Path, monkeypatch):
        """Validation error on edit → user declines re-edit → aborted."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Active")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        # Empty fact text fails validation
        monkeypatch.setattr("subprocess.run", _mock_editor({"fact": "x"}))
        result = runner.invoke(app, ["fact", "edit", "ADR-01"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_promotion_via_edit_blocked(self, initialized_dir: Path, monkeypatch):
        """Status change matching promotion transition is blocked."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Draft")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        # Try to promote Draft → Under Review via edit
        monkeypatch.setattr("subprocess.run", _mock_editor({"status": "Under Review"}))
        # "n" declines re-edit → aborted
        result = runner.invoke(app, ["fact", "edit", "ADR-01"], input="n\n")
        assert result.exit_code == 0
        assert "promote" in result.output.lower() or "Aborted" in result.output

    def test_updates_tags(self, initialized_dir: Path, monkeypatch):
        """Edit can update tags."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Active", tags=["architecture", "test"])
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        monkeypatch.setattr(
            "subprocess.run",
            _mock_editor({"tags": ["architecture", "test", "updated"]}),
        )
        result = runner.invoke(app, ["fact", "edit", "ADR-01"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_updates_refs_with_warning(self, initialized_dir: Path, monkeypatch):
        """Adding a broken ref via edit produces a warning."""
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        fact = make_fact(code="ADR-01", status="Active")
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(fact.model_dump(mode="json"), f)

        monkeypatch.setattr(
            "subprocess.run",
            _mock_editor({"refs": [{"code": "NOPE-99", "rel": "relates"}]}),
        )
        result = runner.invoke(app, ["fact", "edit", "ADR-01"])
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "NOPE-99" in result.output


# -- fact deprecate tests -----------------------------------------------------


class TestFactDeprecateCommand:
    def test_deprecate_existing_fact(self, seeded_dir: Path):
        result = runner.invoke(app, ["fact", "deprecate", "ADR-01", "--reason", "no longer needed"])
        assert result.exit_code == 0
        assert "Deprecated" in result.output
        assert "ADR-01" in result.output

    def test_deprecate_not_found(self, initialized_dir: Path):
        result = runner.invoke(app, ["fact", "deprecate", "NOPE-99", "--reason", "does not exist"])
        assert result.exit_code == 1
