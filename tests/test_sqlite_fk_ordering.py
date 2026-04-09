"""Tests for issue #54: SQLite FK constraint failure on superseded facts.

Verifies that topological sorting prevents IntegrityError when migrating
facts with superseded_by references, and that cycles are handled gracefully.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR
from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus
from lattice_lens.store.ordering import topological_sort_facts
from lattice_lens.store.sqlite_store import SqliteStore
from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact

runner = CliRunner()


def _make_lattice(tmp_path: Path) -> Path:
    """Create a minimal lattice directory."""
    lattice_root = tmp_path / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)
    (lattice_root / "config.yaml").write_text("version: 0.5.0\nbackend: yaml\n")
    return lattice_root


class TestTopologicalSort:
    """Unit tests for topological_sort_facts."""

    def test_empty_list(self):
        assert topological_sort_facts([]) == []

    def test_no_dependencies(self):
        facts = [make_fact(code="ADR-01"), make_fact(code="ADR-02")]
        result = topological_sort_facts(facts)
        assert len(result) == 2
        assert {f.code for f in result} == {"ADR-01", "ADR-02"}

    def test_superseded_by_ordering(self):
        """Fact that is superseded_by another should come after that target."""
        # ADR-01 is superseded by ADR-02, so ADR-02 must be inserted first
        superseded = make_fact(
            code="ADR-01",
            status=FactStatus.SUPERSEDED,
            superseded_by="ADR-02",
        )
        replacement = make_fact(code="ADR-02")
        # Feed them in wrong order (superseded first)
        result = topological_sort_facts([superseded, replacement])
        codes = [f.code for f in result]
        assert codes.index("ADR-02") < codes.index("ADR-01")

    def test_chain_ordering(self):
        """A -> B -> C chain: C must come first, then B, then A."""
        a = make_fact(code="ADR-01", status=FactStatus.SUPERSEDED, superseded_by="ADR-02")
        b = make_fact(code="ADR-02", status=FactStatus.SUPERSEDED, superseded_by="ADR-03")
        c = make_fact(code="ADR-03")
        result = topological_sort_facts([a, b, c])
        codes = [f.code for f in result]
        assert codes.index("ADR-03") < codes.index("ADR-02") < codes.index("ADR-01")

    def test_cycle_handled_gracefully(self):
        """Cycles should be broken rather than causing infinite recursion."""
        a = make_fact(code="ADR-01", status=FactStatus.SUPERSEDED, superseded_by="ADR-02")
        b = make_fact(code="ADR-02", status=FactStatus.SUPERSEDED, superseded_by="ADR-01")
        result = topological_sort_facts([a, b])
        assert len(result) == 2
        assert {f.code for f in result} == {"ADR-01", "ADR-02"}

    def test_external_reference_ignored(self):
        """superseded_by pointing to a code NOT in the batch should not block."""
        fact = make_fact(
            code="ADR-01",
            status=FactStatus.SUPERSEDED,
            superseded_by="ADR-99",  # not in the list
        )
        result = topological_sort_facts([fact])
        assert len(result) == 1
        assert result[0].code == "ADR-01"


class TestMigrationWithSupersededFacts:
    """Integration tests: YAML->SQLite migration with superseded facts."""

    def test_migration_superseded_fact_inserted_after_target(self, tmp_path, monkeypatch):
        """Reproduces issue #54: migrating facts with superseded_by references."""
        lattice_root = _make_lattice(tmp_path)
        store = YamlFileStore(lattice_root)

        # Create the replacement fact
        store.create(make_fact(code="ADR-02", tags=["replacement", "test"]))
        # Create a fact that is superseded by ADR-02
        store.create(
            make_fact(
                code="ADR-01",
                status=FactStatus.SUPERSEDED,
                superseded_by="ADR-02",
                tags=["original", "test"],
            )
        )

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["backend", "switch", "sqlite"])
        assert result.exit_code == 0
        assert "Migrated 2 facts" in result.output

        # Verify both facts are in SQLite
        sqlite_store = SqliteStore(lattice_root)
        assert sqlite_store.get("ADR-01") is not None
        assert sqlite_store.get("ADR-02") is not None
        assert sqlite_store.get("ADR-01").superseded_by == "ADR-02"
        sqlite_store.close()

    def test_migration_reverse_order_without_fix_would_fail(self, tmp_path):
        """Directly test that inserting in wrong order hits FK constraint."""
        lattice_root = _make_lattice(tmp_path)
        sqlite_store = SqliteStore(lattice_root)

        replacement = make_fact(code="ADR-02")
        superseded = make_fact(
            code="ADR-01",
            status=FactStatus.SUPERSEDED,
            superseded_by="ADR-02",
        )

        # Inserting superseded first (without the fix) should fail on FK
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            sqlite_store.create(superseded)

        sqlite_store.close()

    def test_migration_chain_of_superseded_facts(self, tmp_path, monkeypatch):
        """Chain: ADR-01 -> ADR-02 -> ADR-03 (all superseded in sequence)."""
        lattice_root = _make_lattice(tmp_path)
        store = YamlFileStore(lattice_root)

        store.create(make_fact(code="ADR-03", tags=["latest", "test"]))
        store.create(
            make_fact(
                code="ADR-02",
                status=FactStatus.SUPERSEDED,
                superseded_by="ADR-03",
                tags=["middle", "test"],
            )
        )
        store.create(
            make_fact(
                code="ADR-01",
                status=FactStatus.SUPERSEDED,
                superseded_by="ADR-02",
                tags=["oldest", "test"],
            )
        )

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["backend", "switch", "sqlite"])
        assert result.exit_code == 0
        assert "Migrated 3 facts" in result.output

        sqlite_store = SqliteStore(lattice_root)
        assert sqlite_store.get("ADR-01").superseded_by == "ADR-02"
        assert sqlite_store.get("ADR-02").superseded_by == "ADR-03"
        assert sqlite_store.get("ADR-03").superseded_by is None
        sqlite_store.close()
