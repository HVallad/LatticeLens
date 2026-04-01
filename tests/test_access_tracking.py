"""Tests for fact access count tracking (access_service)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lattice_lens.services.access_service import AccessTracker, get_tracker

runner = CliRunner()


@pytest.fixture
def tracker(tmp_lattice: Path) -> AccessTracker:
    """Return an AccessTracker pointed at a temp .lattice/ dir."""
    return get_tracker(tmp_lattice)


class TestRecordAccess:
    def test_increments_count(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("ADR-01", source="api")

        counts = tracker.get_counts()
        assert counts["ADR-01"]["count"] == 3

    def test_tracks_sources(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("ADR-01", source="context")
        tracker.record_access("ADR-01", source="api")

        entry = tracker.get_counts()["ADR-01"]
        assert entry["sources"]["cli"] == 2
        assert entry["sources"]["context"] == 1
        assert entry["sources"]["api"] == 1

    def test_tracks_timestamps(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        entry = tracker.get_counts()["ADR-01"]

        assert entry["first_accessed"] is not None
        assert entry["last_accessed"] is not None
        # first_accessed should be set
        dt = datetime.fromisoformat(entry["first_accessed"])
        assert dt.tzinfo is not None  # Should be timezone-aware

    def test_first_accessed_stays_constant(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        first = tracker.get_counts()["ADR-01"]["first_accessed"]

        tracker.record_access("ADR-01", source="cli")
        assert tracker.get_counts()["ADR-01"]["first_accessed"] == first

    def test_multiple_codes(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("RISK-01", source="api")
        tracker.record_access("ADR-01", source="mcp")

        counts = tracker.get_counts()
        assert counts["ADR-01"]["count"] == 2
        assert counts["RISK-01"]["count"] == 1

    def test_default_source(self, tracker: AccessTracker):
        tracker.record_access("ADR-01")
        entry = tracker.get_counts()["ADR-01"]
        assert entry["sources"]["unknown"] == 1


class TestGetStats:
    def test_returns_none_for_untracked(self, tracker: AccessTracker):
        assert tracker.get_stats("NEVER-01") is None

    def test_returns_stats_for_tracked(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        stats = tracker.get_stats("ADR-01")
        assert stats is not None
        assert stats["count"] == 1


class TestColdFacts:
    def test_finds_never_accessed(self, tracker: AccessTracker):
        tracker.data["ADR-01"] = {
            "count": 0,
            "last_accessed": None,
            "first_accessed": None,
            "sources": {},
        }
        tracker.data["ADR-02"] = {
            "count": 5,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "first_accessed": datetime.now(timezone.utc).isoformat(),
            "sources": {"cli": 5},
        }

        cold = tracker.get_cold_facts(threshold=0, days=30)
        codes = [c["code"] for c in cold]
        assert "ADR-01" in codes
        assert "ADR-02" not in codes

    def test_threshold_parameter(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("ADR-02", source="cli")
        tracker.record_access("ADR-02", source="cli")

        cold = tracker.get_cold_facts(threshold=1, days=9999)
        codes = [c["code"] for c in cold]
        assert "ADR-01" in codes  # count=1 <= threshold=1
        assert "ADR-02" not in codes  # count=2 > threshold=1

    def test_sorted_by_count(self, tracker: AccessTracker):
        tracker.data["B-01"] = {
            "count": 0,
            "last_accessed": None,
            "first_accessed": None,
            "sources": {},
        }
        tracker.data["A-01"] = {
            "count": 0,
            "last_accessed": None,
            "first_accessed": None,
            "sources": {},
        }

        cold = tracker.get_cold_facts()
        # Both have count 0, should be sorted
        assert len(cold) == 2


class TestHotFacts:
    def test_ordering(self, tracker: AccessTracker):
        for _ in range(5):
            tracker.record_access("ADR-01", source="cli")
        for _ in range(10):
            tracker.record_access("RISK-01", source="api")
        tracker.record_access("SP-01", source="mcp")

        hot = tracker.get_hot_facts(top_k=3)
        assert hot[0]["code"] == "RISK-01"
        assert hot[0]["count"] == 10
        assert hot[1]["code"] == "ADR-01"
        assert hot[1]["count"] == 5
        assert hot[2]["code"] == "SP-01"
        assert hot[2]["count"] == 1

    def test_top_k_limit(self, tracker: AccessTracker):
        for i in range(20):
            tracker.record_access(f"ADR-{i:02d}", source="cli")

        hot = tracker.get_hot_facts(top_k=5)
        assert len(hot) == 5

    def test_empty(self, tracker: AccessTracker):
        hot = tracker.get_hot_facts()
        assert hot == []


class TestSaveLoadRoundTrip:
    def test_persist_and_reload(self, tmp_lattice: Path):
        tracker1 = get_tracker(tmp_lattice)
        tracker1.record_access("ADR-01", source="cli")
        tracker1.record_access("ADR-01", source="api")
        tracker1.record_access("RISK-01", source="context")

        # Create a new tracker instance — should load from disk
        tracker2 = get_tracker(tmp_lattice)
        counts = tracker2.get_counts()
        assert counts["ADR-01"]["count"] == 2
        assert counts["ADR-01"]["sources"]["cli"] == 1
        assert counts["ADR-01"]["sources"]["api"] == 1
        assert counts["RISK-01"]["count"] == 1

    def test_empty_file_loads_safely(self, tmp_lattice: Path):
        # Write an empty file
        log_path = tmp_lattice / "access_log.yaml"
        log_path.write_text("")

        tracker = get_tracker(tmp_lattice)
        assert tracker.get_counts() == {}

    def test_missing_file_loads_safely(self, tmp_lattice: Path):
        tracker = get_tracker(tmp_lattice)
        assert tracker.get_counts() == {}


class TestReset:
    def test_reset_single(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("RISK-01", source="api")

        tracker.reset("ADR-01")

        assert tracker.get_counts()["ADR-01"]["count"] == 0
        assert tracker.get_counts()["RISK-01"]["count"] == 1

    def test_reset_all(self, tracker: AccessTracker):
        tracker.record_access("ADR-01", source="cli")
        tracker.record_access("RISK-01", source="api")

        tracker.reset()
        assert tracker.get_counts() == {}

    def test_reset_nonexistent_code(self, tracker: AccessTracker):
        # Should not raise
        tracker.reset("NONEXISTENT-99")
        assert tracker.get_counts() == {}


class TestCLIStats:
    """Test the CLI `lattice fact stats` command output."""

    def test_stats_default(self, seeded_store):
        from lattice_lens.cli.main import app

        result = runner.invoke(app, ["fact", "stats"])
        assert result.exit_code == 0
        assert "Fact Access Statistics" in result.output

    def test_stats_json(self, seeded_store):
        from lattice_lens.cli.main import app

        result = runner.invoke(app, ["fact", "stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_stats_cold(self, seeded_store):
        from lattice_lens.cli.main import app

        result = runner.invoke(app, ["fact", "stats", "--cold"])
        assert result.exit_code == 0
        assert "Cold Facts" in result.output

    def test_stats_hot(self, seeded_store):
        from lattice_lens.cli.main import app

        result = runner.invoke(app, ["fact", "stats", "--hot"])
        assert result.exit_code == 0
        # With no access data yet, should show empty message
        assert "No access data" in result.output or "Hot Facts" in result.output

    def test_stats_specific_code(self, seeded_store):
        from lattice_lens.cli.main import app

        # Get a code from the seeded store
        codes = seeded_store.all_codes()
        assert len(codes) > 0
        code = sorted(codes)[0]

        result = runner.invoke(app, ["fact", "stats", code])
        assert result.exit_code == 0
        assert "Count:" in result.output

    def test_stats_specific_code_not_found(self, seeded_store):
        from lattice_lens.cli.main import app

        result = runner.invoke(app, ["fact", "stats", "NONEXISTENT-99"])
        assert result.exit_code == 1

    def test_stats_cold_json(self, seeded_store):
        from lattice_lens.cli.main import app

        result = runner.invoke(app, ["fact", "stats", "--cold", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
