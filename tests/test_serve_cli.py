"""Tests for the lattice serve CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from lattice_lens.cli.main import app

runner = CliRunner()


class TestServeCli:
    def test_no_lattice_errors(self, tmp_path, monkeypatch):
        """Without .lattice/, serve should exit with error."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["serve"])
        assert result.exit_code != 0
        assert "No .lattice directory" in result.output or result.exit_code == 1

    def test_lens_mode_errors(self, tmp_path, monkeypatch):
        """Serve is not available in lens mode."""
        monkeypatch.chdir(tmp_path)
        with patch("lattice_lens.cli.serve_command.is_lens_mode", return_value=True):
            result = runner.invoke(app, ["serve"])
        assert result.exit_code != 0
        assert "not available in lens mode" in result.output

    def test_mcp_not_installed(self, tmp_path, monkeypatch):
        """Missing MCP package should give a helpful error."""
        lattice_dir = tmp_path / ".lattice"
        lattice_dir.mkdir()
        (lattice_dir / "config.yaml").write_text("schema_version: '0.7.0'\nbackend: yaml\n")
        (lattice_dir / "facts").mkdir()
        (lattice_dir / "history").mkdir()
        monkeypatch.chdir(tmp_path)

        with (
            patch("lattice_lens.cli.serve_command.is_lens_mode", return_value=False),
            patch("lattice_lens.cli.serve_command.find_lattice_root", return_value=lattice_dir),
        ):
            # Simulate ImportError when importing MCP server
            import builtins

            real_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "lattice_lens.mcp.server":
                    raise ImportError("No module named 'mcp'")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = runner.invoke(app, ["serve"])
        assert result.exit_code != 0
        assert "MCP dependencies not installed" in result.output

    def test_stdio_transport_default(self, tmp_path, monkeypatch):
        """Default invocation uses stdio transport."""
        lattice_dir = tmp_path / ".lattice"
        lattice_dir.mkdir()
        (lattice_dir / "config.yaml").write_text("schema_version: '0.7.0'\nbackend: yaml\n")
        (lattice_dir / "facts").mkdir()
        (lattice_dir / "history").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_server = MagicMock()
        with (
            patch("lattice_lens.cli.serve_command.is_lens_mode", return_value=False),
            patch("lattice_lens.cli.serve_command.find_lattice_root", return_value=lattice_dir),
            patch("lattice_lens.mcp.server.create_server", return_value=mock_server),
        ):
            runner.invoke(app, ["serve"])

        mock_server.run.assert_called_once_with(transport="stdio")

    def test_sse_transport_on_custom_host(self, tmp_path, monkeypatch):
        """Custom --host triggers SSE transport."""
        lattice_dir = tmp_path / ".lattice"
        lattice_dir.mkdir()
        (lattice_dir / "config.yaml").write_text("schema_version: '0.7.0'\nbackend: yaml\n")
        (lattice_dir / "facts").mkdir()
        (lattice_dir / "history").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_server = MagicMock()
        with (
            patch("lattice_lens.cli.serve_command.is_lens_mode", return_value=False),
            patch("lattice_lens.cli.serve_command.find_lattice_root", return_value=lattice_dir),
            patch("lattice_lens.mcp.server.create_server", return_value=mock_server),
        ):
            runner.invoke(app, ["serve", "--host", "0.0.0.0"])

        mock_server.run.assert_called_once_with(transport="sse")
        assert mock_server.settings.host == "0.0.0.0"

    def test_sse_transport_on_custom_port(self, tmp_path, monkeypatch):
        """Custom --port triggers SSE transport."""
        lattice_dir = tmp_path / ".lattice"
        lattice_dir.mkdir()
        (lattice_dir / "config.yaml").write_text("schema_version: '0.7.0'\nbackend: yaml\n")
        (lattice_dir / "facts").mkdir()
        (lattice_dir / "history").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_server = MagicMock()
        with (
            patch("lattice_lens.cli.serve_command.is_lens_mode", return_value=False),
            patch("lattice_lens.cli.serve_command.find_lattice_root", return_value=lattice_dir),
            patch("lattice_lens.mcp.server.create_server", return_value=mock_server),
        ):
            runner.invoke(app, ["serve", "--port", "8080"])

        mock_server.run.assert_called_once_with(transport="sse")
        assert mock_server.settings.port == 8080

    def test_writable_flag_passed(self, tmp_path, monkeypatch):
        """--writable flag is forwarded to create_server."""
        lattice_dir = tmp_path / ".lattice"
        lattice_dir.mkdir()
        (lattice_dir / "config.yaml").write_text("schema_version: '0.7.0'\nbackend: yaml\n")
        (lattice_dir / "facts").mkdir()
        (lattice_dir / "history").mkdir()
        monkeypatch.chdir(tmp_path)

        mock_server = MagicMock()
        with (
            patch("lattice_lens.cli.serve_command.is_lens_mode", return_value=False),
            patch("lattice_lens.cli.serve_command.find_lattice_root", return_value=lattice_dir),
            patch("lattice_lens.mcp.server.create_server", return_value=mock_server) as mock_create,
        ):
            runner.invoke(app, ["serve", "--writable"])

        mock_create.assert_called_once_with(lattice_dir, writable=True)
