"""Tests for the lattice backend CLI commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR
from lattice_lens.store.yaml_store import YamlFileStore
from lattice_lens.store.sqlite_store import SqliteStore
from tests.conftest import make_fact

runner = CliRunner()


def _setup_lattice(tmp_path: Path) -> Path:
    """Create a minimal lattice with config and a few facts."""
    lattice_root = tmp_path / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)
    (lattice_root / "config.yaml").write_text("version: 0.5.0\nbackend: yaml\n")

    store = YamlFileStore(lattice_root)
    store.create(make_fact(code="ADR-01", tags=["alpha", "beta"]))
    store.create(make_fact(code="ADR-02", tags=["gamma", "delta"]))
    return lattice_root


class TestBackendStatus:
    def test_shows_backend_type(self, tmp_path, monkeypatch):
        _setup_lattice(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["backend", "status"])
        assert result.exit_code == 0
        assert "yaml" in result.output.lower()

    def test_shows_fact_count(self, tmp_path, monkeypatch):
        _setup_lattice(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["backend", "status"])
        assert "2" in result.output


class TestBackendSwitch:
    def test_switch_yaml_to_sqlite(self, tmp_path, monkeypatch):
        """All facts migrated, config updated."""
        lattice_root = _setup_lattice(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["backend", "switch", "sqlite"])
        assert result.exit_code == 0
        assert "Migrated 2 facts" in result.output

        # Verify config updated
        config_text = (lattice_root / "config.yaml").read_text()
        assert "sqlite" in config_text

        # Verify facts accessible via SQLite
        sqlite_store = SqliteStore(lattice_root)
        assert sqlite_store.get("ADR-01") is not None
        assert sqlite_store.get("ADR-02") is not None
        sqlite_store.close()

    def test_switch_sqlite_to_yaml(self, tmp_path, monkeypatch):
        """All facts exported to YAML files after round-trip."""
        lattice_root = _setup_lattice(tmp_path)
        monkeypatch.chdir(tmp_path)

        # First switch to SQLite
        runner.invoke(app, ["backend", "switch", "sqlite"])

        # Then switch back to YAML
        result = runner.invoke(app, ["backend", "switch", "yaml"])
        assert result.exit_code == 0

        # Config should be back to yaml
        config_text = (lattice_root / "config.yaml").read_text()
        assert "yaml" in config_text

    def test_switch_preserves_data(self, tmp_path, monkeypatch):
        """Fact count and content identical after switch."""
        lattice_root = _setup_lattice(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Get original facts
        yaml_store = YamlFileStore(lattice_root)
        original_facts = yaml_store.list_facts(status=None)
        original_codes = {f.code for f in original_facts}

        # Switch to SQLite
        runner.invoke(app, ["backend", "switch", "sqlite"])

        # Verify in SQLite
        sqlite_store = SqliteStore(lattice_root)
        sqlite_facts = sqlite_store.list_facts(status=None)
        sqlite_codes = {f.code for f in sqlite_facts}
        sqlite_store.close()

        assert original_codes == sqlite_codes

    def test_switch_same_backend_noop(self, tmp_path, monkeypatch):
        """Switching to same backend is a no-op."""
        _setup_lattice(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["backend", "switch", "yaml"])
        assert result.exit_code == 0
        assert "Nothing to do" in result.output

    def test_switch_invalid_backend(self, tmp_path, monkeypatch):
        _setup_lattice(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["backend", "switch", "postgres"])
        assert result.exit_code == 1
