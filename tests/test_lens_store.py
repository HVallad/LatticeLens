"""Tests for LensStore — mocked MCP client."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lattice_lens.lens import LensConfig, LensConnectionError, LensModeError
from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus
from lattice_lens.store.lens_store import LensStore


# ── Helpers ──


def _make_lens_config(writable: bool = False) -> LensConfig:
    return LensConfig(
        endpoint="http://localhost:8080/mcp",
        transport="sse",
        writable=writable,
    )


def _sample_fact_dict() -> dict:
    """A serialized fact dict as it would arrive from the MCP server."""
    return {
        "code": "ADR-01",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact": "We use YAML files as the primary storage format.",
        "tags": ["architecture", "storage"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "platform-team",
        "refs": [],
        "superseded_by": None,
        "projects": [],
    }


def _sample_fact() -> Fact:
    """A Fact object matching _sample_fact_dict()."""
    return Fact(
        code="ADR-01",
        layer=FactLayer.WHY,
        type="Architecture Decision Record",
        fact="We use YAML files as the primary storage format.",
        tags=["architecture", "storage"],
        status=FactStatus.ACTIVE,
        confidence=FactConfidence.CONFIRMED,
        owner="platform-team",
    )


class TestLensStoreReadOps:
    """Test read-only protocol methods with mocked _call_json."""

    def test_get_returns_fact(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)
        fact_dict = _sample_fact_dict()

        with patch.object(store, "_call_json", return_value=fact_dict) as mock:
            result = store.get("ADR-01")
            mock.assert_called_once_with("fact_get", {"code": "ADR-01"})

        assert result is not None
        assert isinstance(result, Fact)
        assert result.code == "ADR-01"
        assert result.layer == FactLayer.WHY

    def test_get_not_found_returns_none(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(store, "_call_json", return_value={"error": "Fact ZZZ-99 not found"}):
            result = store.get("ZZZ-99")

        assert result is None

    def test_list_facts_returns_facts(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)
        facts = [_sample_fact_dict()]

        with patch.object(store, "_call_json", return_value=facts) as mock:
            result = store.list_facts(layer="WHY", tags_any=["architecture"])
            mock.assert_called_once_with("fact_query", {"layer": "WHY", "tags": ["architecture"]})

        assert len(result) == 1
        assert result[0].code == "ADR-01"

    def test_list_facts_with_status_filter(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(store, "_call_json", return_value=[]) as mock:
            store.list_facts(status="Active")
            mock.assert_called_once_with("fact_query", {"status": "Active"})

    def test_list_facts_error_returns_empty(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(store, "_call_json", return_value={"error": "server error"}):
            result = store.list_facts()

        assert result == []

    def test_exists_returns_true(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(
            store, "_call_json", return_value={"code": "ADR-01", "exists": True}
        ) as mock:
            result = store.exists("ADR-01")
            mock.assert_called_once_with("fact_exists", {"code": "ADR-01"})

        assert result is True

    def test_exists_returns_false(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(store, "_call_json", return_value={"code": "ZZZ-99", "exists": False}):
            result = store.exists("ZZZ-99")

        assert result is False

    def test_all_codes_returns_list(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)
        codes = ["ADR-01", "ADR-02", "SP-01"]

        with patch.object(store, "_call_json", return_value=codes) as mock:
            result = store.all_codes()
            mock.assert_called_once_with("all_codes")

        assert result == codes

    def test_all_codes_empty(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(store, "_call_json", return_value=[]):
            result = store.all_codes()

        assert result == []

    def test_stats_returns_dict(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)
        stats = {"total": 42, "backend": "yaml", "by_status": {"Active": 30}}

        with patch.object(store, "_call_json", return_value=stats) as mock:
            result = store.stats()
            mock.assert_called_once_with("lattice_status")

        assert result == stats
        assert result["total"] == 42


class TestLensStoreWriteGuard:
    """Test that write ops are blocked when writable=False."""

    def test_create_rejected_when_read_only(self, tmp_path):
        config = _make_lens_config(writable=False)
        store = LensStore(tmp_path, config)
        fact = _sample_fact()

        with pytest.raises(LensModeError, match="read-only lens mode"):
            store.create(fact)

    def test_update_rejected_when_read_only(self, tmp_path):
        config = _make_lens_config(writable=False)
        store = LensStore(tmp_path, config)

        with pytest.raises(LensModeError, match="read-only lens mode"):
            store.update("ADR-01", {"fact": "new text"}, "updating")

    def test_deprecate_rejected_when_read_only(self, tmp_path):
        config = _make_lens_config(writable=False)
        store = LensStore(tmp_path, config)

        with pytest.raises(LensModeError, match="read-only lens mode"):
            store.deprecate("ADR-01", "no longer needed")


class TestLensStoreWriteOps:
    """Test write ops when writable=True."""

    def test_create_calls_fact_create(self, tmp_path):
        config = _make_lens_config(writable=True)
        store = LensStore(tmp_path, config)
        fact = _sample_fact()
        fact_dict = _sample_fact_dict()

        with patch.object(store, "_call_json", return_value=fact_dict) as mock:
            result = store.create(fact)
            mock.assert_called_once()
            call_args = mock.call_args
            assert call_args[0][0] == "fact_create"

        assert isinstance(result, Fact)
        assert result.code == "ADR-01"

    def test_update_calls_fact_update(self, tmp_path):
        config = _make_lens_config(writable=True)
        store = LensStore(tmp_path, config)
        updated_dict = _sample_fact_dict()
        updated_dict["fact"] = "Updated fact text here."

        with patch.object(store, "_call_json", return_value=updated_dict) as mock:
            result = store.update("ADR-01", {"fact": "Updated fact text here."}, "test update")
            mock.assert_called_once_with(
                "fact_update",
                {"code": "ADR-01", "reason": "test update", "fact": "Updated fact text here."},
            )

        assert result.fact == "Updated fact text here."

    def test_deprecate_calls_fact_deprecate(self, tmp_path):
        config = _make_lens_config(writable=True)
        store = LensStore(tmp_path, config)
        deprecated_dict = _sample_fact_dict()
        deprecated_dict["status"] = "Deprecated"

        with patch.object(store, "_call_json", return_value=deprecated_dict) as mock:
            result = store.deprecate("ADR-01", "no longer needed")
            mock.assert_called_once_with(
                "fact_deprecate", {"code": "ADR-01", "reason": "no longer needed"}
            )

        assert result.status == FactStatus.DEPRECATED

    def test_create_error_raises_value_error(self, tmp_path):
        config = _make_lens_config(writable=True)
        store = LensStore(tmp_path, config)
        fact = _sample_fact()

        with patch.object(store, "_call_json", return_value={"error": "Duplicate code ADR-01"}):
            with pytest.raises(ValueError, match="Duplicate code"):
                store.create(fact)


class TestLensStoreIndex:
    """Test index building from remote facts."""

    def test_index_builds_from_remote_facts(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)
        facts_data = [
            _sample_fact_dict(),
            {
                **_sample_fact_dict(),
                "code": "SP-01",
                "layer": "HOW",
                "type": "System Prompt Rule",
                "tags": ["prompt", "safety"],
            },
        ]

        with patch.object(store, "_call_json", return_value=facts_data):
            idx = store.index

        assert len(idx.all_facts()) == 2
        assert idx.get("ADR-01") is not None
        assert idx.get("SP-01") is not None
        assert "ADR-01" in idx.codes_by_layer("WHY")
        assert "SP-01" in idx.codes_by_layer("HOW")

    def test_invalidate_index_clears_cache(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(store, "_call_json", return_value=[_sample_fact_dict()]):
            idx1 = store.index
            assert len(idx1.all_facts()) == 1

        store.invalidate_index()

        with patch.object(store, "_call_json", return_value=[]):
            idx2 = store.index
            assert len(idx2.all_facts()) == 0

    def test_index_caches_result(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(store, "_call_json", return_value=[_sample_fact_dict()]) as mock:
            _ = store.index
            _ = store.index  # second access should use cache
            mock.assert_called_once()  # only one call


class TestLensStoreInit:
    """Test LensStore initialization and sentinel paths."""

    def test_sentinel_paths(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        assert store.root == tmp_path
        assert store.facts_dir == tmp_path / "facts"
        assert store.history_dir == tmp_path / "history"

    def test_writable_flag(self, tmp_path):
        config_ro = _make_lens_config(writable=False)
        store_ro = LensStore(tmp_path, config_ro)
        assert store_ro._writable is False

        config_rw = _make_lens_config(writable=True)
        store_rw = LensStore(tmp_path, config_rw)
        assert store_rw._writable is True


class TestLensStoreConnectionError:
    """Test connection error handling."""

    def test_connection_refused_raises(self, tmp_path):
        config = _make_lens_config()
        store = LensStore(tmp_path, config)

        with patch.object(
            store,
            "_run_sync",
            side_effect=LensConnectionError("Failed to connect to remote lattice"),
        ):
            with pytest.raises(LensConnectionError, match="Failed to connect"):
                store._call("fact_get", {"code": "ADR-01"})
