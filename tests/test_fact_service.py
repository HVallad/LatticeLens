"""Business rule tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from lattice_lens.models import FactStatus
from lattice_lens.services.fact_service import (
    check_refs,
    create_fact,
    deprecate_fact,
    is_stale,
    next_code,
    update_fact,
)
from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact


class TestFactService:
    def test_next_code_empty(self, yaml_store: YamlFileStore):
        code = next_code(yaml_store, "ADR")
        assert code == "ADR-01"

    def test_next_code_increments(self, seeded_store: YamlFileStore):
        code = next_code(seeded_store, "ADR")
        # ADR-01 and ADR-03 exist, so next is ADR-04
        assert code == "ADR-04"

    def test_check_refs_warns_on_missing(self, yaml_store: YamlFileStore):
        warnings = check_refs(yaml_store, ["NOPE-01", "NOPE-02"])
        assert len(warnings) == 2

    def test_check_refs_no_warnings(self, seeded_store: YamlFileStore):
        warnings = check_refs(seeded_store, ["ADR-01", "PRD-01"])
        assert len(warnings) == 0

    def test_create_fact_with_warnings(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-10", refs=["NOPE-01"])
        created, warnings = create_fact(yaml_store, fact)
        assert created.code == "ADR-10"
        assert len(warnings) == 1

    def test_update_fact_code_immutable(self, yaml_store: YamlFileStore):
        yaml_store.create(make_fact(code="ADR-10"))
        with pytest.raises(ValueError, match="immutable"):
            update_fact(yaml_store, "ADR-10", {"code": "ADR-99"}, "test")

    def test_deprecate_fact(self, yaml_store: YamlFileStore):
        yaml_store.create(make_fact(code="ADR-10"))
        result = deprecate_fact(yaml_store, "ADR-10", "obsolete")
        assert result.status == FactStatus.DEPRECATED

    def test_is_stale_past_date(self):
        fact = make_fact(review_by=date.today() - timedelta(days=1))
        assert is_stale(fact) is True

    def test_is_stale_future_date(self):
        fact = make_fact(review_by=date.today() + timedelta(days=30))
        assert is_stale(fact) is False

    def test_is_stale_no_date(self):
        fact = make_fact()
        assert is_stale(fact) is False
