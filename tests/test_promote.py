"""Tests for the fact promote command and service logic."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, LATTICE_DIR
from lattice_lens.models import FactConfidence, FactStatus
from lattice_lens.services.fact_service import PROMOTION_TRANSITIONS, promote_fact
from tests.conftest import make_fact

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
    seed_src = Path(__file__).resolve().parent.parent / "seed"
    seed_dst = initialized_dir / "seed"
    if seed_src.exists():
        shutil.copytree(seed_src, seed_dst, dirs_exist_ok=True)
    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    return initialized_dir


class TestPromoteService:
    """Unit tests for promote_fact() business logic."""

    def test_promote_draft_to_under_review(self, yaml_store):
        fact = make_fact(
            code="ADR-99", status=FactStatus.DRAFT, confidence=FactConfidence.PROVISIONAL
        )
        yaml_store.create(fact)

        result = promote_fact(yaml_store, "ADR-99", "Ready for review")
        assert result.status == FactStatus.UNDER_REVIEW
        assert result.confidence == FactConfidence.PROVISIONAL
        assert result.version == 2

    def test_promote_under_review_to_active(self, yaml_store):
        fact = make_fact(
            code="ADR-99", status=FactStatus.UNDER_REVIEW, confidence=FactConfidence.PROVISIONAL
        )
        yaml_store.create(fact)

        result = promote_fact(yaml_store, "ADR-99", "Reviewed and approved")
        assert result.status == FactStatus.ACTIVE
        assert result.confidence == FactConfidence.CONFIRMED
        assert result.version == 2

    def test_promote_active_raises(self, yaml_store):
        fact = make_fact(code="ADR-99", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        with pytest.raises(ValueError, match="not promotable"):
            promote_fact(yaml_store, "ADR-99", "Can't promote Active")

    def test_promote_deprecated_raises(self, yaml_store):
        fact = make_fact(code="ADR-99", status=FactStatus.DEPRECATED)
        yaml_store.create(fact)

        with pytest.raises(ValueError, match="not promotable"):
            promote_fact(yaml_store, "ADR-99", "Can't promote Deprecated")

    def test_promote_superseded_raises(self, yaml_store):
        fact = make_fact(
            code="ADR-99",
            status=FactStatus.SUPERSEDED,
            superseded_by="ADR-100",
        )
        yaml_store.create(fact)

        with pytest.raises(ValueError, match="not promotable"):
            promote_fact(yaml_store, "ADR-99", "Can't promote Superseded")

    def test_promote_not_found(self, yaml_store):
        with pytest.raises(FileNotFoundError):
            promote_fact(yaml_store, "ADR-99", "Doesn't exist")

    def test_promote_appends_changelog(self, yaml_store):
        fact = make_fact(code="ADR-99", status=FactStatus.DRAFT)
        yaml_store.create(fact)
        promote_fact(yaml_store, "ADR-99", "Promoting")

        changelog = yaml_store.history_dir / "changelog.jsonl"
        lines = changelog.read_text().strip().split("\n")
        last_entry = json.loads(lines[-1])
        assert last_entry["action"] == "update"
        assert last_entry["code"] == "ADR-99"
        assert "Promoted" in last_entry["reason"]

    def test_full_lifecycle_draft_to_active(self, yaml_store):
        """Test the full Draft -> Under Review -> Active promotion path."""
        fact = make_fact(
            code="ADR-99", status=FactStatus.DRAFT, confidence=FactConfidence.PROVISIONAL
        )
        yaml_store.create(fact)

        # Step 1: Draft -> Under Review
        result = promote_fact(yaml_store, "ADR-99", "Step 1")
        assert result.status == FactStatus.UNDER_REVIEW
        assert result.version == 2

        # Step 2: Under Review -> Active
        result = promote_fact(yaml_store, "ADR-99", "Step 2")
        assert result.status == FactStatus.ACTIVE
        assert result.confidence == FactConfidence.CONFIRMED
        assert result.version == 3

        # Step 3: Active cannot be promoted further
        with pytest.raises(ValueError, match="not promotable"):
            promote_fact(yaml_store, "ADR-99", "Step 3")

    def test_promotion_transitions_map(self):
        """Verify the transition map is complete and correct."""
        assert PROMOTION_TRANSITIONS[FactStatus.DRAFT] == FactStatus.UNDER_REVIEW
        assert PROMOTION_TRANSITIONS[FactStatus.UNDER_REVIEW] == FactStatus.ACTIVE
        assert FactStatus.ACTIVE not in PROMOTION_TRANSITIONS
        assert FactStatus.DEPRECATED not in PROMOTION_TRANSITIONS
        assert FactStatus.SUPERSEDED not in PROMOTION_TRANSITIONS


class TestPromoteCLI:
    """CLI integration tests for `lattice fact promote`."""

    def test_promote_cli(self, seeded_dir):
        # Create a Draft fact first
        from ruamel.yaml import YAML

        yaml_rw = YAML()
        yaml_rw.default_flow_style = False
        fact_data = {
            "code": "ADR-99",
            "layer": "WHY",
            "type": "Architecture Decision Record",
            "fact": "This is a test fact for promotion testing.",
            "tags": ["test", "promotion"],
            "status": "Draft",
            "confidence": "Provisional",
            "owner": "test-team",
            "version": 1,
            "refs": [],
        }

        facts_dir = seeded_dir / LATTICE_DIR / FACTS_DIR
        with open(facts_dir / "ADR-99.yaml", "w") as f:
            yaml_rw.dump(fact_data, f)

        # Promote Draft -> Under Review
        result = runner.invoke(app, ["fact", "promote", "ADR-99", "--reason", "Ready for review"])
        assert result.exit_code == 0
        assert "Promoted" in result.output
        assert "Under Review" in result.output

        # Promote Under Review -> Active
        result = runner.invoke(app, ["fact", "promote", "ADR-99", "--reason", "Approved"])
        assert result.exit_code == 0
        assert "Active" in result.output

    def test_promote_not_found_cli(self, seeded_dir):
        result = runner.invoke(app, ["fact", "promote", "NOPE-99", "--reason", "test"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_promote_active_fails_cli(self, seeded_dir):
        result = runner.invoke(app, ["fact", "promote", "ADR-01", "--reason", "test"])
        assert result.exit_code != 0
        assert "not promotable" in result.output

    def test_promote_requires_reason(self, seeded_dir):
        result = runner.invoke(app, ["fact", "promote", "ADR-01"])
        assert result.exit_code != 0


class TestLifecycleEnforcement:
    """Tests for lifecycle bypass prevention (Gaps 1 & 2)."""

    def test_add_from_file_warns_on_non_draft(self, seeded_dir):
        """Gap 1: Importing a fact with status != Draft should emit a warning."""
        from ruamel.yaml import YAML

        yaml_rw = YAML()
        yaml_rw.default_flow_style = False
        fact_data = {
            "code": "ADR-99",
            "layer": "WHY",
            "type": "Architecture Decision Record",
            "fact": "This fact is imported with Active status bypassing lifecycle.",
            "tags": ["test", "bypass"],
            "status": "Active",
            "confidence": "Confirmed",
            "owner": "test-team",
        }
        import_file = seeded_dir / "import-active.yaml"
        with open(import_file, "w") as f:
            yaml_rw.dump(fact_data, f)

        result = runner.invoke(app, ["fact", "add", "--from", str(import_file)])
        assert result.exit_code == 0
        # Should warn about non-Draft status
        assert "AUP-08" in result.output
        assert "Draft" in result.output
        # But still creates the fact (warn, not block)
        assert "Created" in result.output

    def test_add_from_file_no_warning_for_draft(self, seeded_dir):
        """Importing a Draft fact should not produce a warning."""
        from ruamel.yaml import YAML

        yaml_rw = YAML()
        yaml_rw.default_flow_style = False
        fact_data = {
            "code": "ADR-99",
            "layer": "WHY",
            "type": "Architecture Decision Record",
            "fact": "This fact is imported with Draft status, which is correct.",
            "tags": ["test", "lifecycle"],
            "status": "Draft",
            "confidence": "Provisional",
            "owner": "test-team",
        }
        import_file = seeded_dir / "import-draft.yaml"
        with open(import_file, "w") as f:
            yaml_rw.dump(fact_data, f)

        result = runner.invoke(app, ["fact", "add", "--from", str(import_file)])
        assert result.exit_code == 0
        assert "AUP-08" not in result.output
        assert "Created" in result.output
