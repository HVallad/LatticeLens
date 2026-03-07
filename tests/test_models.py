"""Pydantic model validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lattice_lens.models import FactLayer, FactStatus
from tests.conftest import make_fact


class TestFactCreation:
    def test_valid_fact_creation(self):
        fact = make_fact()
        assert fact.code == "ADR-99"
        assert fact.layer == FactLayer.WHY
        assert fact.version == 1
        assert fact.tags == ["example", "test"]  # sorted

    def test_code_format_validation(self):
        with pytest.raises(ValidationError):
            make_fact(code="bad-code")  # lowercase not allowed

    def test_layer_prefix_mismatch(self):
        with pytest.raises(ValidationError):
            make_fact(code="ADR-01", layer=FactLayer.GUARDRAILS)

    def test_tag_normalization(self):
        fact = make_fact(tags=["Security", "API"])
        assert fact.tags == ["api", "security"]  # lowercase + sorted

    def test_minimum_tags(self):
        with pytest.raises(ValidationError):
            make_fact(tags=["only-one"])

    def test_superseded_requires_target(self):
        with pytest.raises(ValidationError):
            make_fact(status=FactStatus.SUPERSEDED, superseded_by=None)

    def test_superseded_with_target_ok(self):
        fact = make_fact(status=FactStatus.SUPERSEDED, superseded_by="ADR-02")
        assert fact.superseded_by == "ADR-02"

    def test_fact_text_minimum_length(self):
        with pytest.raises(ValidationError):
            make_fact(fact="Short")  # less than 10 chars

    def test_all_layers_valid(self):
        make_fact(code="ADR-01", layer=FactLayer.WHY)
        make_fact(code="RISK-01", layer=FactLayer.GUARDRAILS)
        make_fact(code="SP-01", layer=FactLayer.HOW)

    def test_tag_special_chars_rejected(self):
        with pytest.raises(ValidationError):
            make_fact(tags=["good-tag", "bad tag!"])
