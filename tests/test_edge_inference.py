"""Tests for edge type inference from code prefix pairs."""

from __future__ import annotations

from lattice_lens.models import EdgeType
from lattice_lens.services.edge_inference import infer_edge_type


class TestPrefixPairInference:
    """Exact prefix-pair matches."""

    def test_prd_to_adr_drives(self):
        assert infer_edge_type("PRD-01", "ADR-03") == EdgeType.DRIVES

    def test_adr_to_des_drives(self):
        assert infer_edge_type("ADR-01", "DES-01") == EdgeType.DRIVES

    def test_adr_to_risk_mitigates(self):
        assert infer_edge_type("ADR-01", "RISK-03") == EdgeType.MITIGATES

    def test_mon_to_risk_validates(self):
        assert infer_edge_type("MON-01", "RISK-05") == EdgeType.VALIDATES

    def test_risk_to_adr_constrains(self):
        assert infer_edge_type("RISK-07", "ADR-01") == EdgeType.CONSTRAINS

    def test_sp_to_des_implements(self):
        assert infer_edge_type("SP-01", "DES-01") == EdgeType.IMPLEMENTS

    def test_des_to_des_depends_on(self):
        assert infer_edge_type("DES-01", "DES-02") == EdgeType.DEPENDS_ON

    def test_aup_to_sp_constrains(self):
        assert infer_edge_type("AUP-05", "SP-01") == EdgeType.CONSTRAINS


class TestLayerPairFallback:
    """When no prefix-pair match, fall back to layer pairs."""

    def test_eth_to_sp_drives(self):
        """ETH→SP: WHY→HOW = drives (no prefix pair for ETH→SP)."""
        assert infer_edge_type("ETH-01", "SP-01") == EdgeType.DRIVES

    def test_run_to_prd_implements(self):
        """RUN→PRD: HOW→WHY = implements."""
        assert infer_edge_type("RUN-01", "PRD-01") == EdgeType.IMPLEMENTS

    def test_mc_to_adr_constrains(self):
        """MC→ADR: GUARDRAILS→WHY = constrains."""
        assert infer_edge_type("MC-01", "ADR-01") == EdgeType.CONSTRAINS


class TestDefaultRelates:
    """Unknown prefix combinations default to relates."""

    def test_unknown_prefix(self):
        assert infer_edge_type("FOO-01", "BAR-01") == EdgeType.RELATES

    def test_same_unknown(self):
        assert infer_edge_type("FOO-01", "FOO-02") == EdgeType.RELATES


class TestIdempotent:
    """Inference is deterministic and stable."""

    def test_same_input_same_output(self):
        result1 = infer_edge_type("ADR-01", "RISK-03")
        result2 = infer_edge_type("ADR-01", "RISK-03")
        assert result1 == result2
