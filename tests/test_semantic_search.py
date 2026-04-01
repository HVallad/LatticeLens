"""Tests for semantic search — embedding service and CLI."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lattice_lens.models import FactLayer, FactStatus
from tests.conftest import make_fact


# ---------------------------------------------------------------------------
# Unit tests that do NOT require sentence-transformers
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Verify graceful errors when sentence-transformers is not installed."""

    def test_import_service_always_works(self):
        """The module should import without error regardless of dependencies."""
        from lattice_lens.services import embedding_service

        assert hasattr(embedding_service, "EmbeddingIndex")
        assert hasattr(embedding_service, "semantic_search")
        assert hasattr(embedding_service, "HAS_SENTENCE_TRANSFORMERS")

    def test_has_sentence_transformers_flag(self):
        """Flag should be a boolean."""
        from lattice_lens.services.embedding_service import HAS_SENTENCE_TRANSFORMERS

        assert isinstance(HAS_SENTENCE_TRANSFORMERS, bool)


class TestFactChecksum:
    """Test the checksum utility (no ML dependencies needed)."""

    def test_checksum_deterministic(self):
        from lattice_lens.services.embedding_service import _fact_checksum

        fact = make_fact(code="ADR-01", fact="This is a test fact with sufficient text.")
        c1 = _fact_checksum(fact)
        c2 = _fact_checksum(fact)
        assert c1 == c2

    def test_checksum_changes_with_content(self):
        from lattice_lens.services.embedding_service import _fact_checksum

        fact1 = make_fact(code="ADR-01", fact="This is a test fact with sufficient text.")
        fact2 = make_fact(code="ADR-01", fact="Different fact text that is long enough.")
        assert _fact_checksum(fact1) != _fact_checksum(fact2)

    def test_checksum_changes_with_version(self):
        from lattice_lens.services.embedding_service import _fact_checksum

        fact1 = make_fact(
            code="ADR-01", fact="This is a test fact with sufficient text.", version=1
        )
        fact2 = make_fact(
            code="ADR-01", fact="This is a test fact with sufficient text.", version=2
        )
        assert _fact_checksum(fact1) != _fact_checksum(fact2)


class TestFactText:
    """Test the text generation utility."""

    def test_fact_text_combines_type_and_body(self):
        from lattice_lens.services.embedding_service import _fact_text

        fact = make_fact(
            type="Architecture Decision Record",
            fact="We decided to use PostgreSQL as the primary database.",
        )
        text = _fact_text(fact)
        assert "Architecture Decision Record" in text
        assert "PostgreSQL" in text


# ---------------------------------------------------------------------------
# Integration tests that REQUIRE sentence-transformers
# ---------------------------------------------------------------------------


def _st_available():
    try:
        import sentence_transformers  # noqa: F401
        import numpy  # noqa: F401

        return True
    except ImportError:
        return False


requires_st = pytest.mark.skipif(
    not _st_available(),
    reason="sentence-transformers not installed",
)


def _make_diverse_facts():
    """Create a set of facts with diverse topics for semantic testing."""
    return [
        make_fact(
            code="ADR-01",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            fact="We use PostgreSQL as the primary database for its reliability and JSONB support.",
            tags=["database", "architecture"],
            status=FactStatus.ACTIVE,
        ),
        make_fact(
            code="ADR-02",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            fact="The deployment pipeline uses Docker containers orchestrated by Kubernetes.",
            tags=["deployment", "infrastructure"],
            status=FactStatus.ACTIVE,
        ),
        make_fact(
            code="MC-01",
            layer=FactLayer.GUARDRAILS,
            type="Mandatory Control",
            fact="All API endpoints must validate authentication tokens before processing requests.",
            tags=["security", "api"],
            status=FactStatus.ACTIVE,
        ),
        make_fact(
            code="SP-01",
            layer=FactLayer.HOW,
            type="Standard Procedure",
            fact="Unit tests must cover at least 80% of code. Use pytest for testing.",
            tags=["testing", "quality"],
            status=FactStatus.ACTIVE,
        ),
        make_fact(
            code="RISK-01",
            layer=FactLayer.GUARDRAILS,
            type="Risk Register Entry",
            fact="Data loss risk is mitigated by automated daily backups to S3.",
            tags=["risk", "backup"],
            status=FactStatus.ACTIVE,
        ),
        make_fact(
            code="ADR-03",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            fact="We chose GraphQL over REST for the public API to reduce over-fetching.",
            tags=["api", "architecture"],
            status=FactStatus.ACTIVE,
            projects=["backend"],
        ),
        make_fact(
            code="DG-01",
            layer=FactLayer.GUARDRAILS,
            type="Data Governance Rule",
            fact="Every mutation to the knowledge lattice must be appended to the changelog.",
            tags=["governance", "changelog"],
            status=FactStatus.ACTIVE,
        ),
    ]


