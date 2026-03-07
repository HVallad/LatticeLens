"""Tests for SqliteStore — SQLite-backed LatticeStore implementation."""

from __future__ import annotations

from pathlib import Path

import pytest

from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR
from lattice_lens.models import FactLayer, FactStatus
from lattice_lens.store.sqlite_store import SqliteStore
from tests.conftest import make_fact


@pytest.fixture
def tmp_lattice_sqlite(tmp_path: Path) -> Path:
    """Create a temporary .lattice/ directory for SQLite store."""
    lattice_root = tmp_path / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)
    return lattice_root


@pytest.fixture
def sqlite_store(tmp_lattice_sqlite: Path) -> SqliteStore:
    """Return a SqliteStore pointed at tmp_lattice."""
    store = SqliteStore(tmp_lattice_sqlite)
    yield store
    store.close()


class TestSqliteStoreCRUD:
    def test_create_and_get(self, sqlite_store: SqliteStore):
        """Round-trip fact through SQLite."""
        fact = make_fact(code="ADR-10")
        sqlite_store.create(fact)
        retrieved = sqlite_store.get("ADR-10")
        assert retrieved is not None
        assert retrieved.code == "ADR-10"
        assert retrieved.layer == FactLayer.WHY
        assert retrieved.tags == fact.tags
        assert retrieved.refs == fact.refs

    def test_get_nonexistent(self, sqlite_store: SqliteStore):
        assert sqlite_store.get("NOPE-01") is None

    def test_list_facts_default_status(self, sqlite_store: SqliteStore):
        """Default returns Active facts."""
        sqlite_store.create(make_fact(code="ADR-01", status=FactStatus.ACTIVE))
        sqlite_store.create(make_fact(code="ADR-02", status=FactStatus.DRAFT))
        facts = sqlite_store.list_facts()
        codes = {f.code for f in facts}
        assert "ADR-01" in codes
        assert "ADR-02" not in codes

    def test_list_facts_layer_filter(self, sqlite_store: SqliteStore):
        """layer='WHY' returns only WHY facts."""
        sqlite_store.create(make_fact(code="ADR-01"))
        sqlite_store.create(
            make_fact(
                code="RISK-01",
                layer=FactLayer.GUARDRAILS,
                type="Risk Register Entry",
            )
        )
        facts = sqlite_store.list_facts(layer="WHY", status=["Active", "Draft"])
        assert all(f.layer == FactLayer.WHY for f in facts)

    def test_list_facts_tag_filter(self, sqlite_store: SqliteStore):
        """tags_any matches correctly."""
        sqlite_store.create(make_fact(code="ADR-01", tags=["alpha", "beta"]))
        sqlite_store.create(make_fact(code="ADR-02", tags=["gamma", "delta"]))
        facts = sqlite_store.list_facts(tags_any=["alpha"], status=["Active"])
        assert len(facts) == 1
        assert facts[0].code == "ADR-01"

    def test_update_increments_version(self, sqlite_store: SqliteStore):
        """Version bumps by 1 (AUP-03)."""
        sqlite_store.create(make_fact(code="ADR-01"))
        updated = sqlite_store.update(
            "ADR-01", {"fact": "Updated fact text with enough length."}, "test update"
        )
        assert updated.version == 2

    def test_update_preserves_created_at(self, sqlite_store: SqliteStore):
        """created_at unchanged (AUP-05)."""
        fact = make_fact(code="ADR-01")
        sqlite_store.create(fact)
        original_created = sqlite_store.get("ADR-01").created_at
        sqlite_store.update("ADR-01", {"fact": "Changed fact text with enough chars."}, "test")
        assert sqlite_store.get("ADR-01").created_at == original_created

    def test_deprecate_sets_status(self, sqlite_store: SqliteStore):
        """Status set to Deprecated."""
        sqlite_store.create(make_fact(code="ADR-01"))
        deprecated = sqlite_store.deprecate("ADR-01", "no longer needed")
        assert deprecated.status == FactStatus.DEPRECATED

    def test_changelog_appended(self, sqlite_store: SqliteStore):
        """Each mutation adds changelog entry (DG-01)."""
        sqlite_store.create(make_fact(code="ADR-01"))
        rows = sqlite_store.conn.execute("SELECT * FROM changelog").fetchall()
        assert len(rows) == 1
        assert rows[0]["action"] == "create"
        assert rows[0]["code"] == "ADR-01"

        # Also check JSONL file
        changelog = sqlite_store.history_dir / "changelog.jsonl"
        assert changelog.exists()
        lines = changelog.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_duplicate_code_rejected(self, sqlite_store: SqliteStore):
        """Second create with same code → error (AUP-06)."""
        sqlite_store.create(make_fact(code="ADR-01"))
        with pytest.raises(FileExistsError):
            sqlite_store.create(make_fact(code="ADR-01"))

    def test_code_immutable(self, sqlite_store: SqliteStore):
        """Changing code in update → rejected (AUP-02)."""
        sqlite_store.create(make_fact(code="ADR-01"))
        with pytest.raises(ValueError, match="immutable"):
            sqlite_store.update("ADR-01", {"code": "ADR-99"}, "try rename")

    def test_wal_mode_enabled(self, sqlite_store: SqliteStore):
        """PRAGMA journal_mode returns WAL."""
        result = sqlite_store.conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"

    def test_exists(self, sqlite_store: SqliteStore):
        assert not sqlite_store.exists("ADR-01")
        sqlite_store.create(make_fact(code="ADR-01"))
        assert sqlite_store.exists("ADR-01")

    def test_all_codes(self, sqlite_store: SqliteStore):
        sqlite_store.create(make_fact(code="ADR-01"))
        sqlite_store.create(make_fact(code="ADR-02"))
        codes = sqlite_store.all_codes()
        assert codes == ["ADR-01", "ADR-02"]

    def test_stats_counts(self, sqlite_store: SqliteStore):
        """Group-by counts match actual data."""
        sqlite_store.create(make_fact(code="ADR-01", status=FactStatus.ACTIVE))
        sqlite_store.create(make_fact(code="ADR-02", status=FactStatus.DRAFT))
        sqlite_store.create(
            make_fact(
                code="RISK-01",
                layer=FactLayer.GUARDRAILS,
                type="Risk Register Entry",
                status=FactStatus.ACTIVE,
            )
        )
        stats = sqlite_store.stats()
        assert stats["total"] == 3
        assert stats["backend"] == "sqlite"
        assert stats["by_layer"]["WHY"] == 2
        assert stats["by_layer"]["GUARDRAILS"] == 1
        assert stats["by_status"]["Active"] == 2
        assert stats["by_status"]["Draft"] == 1

    def test_index_property(self, sqlite_store: SqliteStore):
        """.index returns valid FactIndex."""
        sqlite_store.create(make_fact(code="ADR-01", tags=["test", "alpha"]))
        idx = sqlite_store.index
        assert idx.get("ADR-01") is not None
        assert "ADR-01" in idx.codes_by_tag("test")

    def test_update_tags_and_refs(self, sqlite_store: SqliteStore):
        """Tags and refs are properly replaced on update."""
        sqlite_store.create(make_fact(code="ADR-01", tags=["old-tag", "common"], refs=["DES-01"]))
        sqlite_store.update(
            "ADR-01",
            {"tags": ["new-tag", "common"], "refs": ["DES-02"]},
            "update tags and refs",
        )
        fact = sqlite_store.get("ADR-01")
        assert "new-tag" in fact.tags
        assert "old-tag" not in fact.tags
        assert "DES-02" in fact.refs
        assert "DES-01" not in fact.refs
