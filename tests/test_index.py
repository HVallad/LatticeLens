"""Index building and query tests."""

from __future__ import annotations

from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact


class TestFactIndex:
    def test_index_builds_from_facts(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        assert len(index.all_facts()) == 12

    def test_codes_by_tag(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        arch_codes = index.codes_by_tag("architecture")
        assert "ADR-01" in arch_codes
        assert "DES-01" in arch_codes

    def test_codes_by_layer(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        why_codes = index.codes_by_layer("WHY")
        assert "ADR-01" in why_codes
        assert "ADR-03" in why_codes
        assert "PRD-01" in why_codes
        assert "DES-01" in why_codes

    def test_refs_forward(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        refs = index.refs_from("ADR-01")
        assert "DES-01" in refs
        assert "RISK-03" in refs
        assert "API-01" in refs

    def test_refs_reverse(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        # DES-01 is referenced by ADR-01
        refs_to = index.refs_to("DES-01")
        assert "ADR-01" in refs_to

    def test_get_from_index(self, seeded_store: YamlFileStore):
        index = seeded_store.index
        fact = index.get("ADR-01")
        assert fact is not None
        assert fact.code == "ADR-01"

    def test_empty_index(self, yaml_store: YamlFileStore):
        index = yaml_store.index
        assert len(index.all_facts()) == 0
        assert index.get("ADR-01") is None
        assert index.codes_by_tag("test") == set()
