"""YamlFileStore CRUD tests."""

from __future__ import annotations

import json

import pytest

from lattice_lens.models import FactStatus
from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact


class TestYamlStoreCRUD:
    def test_create_and_get(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10")
        yaml_store.create(fact)
        retrieved = yaml_store.get("ADR-10")
        assert retrieved is not None
        assert retrieved.code == "ADR-10"
        assert retrieved.fact == fact.fact
        assert retrieved.tags == fact.tags

    def test_create_duplicate(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10")
        yaml_store.create(fact)
        with pytest.raises(FileExistsError):
            yaml_store.create(fact)

    def test_update_increments_version(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10")
        yaml_store.create(fact)
        updated = yaml_store.update(
            "ADR-10", {"fact": "Updated fact text that is long enough"}, "test update"
        )
        assert updated.version == 2
        assert updated.fact == "Updated fact text that is long enough"
        assert updated.updated_at > fact.updated_at

    def test_deprecate(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10")
        yaml_store.create(fact)
        deprecated = yaml_store.deprecate("ADR-10", "no longer relevant")
        assert deprecated.status == FactStatus.DEPRECATED
        assert deprecated.version == 2

    def test_list_default_active(self, seeded_store: YamlFileStore):
        facts = seeded_store.list_facts()
        assert len(facts) > 0
        for f in facts:
            assert f.status == FactStatus.ACTIVE

    def test_list_filter_layer(self, seeded_store: YamlFileStore):
        facts = seeded_store.list_facts(layer="WHY")
        assert len(facts) > 0
        for f in facts:
            assert f.layer.value == "WHY"

    def test_list_filter_tags_any(self, seeded_store: YamlFileStore):
        facts = seeded_store.list_facts(tags_any=["security"])
        codes = {f.code for f in facts}
        assert "RISK-07" in codes
        assert "DG-01" not in codes  # DG-01 has "privacy" not "security"

    def test_list_filter_tags_all(self, seeded_store: YamlFileStore):
        facts = seeded_store.list_facts(tags_all=["privacy", "pii"])
        assert len(facts) > 0
        for f in facts:
            assert "privacy" in f.tags
            assert "pii" in f.tags

    def test_list_text_search(self, seeded_store: YamlFileStore):
        facts = seeded_store.list_facts(text_search="prompt injection")
        assert len(facts) >= 1
        codes = {f.code for f in facts}
        assert "RISK-07" in codes

    def test_exists(self, yaml_store: YamlFileStore):
        assert not yaml_store.exists("ADR-10")
        yaml_store.create(make_fact(code="ADR-10"))
        assert yaml_store.exists("ADR-10")

    def test_stats(self, seeded_store: YamlFileStore):
        stats = seeded_store.stats()
        assert stats["total"] == 12
        assert stats["backend"] == "yaml"
        assert "WHY" in stats["by_layer"]
        assert "Active" in stats["by_status"]

    def test_changelog_appended(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10")
        yaml_store.create(fact)
        yaml_store.update("ADR-10", {"fact": "Updated fact with enough characters"}, "test")

        changelog = yaml_store.history_dir / "changelog.jsonl"
        lines = changelog.read_text().strip().splitlines()
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1["action"] == "create"
        assert entry1["code"] == "ADR-10"

        entry2 = json.loads(lines[1])
        assert entry2["action"] == "update"

    def test_get_nonexistent(self, yaml_store: YamlFileStore):
        assert yaml_store.get("NOPE-99") is None

    def test_update_nonexistent(self, yaml_store: YamlFileStore):
        with pytest.raises(FileNotFoundError):
            yaml_store.update("NOPE-99", {"fact": "test"}, "reason")

    def test_all_codes(self, seeded_store: YamlFileStore):
        codes = seeded_store.all_codes()
        assert len(codes) == 12
        assert "ADR-01" in codes
