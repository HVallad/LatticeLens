"""Pydantic model validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lattice_lens.models import EdgeType, FactLayer, FactRef, FactStatus
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


class TestEdgeTypes:
    def test_edge_type_enum_values(self):
        assert len(EdgeType) == 9
        assert EdgeType.DRIVES == "drives"
        assert EdgeType.RELATES == "relates"
        assert EdgeType.SUPERSEDES == "supersedes"

    def test_factref_from_code(self):
        ref = FactRef(code="ADR-01")
        assert ref.code == "ADR-01"
        assert ref.rel == EdgeType.RELATES

    def test_factref_with_edge_type(self):
        ref = FactRef(code="ADR-01", rel=EdgeType.DRIVES)
        assert ref.rel == EdgeType.DRIVES

    def test_factref_invalid_code(self):
        with pytest.raises(ValidationError):
            FactRef(code="bad-code")

    def test_refs_backward_compat_strings(self):
        fact = make_fact(refs=["ADR-01", "DES-01"])
        assert len(fact.refs) == 2
        assert all(isinstance(r, FactRef) for r in fact.refs)
        assert fact.refs[0].code == "ADR-01"
        assert fact.refs[0].rel == EdgeType.RELATES

    def test_refs_from_dicts(self):
        fact = make_fact(refs=[{"code": "ADR-01", "rel": "drives"}])
        assert fact.refs[0].code == "ADR-01"
        assert fact.refs[0].rel == EdgeType.DRIVES

    def test_refs_mixed_input(self):
        fact = make_fact(refs=["ADR-01", {"code": "DES-01", "rel": "drives"}])
        assert fact.refs[0].rel == EdgeType.RELATES
        assert fact.refs[1].rel == EdgeType.DRIVES

    def test_ref_codes_property(self):
        fact = make_fact(refs=["ADR-01", "DES-01"])
        assert fact.ref_codes == ["ADR-01", "DES-01"]

    def test_refs_model_dump_json(self):
        fact = make_fact(refs=[{"code": "ADR-01", "rel": "drives"}])
        dumped = fact.model_dump(mode="json")
        assert dumped["refs"] == [{"code": "ADR-01", "rel": "drives"}]

    def test_refs_empty_default(self):
        fact = make_fact()
        assert fact.refs == []
        assert fact.ref_codes == []
