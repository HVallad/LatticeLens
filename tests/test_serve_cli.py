"""Tests for the lattice serve CLI command."""

from __future__ import annotations

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
