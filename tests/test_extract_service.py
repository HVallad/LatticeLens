"""Tests for LLM-powered fact extraction service."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lattice_lens.models import FactStatus
from lattice_lens.services.extract_service import (
    EXTRACTION_SYSTEM_PROMPT,
    _read_document,
    extract_facts_from_document,
)


# -- Helpers ------------------------------------------------------------------


def _mock_api_response(json_text: str):
    """Create a mock Anthropic client that returns json_text as the response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


VALID_FACTS_JSON = json.dumps([
    {
        "code": "ADR-50",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact": "Redis is used as the caching layer for all API responses.",
        "tags": ["caching", "api"],
        "confidence": "Confirmed",
        "refs": [],
        "owner": "architecture-team",
    },
    {
        "code": "RISK-50",
        "layer": "GUARDRAILS",
        "type": "Risk Assessment Finding",
        "fact": "Without rate limiting the API is vulnerable to denial-of-service attacks.",
        "tags": ["security", "api"],
        "confidence": "Confirmed",
        "refs": ["ADR-50"],
        "owner": "security-team",
    },
])


# -- Test _read_document ------------------------------------------------------


class TestReadDocument:
    def test_read_markdown(self, tmp_path: Path):
        doc = tmp_path / "test.md"
        doc.write_text("# Hello\nContent here.", encoding="utf-8")
        assert _read_document(doc) == "# Hello\nContent here."

    def test_read_txt(self, tmp_path: Path):
        doc = tmp_path / "test.txt"
        doc.write_text("Plain text content.", encoding="utf-8")
        assert _read_document(doc) == "Plain text content."

    def test_unsupported_format_errors(self, tmp_path: Path):
        doc = tmp_path / "test.pdf"
        doc.write_text("fake pdf", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported document type"):
            _read_document(doc)


# -- Test extraction prompt ---------------------------------------------------


class TestExtractionPrompt:
    def test_prompt_contains_required_fields(self):
        for field in ("code", "layer", "type", "fact", "tags", "confidence", "refs", "owner"):
            assert field in EXTRACTION_SYSTEM_PROMPT

    def test_prompt_contains_layer_names(self):
        for layer in ("WHY", "GUARDRAILS", "HOW"):
            assert layer in EXTRACTION_SYSTEM_PROMPT


# -- Test extraction logic ----------------------------------------------------


class TestExtractFacts:
    def test_parse_valid_response(self, tmp_path: Path):
        doc = tmp_path / "doc.md"
        doc.write_text("# Some design document content here", encoding="utf-8")

        mock_client = _mock_api_response(VALID_FACTS_JSON)
        with patch("anthropic.Anthropic", return_value=mock_client):
            facts = extract_facts_from_document(doc, api_key="test-key")

        assert len(facts) == 2
        assert facts[0].code == "ADR-50"
        assert facts[0].layer.value == "WHY"
        assert facts[1].code == "RISK-50"
        assert facts[1].layer.value == "GUARDRAILS"

    def test_extracted_facts_are_draft(self, tmp_path: Path):
        doc = tmp_path / "doc.md"
        doc.write_text("# Test document with enough content", encoding="utf-8")

        mock_client = _mock_api_response(VALID_FACTS_JSON)
        with patch("anthropic.Anthropic", return_value=mock_client):
            facts = extract_facts_from_document(doc, api_key="test-key")

        for f in facts:
            assert f.status == FactStatus.DRAFT

    def test_parse_invalid_fact_skipped(self, tmp_path: Path, capsys):
        doc = tmp_path / "doc.md"
        doc.write_text("# Test document content here", encoding="utf-8")

        mixed_json = json.dumps([
            {
                "code": "ADR-50",
                "layer": "WHY",
                "type": "Architecture Decision Record",
                "fact": "A valid fact with enough text content.",
                "tags": ["caching", "api"],
                "confidence": "Confirmed",
                "refs": [],
                "owner": "architecture-team",
            },
            {
                "code": "bad",  # Invalid code format
                "layer": "WHY",
                "type": "Test",
                "fact": "x",  # Too short
                "tags": [],  # Too few
                "owner": "test",
            },
            {
                "code": "RISK-50",
                "layer": "GUARDRAILS",
                "type": "Risk Assessment Finding",
                "fact": "Another valid fact with sufficient content.",
                "tags": ["security", "api"],
                "confidence": "Confirmed",
                "refs": [],
                "owner": "security-team",
            },
        ])

        mock_client = _mock_api_response(mixed_json)
        with patch("anthropic.Anthropic", return_value=mock_client):
            facts = extract_facts_from_document(doc, api_key="test-key")

        assert len(facts) == 2
        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "bad" in captured.err

    def test_existing_codes_in_prompt(self, tmp_path: Path):
        doc = tmp_path / "doc.md"
        doc.write_text("# Test document content here", encoding="utf-8")

        mock_client = _mock_api_response("[]")
        with patch("anthropic.Anthropic", return_value=mock_client):
            extract_facts_from_document(
                doc, api_key="test-key", existing_codes=["ADR-01", "PRD-01"]
            )

        call_args = mock_client.messages.create.call_args
        user_content = call_args.kwargs["messages"][0]["content"]
        assert "ADR-01" in user_content
        assert "PRD-01" in user_content

    def test_code_fence_stripping(self, tmp_path: Path):
        doc = tmp_path / "doc.md"
        doc.write_text("# Test document content here", encoding="utf-8")

        fenced = f"```json\n{VALID_FACTS_JSON}\n```"
        mock_client = _mock_api_response(fenced)
        with patch("anthropic.Anthropic", return_value=mock_client):
            facts = extract_facts_from_document(doc, api_key="test-key")

        assert len(facts) == 2

    def test_empty_document_errors(self, tmp_path: Path):
        doc = tmp_path / "empty.md"
        doc.write_text("", encoding="utf-8")

        with patch("anthropic.Anthropic"):
            with pytest.raises(ValueError, match="Document is empty"):
                extract_facts_from_document(doc, api_key="test-key")


# -- Integration test (requires API key) --------------------------------------


@pytest.mark.integration
def test_live_extraction():
    """End-to-end test with real Anthropic API. Requires LATTICE_ANTHROPIC_API_KEY."""
    import os

    api_key = os.environ.get("LATTICE_ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("LATTICE_ANTHROPIC_API_KEY not set")

    sample = Path(__file__).parent / "fixtures" / "sample_doc.md"
    facts = extract_facts_from_document(sample, api_key=api_key)

    assert len(facts) > 0
    for f in facts:
        assert f.status == FactStatus.DRAFT
        assert len(f.tags) >= 2
        assert len(f.fact) >= 10