@requires_st
class TestEmbeddingIndex:
    """Test EmbeddingIndex with real embeddings."""

    def test_build_index(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)
        assert idx.fact_count == len(facts)

    def test_build_empty(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        idx = EmbeddingIndex()
        idx.build_index([])
        assert idx.fact_count == 0

    def test_search_returns_relevant_results(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        results = idx.search("database storage", top_k=3, threshold=0.1)
        assert len(results) > 0
        codes = [code for code, _score in results]
        # ADR-01 (PostgreSQL/database) should be top result
        assert "ADR-01" in codes[:2]

    def test_search_deployment(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        results = idx.search("deployment pipeline containers", top_k=3, threshold=0.1)
        assert len(results) > 0
        codes = [code for code, _score in results]
        assert "ADR-02" in codes[:2]

    def test_search_security(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        results = idx.search("authentication security", top_k=3, threshold=0.1)
        assert len(results) > 0
        codes = [code for code, _score in results]
        assert "MC-01" in codes[:2]

    def test_search_empty_index(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        idx = EmbeddingIndex()
        idx.build_index([])
        results = idx.search("anything")
        assert results == []

    def test_threshold_filtering(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        # Very high threshold should return fewer results
        strict = idx.search("database", top_k=10, threshold=0.9)
        loose = idx.search("database", top_k=10, threshold=0.1)
        assert len(loose) >= len(strict)


@requires_st
class TestStalenessDetection:
    """Test index staleness checks."""

    def test_not_stale_when_same(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)
        assert not idx.is_stale(facts)

    def test_stale_when_new_fact(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        new_fact = make_fact(
            code="SP-02",
            layer=FactLayer.HOW,
            type="Standard Procedure",
            fact="Logging must use structured JSON format for all services.",
            tags=["logging", "observability"],
        )
        assert idx.is_stale(facts + [new_fact])

    def test_stale_when_fact_removed(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)
        assert idx.is_stale(facts[:-1])

    def test_stale_when_content_changed(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        modified = list(facts)
        modified[0] = make_fact(
            code="ADR-01",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            fact="We switched from PostgreSQL to MySQL for licensing reasons.",
            tags=["database", "architecture"],
            status=FactStatus.ACTIVE,
        )
        assert idx.is_stale(modified)

    def test_stale_when_no_embeddings(self):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        idx = EmbeddingIndex()
        assert idx.is_stale(_make_diverse_facts())


@requires_st
class TestSaveLoad:
    """Test save/load round-trip."""

    def test_save_load_roundtrip(self, tmp_path):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        path = tmp_path / "embeddings.json"
        idx.save(path)

        # Load into fresh index
        idx2 = EmbeddingIndex()
        assert idx2.load(path)
        assert idx2.fact_count == idx.fact_count
        assert idx2.fact_codes == idx.fact_codes

    def test_load_preserves_search(self, tmp_path):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        path = tmp_path / "embeddings.json"
        idx.save(path)

        idx2 = EmbeddingIndex()
        idx2.load(path)

        # Search should work on loaded index
        results = idx2.search("database storage", top_k=3, threshold=0.1)
        assert len(results) > 0
        codes = [code for code, _ in results]
        assert "ADR-01" in codes[:2]

    def test_load_missing_file(self, tmp_path):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        idx = EmbeddingIndex()
        assert not idx.load(tmp_path / "nonexistent.json")

    def test_load_corrupt_file(self, tmp_path):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        path = tmp_path / "embeddings.json"
        path.write_text("not valid json {{{")

        idx = EmbeddingIndex()
        assert not idx.load(path)

    def test_load_wrong_model(self, tmp_path):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        path = tmp_path / "embeddings.json"
        idx.save(path)

        # Load with different model name — should reject
        idx2 = EmbeddingIndex(model_name="different-model")
        assert not idx2.load(path)

    def test_not_stale_after_load(self, tmp_path):
        from lattice_lens.services.embedding_service import EmbeddingIndex

        facts = _make_diverse_facts()
        idx = EmbeddingIndex()
        idx.build_index(facts)

        path = tmp_path / "embeddings.json"
        idx.save(path)

        idx2 = EmbeddingIndex()
        idx2.load(path)
        assert not idx2.is_stale(facts)


@requires_st
class TestSemanticSearchFunction:
    """Test the high-level semantic_search() function."""

    def test_basic_search(self, tmp_path):
        from lattice_lens.services.embedding_service import semantic_search

        facts = _make_diverse_facts()
        results = semantic_search(
            facts=facts,
            query="database",
            lattice_root=tmp_path,
            top_k=3,
            threshold=0.1,
        )
        assert len(results) > 0
        assert results[0]["code"] == "ADR-01"

    def test_tag_filter(self, tmp_path):
        from lattice_lens.services.embedding_service import semantic_search

        facts = _make_diverse_facts()
        results = semantic_search(
            facts=facts,
            query="architecture decisions",
            lattice_root=tmp_path,
            top_k=10,
            threshold=0.1,
            tag="security",
        )
        # Only MC-01 has security tag
        for r in results:
            assert "security" in r["tags"]

    def test_layer_filter(self, tmp_path):
        from lattice_lens.services.embedding_service import semantic_search

        facts = _make_diverse_facts()
        results = semantic_search(
            facts=facts,
            query="how to do things",
            lattice_root=tmp_path,
            top_k=10,
            threshold=0.1,
            layer="HOW",
        )
        for r in results:
            assert r["layer"] == "HOW"

    def test_status_filter(self, tmp_path):
        from lattice_lens.services.embedding_service import semantic_search

        facts = _make_diverse_facts()
        results = semantic_search(
            facts=facts,
            query="database",
            lattice_root=tmp_path,
            top_k=10,
            threshold=0.1,
            status="Active",
        )
        for r in results:
            assert r["status"] == "Active"

    def test_project_filter(self, tmp_path):
        from lattice_lens.services.embedding_service import semantic_search

        facts = _make_diverse_facts()
        results = semantic_search(
            facts=facts,
            query="API design",
            lattice_root=tmp_path,
            top_k=10,
            threshold=0.1,
            project="backend",
        )
        for r in results:
            assert "backend" in r["projects"]

    def test_result_structure(self, tmp_path):
        from lattice_lens.services.embedding_service import semantic_search

        facts = _make_diverse_facts()
        results = semantic_search(
            facts=facts,
            query="database",
            lattice_root=tmp_path,
            top_k=1,
            threshold=0.1,
        )
        assert len(results) == 1
        r = results[0]
        assert "code" in r
        assert "type" in r
        assert "score" in r
        assert "layer" in r
        assert "status" in r
        assert "tags" in r
        assert "snippet" in r
        assert isinstance(r["score"], float)
        assert 0 <= r["score"] <= 1

    def test_caches_embeddings(self, tmp_path):
        from lattice_lens.services.embedding_service import EMBEDDINGS_FILE, semantic_search

        facts = _make_diverse_facts()
        semantic_search(
            facts=facts,
            query="database",
            lattice_root=tmp_path,
            top_k=1,
        )
        # Embeddings file should now exist
        assert (tmp_path / EMBEDDINGS_FILE).exists()

    def test_force_rebuild(self, tmp_path):
        from lattice_lens.services.embedding_service import semantic_search

        facts = _make_diverse_facts()
        # First call
        r1 = semantic_search(
            facts=facts, query="database", lattice_root=tmp_path, top_k=3, threshold=0.1
        )
        # Force rebuild
        r2 = semantic_search(
            facts=facts,
            query="database",
            lattice_root=tmp_path,
            top_k=3,
            threshold=0.1,
            force_rebuild=True,
        )
        # Should get same results
        assert [r["code"] for r in r1] == [r["code"] for r in r2]


# ---------------------------------------------------------------------------
# CLI tests (mock the embedding service to avoid model downloads in CI)
# ---------------------------------------------------------------------------


class TestSearchCLI:
    """Test the search CLI command with mocked embeddings."""

    def test_search_no_args_shows_error(self):
        from typer.testing import CliRunner

        from lattice_lens.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["search"])
        # Should error — no query and no --rebuild-index
        assert result.exit_code != 0

    def test_search_missing_sentence_transformers(self, monkeypatch):
        """CLI gracefully handles missing dependencies."""
        from typer.testing import CliRunner

        from lattice_lens.cli.main import app

        # Patch the import inside search_command
        runner = CliRunner()

        with patch("lattice_lens.cli.search_command.require_lattice"):
            # Mock the import to simulate missing sentence-transformers
            with patch.dict(
                "sys.modules",
                {"sentence_transformers": None},
            ):
                import lattice_lens.services.embedding_service as es

                original = es.HAS_SENTENCE_TRANSFORMERS
                es.HAS_SENTENCE_TRANSFORMERS = False
                try:
                    result = runner.invoke(app, ["search", "test query"])
                    assert result.exit_code != 0
                    assert "sentence-transformers" in result.output or result.exit_code == 1
                finally:
                    es.HAS_SENTENCE_TRANSFORMERS = original
