"""Tests for tag_service — tag registry with usage counts and categories."""

from __future__ import annotations

from tests.conftest import make_fact
from lattice_lens.models import FactStatus
from lattice_lens.services.tag_service import (
    build_tag_registry,
    categorize_tag,
    read_tag_registry,
    write_tag_registry,
)


class TestCategorizeTag:
    def test_domain_tag(self):
        assert categorize_tag("architecture") == "domain"
        assert categorize_tag("scaling") == "domain"

    def test_concern_tag(self):
        assert categorize_tag("security") == "concern"
        assert categorize_tag("compliance") == "concern"

    def test_lifecycle_tag(self):
        assert categorize_tag("runtime") == "lifecycle"

    def test_stakeholder_tag(self):
        assert categorize_tag("developer") == "stakeholder"

    def test_risk_tag(self):
        assert categorize_tag("high-severity") == "risk"

    def test_free_tag(self):
        assert categorize_tag("custom-tag") == "free"
        assert categorize_tag("my-project") == "free"


class TestBuildRegistry:
    def test_counts(self, yaml_store):
        yaml_store.create(make_fact(code="ADR-01", tags=["architecture", "scaling"]))
        yaml_store.create(make_fact(code="ADR-02", tags=["architecture", "security"]))
        yaml_store.create(
            make_fact(
                code="RISK-01",
                layer="GUARDRAILS",
                type="Risk Register Entry",
                tags=["risk", "security"],
            )
        )

        registry = build_tag_registry(yaml_store)
        tag_map = {e["tag"]: e["count"] for e in registry}

        assert tag_map["architecture"] == 2
        assert tag_map["security"] == 2
        assert tag_map["scaling"] == 1
        assert tag_map["risk"] == 1

    def test_includes_all_statuses(self, yaml_store):
        yaml_store.create(make_fact(code="ADR-01", tags=["active-tag", "shared"]))
        yaml_store.create(
            make_fact(
                code="ADR-02", tags=["deprecated-tag", "shared"], status=FactStatus.DEPRECATED
            )
        )

        registry = build_tag_registry(yaml_store)
        tag_map = {e["tag"]: e["count"] for e in registry}

        assert "active-tag" in tag_map
        assert "deprecated-tag" in tag_map
        assert tag_map["shared"] == 2

    def test_categorization(self, yaml_store):
        yaml_store.create(make_fact(code="ADR-01", tags=["architecture", "my-custom"]))

        registry = build_tag_registry(yaml_store)
        cat_map = {e["tag"]: e["category"] for e in registry}

        assert cat_map["architecture"] == "domain"
        assert cat_map["my-custom"] == "free"


class TestRegistryRoundtrip:
    def test_write_then_read(self, tmp_lattice):
        registry = [
            {"tag": "architecture", "count": 5, "category": "domain"},
            {"tag": "security", "count": 3, "category": "concern"},
        ]
        write_tag_registry(tmp_lattice, registry)
        loaded = read_tag_registry(tmp_lattice)

        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["tag"] == "architecture"
        assert loaded[1]["count"] == 3

    def test_read_nonexistent(self, tmp_lattice):
        assert read_tag_registry(tmp_lattice) is None
