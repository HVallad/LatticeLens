"""Tests for import/export service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus
from lattice_lens.services.exchange_service import (
    detect_format,
    export_facts,
    import_facts,
)
from lattice_lens.store.yaml_store import YamlFileStore

yaml_rw = YAML()
yaml_rw.default_flow_style = False

# Semantic fields for round-trip comparison (exclude timestamps and version)
SEMANTIC_FIELDS = {"code", "layer", "type", "fact", "tags", "status", "confidence", "refs", "owner"}


def _make_fact(**overrides) -> Fact:
    defaults = {
        "code": "ADR-99",
        "layer": FactLayer.WHY,
        "type": "Architecture Decision Record",
        "fact": "This is a test fact with sufficient length.",
        "tags": ["test", "example"],
        "status": FactStatus.ACTIVE,
        "confidence": FactConfidence.CONFIRMED,
        "owner": "test-team",
    }
    defaults.update(overrides)
    return Fact(**defaults)


# -- Export Tests -------------------------------------------------------------


class TestExport:
    def test_export_json(self, seeded_store: YamlFileStore):
        result = export_facts(seeded_store, format="json")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "code" in item
            assert "layer" in item
            assert "fact" in item

    def test_export_yaml(self, seeded_store: YamlFileStore):
        result = export_facts(seeded_store, format="yaml")
        data = yaml_rw.load(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_export_includes_all_statuses(self, yaml_store: YamlFileStore):
        yaml_store.create(_make_fact(code="ADR-01", status=FactStatus.ACTIVE))
        yaml_store.create(_make_fact(code="ADR-02", status=FactStatus.DRAFT))
        yaml_store.create(_make_fact(
            code="ADR-03",
            status=FactStatus.DEPRECATED,
        ))

        result = export_facts(yaml_store, format="json")
        data = json.loads(result)
        statuses = {item["status"] for item in data}
        assert "Active" in statuses
        assert "Draft" in statuses
        assert "Deprecated" in statuses

    def test_export_empty_lattice(self, yaml_store: YamlFileStore):
        result = export_facts(yaml_store, format="json")
        data = json.loads(result)
        assert data == []

    def test_export_unsupported_format(self, yaml_store: YamlFileStore):
        with pytest.raises(ValueError, match="Unsupported format"):
            export_facts(yaml_store, format="xml")


# -- Import Tests -------------------------------------------------------------


class TestImport:
    def test_import_json_skip(self, yaml_store: YamlFileStore):
        # Create an existing fact
        yaml_store.create(_make_fact(code="ADR-01"))

        import_data = json.dumps([
            _make_fact(code="ADR-01").model_dump(mode="json"),
            _make_fact(code="ADR-02").model_dump(mode="json"),
        ], default=str)

        results = import_facts(yaml_store, import_data, format="json", strategy="skip")
        assert results["created"] == 1
        assert results["skipped"] == 1
        assert results["overwritten"] == 0

    def test_import_json_overwrite(self, yaml_store: YamlFileStore):
        yaml_store.create(_make_fact(code="ADR-01", fact="Original fact text content here."))

        updated = _make_fact(code="ADR-01", fact="Updated fact text content here.")
        import_data = json.dumps([
            updated.model_dump(mode="json"),
            _make_fact(code="ADR-02").model_dump(mode="json"),
        ], default=str)

        results = import_facts(
            yaml_store, import_data, format="json", strategy="overwrite"
        )
        assert results["created"] == 1
        assert results["overwritten"] == 1

        # Verify the overwritten fact has updated content and bumped version
        fact = yaml_store.get("ADR-01")
        assert fact is not None
        assert fact.fact == "Updated fact text content here."
        assert fact.version == 2  # Auto-incremented from 1

    def test_import_json_fail(self, yaml_store: YamlFileStore):
        yaml_store.create(_make_fact(code="ADR-01"))

        import_data = json.dumps([
            _make_fact(code="ADR-01").model_dump(mode="json"),
        ], default=str)

        with pytest.raises(FileExistsError, match="ADR-01"):
            import_facts(yaml_store, import_data, format="json", strategy="fail")

    def test_import_invalid_fact(self, yaml_store: YamlFileStore):
        import_data = json.dumps([
            _make_fact(code="ADR-01").model_dump(mode="json"),
            {
                "code": "bad-code",  # Invalid format
                "layer": "WHY",
                "type": "Test",
                "fact": "x",  # Too short
                "tags": [],  # Too few
                "owner": "test",
            },
        ], default=str)

        results = import_facts(yaml_store, import_data, format="json", strategy="skip")
        assert results["created"] == 1
        assert len(results["errors"]) == 1
        assert results["errors"][0]["code"] == "bad-code"

    def test_import_yaml(self, yaml_store: YamlFileStore):
        from io import StringIO

        facts_data = [_make_fact(code="ADR-01").model_dump(mode="json")]
        buf = StringIO()
        yaml_rw.dump(facts_data, buf)
        yaml_data = buf.getvalue()

        results = import_facts(yaml_store, yaml_data, format="yaml", strategy="skip")
        assert results["created"] == 1


# -- Round-trip Tests ---------------------------------------------------------


class TestRoundTrip:
    def _semantic_key(self, item: dict) -> tuple:
        """Extract semantic fields for comparison, normalizing lists."""
        return (
            item["code"],
            item["layer"],
            item["type"],
            item["fact"],
            tuple(sorted(item.get("tags", []))),
            item["status"],
            item["confidence"],
            tuple(sorted(item.get("refs", []))),
            item["owner"],
        )

    def test_round_trip_json(self, seeded_store: YamlFileStore, yaml_store: YamlFileStore):
        # Export from seeded store
        exported = export_facts(seeded_store, format="json")

        # Import into empty store
        results = import_facts(yaml_store, exported, format="json", strategy="skip")
        assert results["errors"] == []

        # Export from new store
        re_exported = export_facts(yaml_store, format="json")

        # Compare semantic fields
        original = json.loads(exported)
        reimported = json.loads(re_exported)

        original_keys = {self._semantic_key(item) for item in original}
        reimported_keys = {self._semantic_key(item) for item in reimported}
        assert original_keys == reimported_keys

    def test_round_trip_yaml(self, seeded_store: YamlFileStore, yaml_store: YamlFileStore):
        exported = export_facts(seeded_store, format="yaml")
        results = import_facts(yaml_store, exported, format="yaml", strategy="skip")
        assert results["errors"] == []

        re_exported = export_facts(yaml_store, format="yaml")

        original = yaml_rw.load(exported)
        reimported = yaml_rw.load(re_exported)

        original_keys = {self._semantic_key(item) for item in original}
        reimported_keys = {self._semantic_key(item) for item in reimported}
        assert original_keys == reimported_keys


# -- Format Detection Tests ---------------------------------------------------


class TestDetectFormat:
    def test_detect_json(self):
        assert detect_format(Path("facts.json")) == "json"

    def test_detect_yaml(self):
        assert detect_format(Path("facts.yaml")) == "yaml"
        assert detect_format(Path("facts.yml")) == "yaml"

    def test_detect_unknown(self):
        with pytest.raises(ValueError, match="Cannot detect format"):
            detect_format(Path("facts.csv"))
