"""Tests for lens file model and helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lattice_lens.lens import (
    LensConfig,
    LensModeError,
    read_lens_file,
    remove_lens_file,
    write_lens_file,
)


class TestLensConfig:
    def test_defaults(self):
        config = LensConfig(endpoint="http://localhost:8080/mcp")
        assert config.version == "1.0"
        assert config.transport == "sse"
        assert config.writable is False
        assert config.project is None

    def test_writable(self):
        config = LensConfig(endpoint="http://localhost:8080/mcp", writable=True)
        assert config.writable is True

    def test_project_scoped(self):
        config = LensConfig(
            endpoint="http://localhost:8080/mcp", project="my-project"
        )
        assert config.project == "my-project"

    def test_rejects_empty_endpoint(self):
        with pytest.raises(ValidationError):
            LensConfig(endpoint="")

    def test_rejects_invalid_transport(self):
        with pytest.raises(ValidationError):
            LensConfig(endpoint="http://localhost:8080/mcp", transport="websocket")

    def test_rejects_non_url_endpoint(self):
        with pytest.raises(ValidationError):
            LensConfig(endpoint="just-a-hostname")

    def test_accepts_https(self):
        config = LensConfig(endpoint="https://lattice.company.com/mcp")
        assert config.endpoint == "https://lattice.company.com/mcp"

    def test_accepts_absolute_path_for_stdio(self):
        config = LensConfig(endpoint="/usr/bin/lattice", transport="stdio")
        assert config.endpoint == "/usr/bin/lattice"


class TestLensFileIO:
    def test_write_and_read(self, tmp_path):
        lattice_root = tmp_path / ".lattice"
        lattice_root.mkdir()

        original = LensConfig(
            endpoint="http://localhost:8080/mcp",
            writable=True,
            project="test-project",
        )
        write_lens_file(lattice_root, original)

        loaded = read_lens_file(lattice_root)
        assert loaded is not None
        assert loaded.endpoint == original.endpoint
        assert loaded.writable == original.writable
        assert loaded.project == original.project
        assert loaded.transport == original.transport

    def test_read_missing(self, tmp_path):
        lattice_root = tmp_path / ".lattice"
        lattice_root.mkdir()

        result = read_lens_file(lattice_root)
        assert result is None

    def test_remove_existing(self, tmp_path):
        lattice_root = tmp_path / ".lattice"
        lattice_root.mkdir()

        config = LensConfig(endpoint="http://localhost:8080/mcp")
        write_lens_file(lattice_root, config)

        assert remove_lens_file(lattice_root) is True
        assert read_lens_file(lattice_root) is None

    def test_remove_nonexistent(self, tmp_path):
        lattice_root = tmp_path / ".lattice"
        lattice_root.mkdir()

        assert remove_lens_file(lattice_root) is False


class TestLensModeError:
    def test_is_exception(self):
        with pytest.raises(LensModeError):
            raise LensModeError("test error")
