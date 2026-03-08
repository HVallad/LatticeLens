"""Tests for lattice lens CLI commands (connect, status, disconnect)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import LATTICE_DIR, LENS_FILE
from lattice_lens.lens import LensConfig, LensConnectionError, write_lens_file

runner = CliRunner()


@pytest.fixture
def cli_dir(tmp_path: Path, monkeypatch):
    """Set cwd to tmp_path for CLI tests."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def lens_dir(cli_dir: Path):
    """Create a .lattice/ directory with a .lens file."""
    lattice_root = cli_dir / LATTICE_DIR
    lattice_root.mkdir()
    config = LensConfig(
        endpoint="http://localhost:8080/mcp",
        transport="sse",
        writable=False,
    )
    write_lens_file(lattice_root, config)
    return cli_dir


class TestLensConnect:
    def test_connect_creates_lens_file(self, cli_dir):
        """lens connect should create .lattice/.lens after verifying server."""
        mock_store = MagicMock()
        mock_store.stats.return_value = {"total": 10, "backend": "yaml"}

        with patch("lattice_lens.store.lens_store.LensStore", return_value=mock_store):
            result = runner.invoke(app, ["lens", "connect", "http://localhost:8080/mcp"])

        assert result.exit_code == 0
        assert "Connected" in result.output
        lens_path = cli_dir / LATTICE_DIR / LENS_FILE
        assert lens_path.exists()

    def test_connect_verifies_server_fails(self, cli_dir):
        """lens connect should fail if server is unreachable."""
        mock_cls = MagicMock()
        mock_cls.return_value.stats.side_effect = LensConnectionError("Connection refused")

        with patch("lattice_lens.store.lens_store.LensStore", mock_cls):
            result = runner.invoke(app, ["lens", "connect", "http://bad-host:9999/mcp"])

        # Should exit with error
        assert result.exit_code != 0 or "Error" in result.output

    def test_connect_writable_flag(self, cli_dir):
        """lens connect --writable should set writable: true in .lens file."""
        mock_store = MagicMock()
        mock_store.stats.return_value = {"total": 5, "backend": "yaml"}

        with patch("lattice_lens.store.lens_store.LensStore", return_value=mock_store):
            result = runner.invoke(
                app, ["lens", "connect", "--writable", "http://localhost:8080/mcp"]
            )

        assert result.exit_code == 0
        assert "writable" in result.output

        # Read back and verify
        from lattice_lens.lens import read_lens_file

        config = read_lens_file(cli_dir / LATTICE_DIR)
        assert config is not None
        assert config.writable is True

    def test_connect_project_flag(self, cli_dir):
        """lens connect --project should set project in .lens file."""
        mock_store = MagicMock()
        mock_store.stats.return_value = {"total": 5, "backend": "yaml"}

        with patch("lattice_lens.store.lens_store.LensStore", return_value=mock_store):
            result = runner.invoke(
                app,
                [
                    "lens",
                    "connect",
                    "--project",
                    "my-app",
                    "http://localhost:8080/mcp",
                ],
            )

        assert result.exit_code == 0

        from lattice_lens.lens import read_lens_file

        config = read_lens_file(cli_dir / LATTICE_DIR)
        assert config is not None
        assert config.project == "my-app"

    def test_connect_rejects_existing_full_lattice(self, cli_dir):
        """lens connect should fail if a full lattice already exists."""
        lattice_root = cli_dir / LATTICE_DIR
        lattice_root.mkdir()
        facts_dir = lattice_root / "facts"
        facts_dir.mkdir()
        # Create a dummy fact file
        (facts_dir / "ADR-01.yaml").write_text("code: ADR-01\n")

        result = runner.invoke(app, ["lens", "connect", "http://localhost:8080/mcp"])
        assert result.exit_code != 0


class TestLensStatus:
    def test_status_shows_config(self, lens_dir):
        """lens status should display lens configuration."""
        mock_store = MagicMock()
        mock_store.stats.return_value = {
            "total": 42,
            "backend": "yaml",
            "by_status": {"Active": 30, "Draft": 12},
        }

        with patch("lattice_lens.store.lens_store.LensStore", return_value=mock_store):
            result = runner.invoke(app, ["lens", "status"])

        assert result.exit_code == 0
        assert "localhost:8080" in result.output
        assert "sse" in result.output
        assert "read-only" in result.output

    def test_status_no_lens_file(self, cli_dir):
        """lens status should error when not in lens mode."""
        # Create .lattice/ but no .lens file
        lattice_root = cli_dir / LATTICE_DIR
        lattice_root.mkdir()

        result = runner.invoke(app, ["lens", "status"])
        assert result.exit_code != 0

    def test_status_no_lattice_dir(self, cli_dir):
        """lens status should error when no .lattice/ directory."""
        result = runner.invoke(app, ["lens", "status"])
        assert result.exit_code != 0


class TestLensDisconnect:
    def test_disconnect_removes_lens_file(self, lens_dir):
        """lens disconnect should remove .lens file."""
        result = runner.invoke(app, ["lens", "disconnect"])

        assert result.exit_code == 0
        assert "Disconnected" in result.output
        lens_path = lens_dir / LATTICE_DIR / LENS_FILE
        assert not lens_path.exists()

    def test_disconnect_no_lens_file(self, cli_dir):
        """lens disconnect should error when not in lens mode."""
        lattice_root = cli_dir / LATTICE_DIR
        lattice_root.mkdir()

        result = runner.invoke(app, ["lens", "disconnect"])
        assert result.exit_code != 0

    def test_disconnect_cleans_empty_lattice_dir(self, cli_dir):
        """lens disconnect should remove empty .lattice/ directory."""
        lattice_root = cli_dir / LATTICE_DIR
        lattice_root.mkdir()
        config = LensConfig(endpoint="http://localhost:8080/mcp")
        write_lens_file(lattice_root, config)

        result = runner.invoke(app, ["lens", "disconnect"])

        assert result.exit_code == 0
        # .lattice/ should be removed since it's empty
        assert not lattice_root.exists()


class TestLensModeGuards:
    """Test that incompatible commands fail in lens mode."""

    def test_seed_blocked_in_lens_mode(self, lens_dir):
        result = runner.invoke(app, ["seed"])
        assert result.exit_code != 0
        assert "not available in lens mode" in result.output or "lens mode" in result.output

    def test_serve_blocked_in_lens_mode(self, lens_dir):
        result = runner.invoke(app, ["serve"])
        assert result.exit_code != 0
        assert "not available in lens mode" in result.output or "lens mode" in result.output

    def test_diff_blocked_in_lens_mode(self, lens_dir):
        result = runner.invoke(app, ["diff"])
        assert result.exit_code != 0
        assert "not available in lens mode" in result.output or "lens mode" in result.output

    def test_log_blocked_in_lens_mode(self, lens_dir):
        result = runner.invoke(app, ["log"])
        assert result.exit_code != 0
        assert "not available in lens mode" in result.output or "lens mode" in result.output

    def test_reindex_blocked_in_lens_mode(self, lens_dir):
        result = runner.invoke(app, ["reindex"])
        assert result.exit_code != 0
        assert "not available in lens mode" in result.output or "lens mode" in result.output

    def test_upgrade_blocked_in_lens_mode(self, lens_dir):
        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code != 0
        assert "not available in lens mode" in result.output or "lens mode" in result.output
