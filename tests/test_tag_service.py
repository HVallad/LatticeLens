"""Tests for tag_service — tag registry with usage counts and categories."""

from __future__ import annotations

from tests.conftest import make_fact
from lattice_lens.models import FactStatus
from lattice_lens.services.tag_service import (
    build_tag_registry,
    categorize_tag,
    load_vocabulary,
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


class TestCustomVocabulary:
    """Tests for loading custom vocabulary from tags.yaml (issue #48)."""

    def test_categorize_tag_without_lattice_root_uses_hardcoded(self):
        """Without lattice_root, only hardcoded vocabulary is used."""
        assert categorize_tag("architecture") == "domain"
        assert categorize_tag("my-custom-tag") == "free"

    def test_categorize_tag_with_custom_vocab(self, tmp_lattice):
        """Custom vocabulary in tags.yaml is respected during categorization."""
        registry = [
            {"tag": "my-custom-tag", "count": 5, "category": "domain"},
            {"tag": "another-tag", "count": 3, "category": "concern"},
        ]
        write_tag_registry(tmp_lattice, registry)

        # Without lattice_root: free
        assert categorize_tag("my-custom-tag") == "free"
        # With lattice_root: picks up custom category
        assert categorize_tag("my-custom-tag", lattice_root=tmp_lattice) == "domain"
        assert categorize_tag("another-tag", lattice_root=tmp_lattice) == "concern"

    def test_custom_vocab_does_not_override_hardcoded_with_free(self, tmp_lattice):
        """A tag marked free in tags.yaml does not override hardcoded category."""
        registry = [
            {"tag": "architecture", "count": 10, "category": "free"},
        ]
        write_tag_registry(tmp_lattice, registry)

        # Hardcoded says domain, tags.yaml says free -- hardcoded wins
        assert categorize_tag("architecture", lattice_root=tmp_lattice) == "domain"

    def test_custom_vocab_overrides_hardcoded_category(self, tmp_lattice):
        """A non-free category in tags.yaml takes priority over hardcoded."""
        registry = [
            {"tag": "architecture", "count": 10, "category": "concern"},
        ]
        write_tag_registry(tmp_lattice, registry)

        # tags.yaml says concern -- overrides hardcoded domain
        assert categorize_tag("architecture", lattice_root=tmp_lattice) == "concern"

    def test_load_vocabulary_merges(self, tmp_lattice):
        """load_vocabulary returns merged dict with custom entries."""
        registry = [
            {"tag": "my-tag", "count": 2, "category": "risk"},
        ]
        write_tag_registry(tmp_lattice, registry)

        vocab = load_vocabulary(tmp_lattice)
        assert vocab["my-tag"] == "risk"
        # Hardcoded entries still present
        assert vocab["architecture"] == "domain"

    def test_load_vocabulary_no_tags_yaml(self, tmp_lattice):
        """Without tags.yaml, load_vocabulary returns only hardcoded entries."""
        vocab = load_vocabulary(tmp_lattice)
        assert vocab["architecture"] == "domain"
        assert "my-tag" not in vocab

    def test_unknown_tag_still_free_with_lattice_root(self, tmp_lattice):
        """A tag not in hardcoded vocab or tags.yaml is still free."""
        assert categorize_tag("totally-unknown", lattice_root=tmp_lattice) == "free"
