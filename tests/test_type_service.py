"""Tests for type_service — canonical type registry and audit."""

from __future__ import annotations

from conftest import make_fact
from lattice_lens.config import LAYER_PREFIXES
from lattice_lens.services.type_service import (
    CANONICAL_TYPES,
    audit_types,
    canonical_type_for_prefix,
    read_type_registry,
    write_type_registry,
)


class TestCanonicalTypes:
    def test_all_prefixes_covered(self):
        """Every prefix in LAYER_PREFIXES should have a canonical type."""
        for layer, prefixes in LAYER_PREFIXES.items():
            for prefix in prefixes:
                canonical = canonical_type_for_prefix(prefix)
                assert canonical is not None, f"Missing canonical type for {prefix} ({layer})"

    def test_lookup(self):
        assert canonical_type_for_prefix("ADR") == "Architecture Decision Record"
        assert canonical_type_for_prefix("RISK") == "Risk Register Entry"
        assert canonical_type_for_prefix("SP") == "System Prompt Rule"

    def test_unknown_prefix(self):
        assert canonical_type_for_prefix("UNKNOWN") is None


class TestAuditTypes:
    def test_finds_mismatches(self, yaml_store):
        # Canonical type for RISK is "Risk Register Entry"
        yaml_store.create(
            make_fact(
                code="RISK-01",
                layer="GUARDRAILS",
                type="Risk Assessment Finding",  # Non-canonical!
                tags=["risk", "test"],
            )
        )
        # Canonical type for ADR is "Architecture Decision Record"
        yaml_store.create(
            make_fact(
                code="ADR-01",
                type="Architecture Decision Record",  # Canonical
                tags=["architecture", "test"],
            )
        )

        mismatches = audit_types(yaml_store)
        assert len(mismatches) == 1
        assert mismatches[0]["code"] == "RISK-01"
        assert mismatches[0]["current_type"] == "Risk Assessment Finding"
        assert mismatches[0]["canonical_type"] == "Risk Register Entry"

    def test_no_mismatches(self, yaml_store):
        yaml_store.create(
            make_fact(
                code="ADR-01",
                type="Architecture Decision Record",
                tags=["architecture", "test"],
            )
        )
        mismatches = audit_types(yaml_store)
        assert mismatches == []


class TestRegistryRoundtrip:
    def test_write_then_read(self, tmp_lattice):
        write_type_registry(tmp_lattice)
        loaded = read_type_registry(tmp_lattice)

        assert loaded is not None
        assert "WHY" in loaded
        assert "GUARDRAILS" in loaded
        assert "HOW" in loaded
        assert loaded["WHY"]["ADR"] == "Architecture Decision Record"

    def test_read_nonexistent(self, tmp_lattice):
        assert read_type_registry(tmp_lattice) is None

    def test_write_custom_map(self, tmp_lattice):
        custom = {"WHY": {"ADR": "Custom Type"}}
        write_type_registry(tmp_lattice, custom)
        loaded = read_type_registry(tmp_lattice)
        assert loaded["WHY"]["ADR"] == "Custom Type"
