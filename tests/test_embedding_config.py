"""Tests for configurable embedding model feature."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR, load_config
from lattice_lens.services.embedding_service import (
    DEFAULT_MODEL,
    EMBEDDINGS_FILE,
    RECOMMENDED_MODELS,
    get_embedding_model,
)

runner = CliRunner()
yaml_rw = YAML()
yaml_rw.default_flow_style = False


@pytest.fixture
def lattice_dir(tmp_path: Path) -> Path:
    """Create a minimal .lattice/ directory with config.yaml."""
    lattice_root = tmp_path / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)

    config = {"version": "0.7.0", "backend": "yaml"}
    config_path = lattice_root / "config.yaml"
    with open(config_path, "w") as f:
        yaml_rw.dump(config, f)

    return lattice_root


# --- get_embedding_model tests ---


class TestGetEmbeddingModel:
    def test_default_when_no_config(self, tmp_path: Path):
        """Returns default model when config.yaml doesn't exist."""
        lattice_root = tmp_path / ".lattice"
        lattice_root.mkdir()
        assert get_embedding_model(lattice_root) == DEFAULT_MODEL

    def test_default_when_no_embedding_section(self, lattice_dir: Path):
        """Returns default model when embedding section is missing."""
        assert get_embedding_model(lattice_dir) == DEFAULT_MODEL

    def test_reads_configured_model(self, lattice_dir: Path):
        """Returns the model specified in config."""
        config = load_config(lattice_dir)
        config["embedding"] = {"model": "BAAI/bge-small-en-v1.5"}
        from lattice_lens.config import save_config

        save_config(lattice_dir, config)

        assert get_embedding_model(lattice_dir) == "BAAI/bge-small-en-v1.5"

    def test_default_when_empty_embedding_section(self, lattice_dir: Path):
        """Returns default when embedding section exists but model key is missing."""
        config = load_config(lattice_dir)
        config["embedding"] = {}
        from lattice_lens.config import save_config

        save_config(lattice_dir, config)

        assert get_embedding_model(lattice_dir) == DEFAULT_MODEL


# --- CLI config embedding tests ---


class TestConfigEmbeddingCLI:
    def test_show_current_model_default(self, lattice_dir: Path, monkeypatch):
        """Shows default model when nothing configured."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(app, ["config", "embedding"])
        assert result.exit_code == 0
        assert DEFAULT_MODEL in result.output
        assert "default" in result.output.lower()

    def test_show_current_model_custom(self, lattice_dir: Path, monkeypatch):
        """Shows custom model when configured."""
        monkeypatch.chdir(lattice_dir.parent)

        config = load_config(lattice_dir)
        config["embedding"] = {"model": "all-mpnet-base-v2"}
        from lattice_lens.config import save_config

        save_config(lattice_dir, config)

        result = runner.invoke(app, ["config", "embedding"])
        assert result.exit_code == 0
        assert "all-mpnet-base-v2" in result.output

    def test_show_current_model_json(self, lattice_dir: Path, monkeypatch):
        """JSON output for current model."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(app, ["config", "embedding", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["model"] == DEFAULT_MODEL
        assert data["default"] == DEFAULT_MODEL

    def test_list_models(self, lattice_dir: Path, monkeypatch):
        """--list shows recommended models table."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(app, ["config", "embedding", "--list"])
        assert result.exit_code == 0
        assert "Recommended" in result.output
        for m in RECOMMENDED_MODELS:
            assert m["name"] in result.output

    def test_list_models_json(self, lattice_dir: Path, monkeypatch):
        """--list --json outputs structured model list."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(app, ["config", "embedding", "--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "models" in data
        assert len(data["models"]) == len(RECOMMENDED_MODELS)
        assert data["current"] == DEFAULT_MODEL

    def test_set_model(self, lattice_dir: Path, monkeypatch):
        """--model changes the embedding model in config."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(app, ["config", "embedding", "--model", "BAAI/bge-small-en-v1.5"])
        assert result.exit_code == 0
        assert "BAAI/bge-small-en-v1.5" in result.output

        # Verify config was updated
        config = load_config(lattice_dir)
        assert config["embedding"]["model"] == "BAAI/bge-small-en-v1.5"

    def test_set_model_deletes_old_embeddings(self, lattice_dir: Path, monkeypatch):
        """Changing model deletes existing embeddings.json."""
        monkeypatch.chdir(lattice_dir.parent)

        # Create a fake embeddings file
        embeddings_path = lattice_dir / EMBEDDINGS_FILE
        embeddings_path.write_text('{"model": "all-MiniLM-L6-v2", "fact_codes": []}')
        assert embeddings_path.exists()

        result = runner.invoke(app, ["config", "embedding", "--model", "all-mpnet-base-v2"])
        assert result.exit_code == 0

        # Embeddings file should be deleted
        assert not embeddings_path.exists()
        assert "deleted" in result.output.lower() or "incompatible" in result.output.lower()

    def test_set_model_no_change(self, lattice_dir: Path, monkeypatch):
        """Setting same model is a no-op."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(app, ["config", "embedding", "--model", DEFAULT_MODEL])
        assert result.exit_code == 0
        assert "Already" in result.output or "Nothing" in result.output

    def test_set_model_json(self, lattice_dir: Path, monkeypatch):
        """--model --json returns structured output."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(
            app, ["config", "embedding", "--model", "all-mpnet-base-v2", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["changed"] is True
        assert data["model"] == "all-mpnet-base-v2"
        assert data["previous_model"] == DEFAULT_MODEL

    def test_reset_model(self, lattice_dir: Path, monkeypatch):
        """--reset reverts to default model."""
        monkeypatch.chdir(lattice_dir.parent)

        # First set a non-default model
        config = load_config(lattice_dir)
        config["embedding"] = {"model": "all-mpnet-base-v2"}
        from lattice_lens.config import save_config

        save_config(lattice_dir, config)

        result = runner.invoke(app, ["config", "embedding", "--reset"])
        assert result.exit_code == 0

        config = load_config(lattice_dir)
        assert config["embedding"]["model"] == DEFAULT_MODEL

    def test_reset_when_already_default(self, lattice_dir: Path, monkeypatch):
        """--reset when already default is a no-op."""
        monkeypatch.chdir(lattice_dir.parent)

        result = runner.invoke(app, ["config", "embedding", "--reset"])
        assert result.exit_code == 0
        assert "Already" in result.output or "Nothing" in result.output


# --- Staleness detection with model change ---


class TestModelStaleness:
    def test_load_rejects_different_model(self, lattice_dir: Path):
        """EmbeddingIndex.load returns False when cached model doesn't match."""
        from lattice_lens.services.embedding_service import EmbeddingIndex

        # Create a fake embeddings file with model A
        embeddings_path = lattice_dir / EMBEDDINGS_FILE
        data = {
            "model": "all-MiniLM-L6-v2",
            "built_at": "2024-01-01T00:00:00+00:00",
            "fact_count": 1,
            "fact_codes": ["ADR-01"],
            "checksums": {"ADR-01": "abc123"},
            "embeddings": {"ADR-01": [0.1] * 384},
        }
        with open(embeddings_path, "w") as f:
            json.dump(data, f)

        # Try to load with model B
        index = EmbeddingIndex(model_name="all-mpnet-base-v2")
        loaded = index.load(embeddings_path)
        assert loaded is False

    def test_load_accepts_same_model(self, lattice_dir: Path):
        """EmbeddingIndex.load returns True when cached model matches."""
        from lattice_lens.services.embedding_service import EmbeddingIndex

        embeddings_path = lattice_dir / EMBEDDINGS_FILE
        data = {
            "model": "all-MiniLM-L6-v2",
            "built_at": "2024-01-01T00:00:00+00:00",
            "fact_count": 1,
            "fact_codes": ["ADR-01"],
            "checksums": {"ADR-01": "abc123"},
            "embeddings": {"ADR-01": [0.1] * 384},
        }
        with open(embeddings_path, "w") as f:
            json.dump(data, f)

        index = EmbeddingIndex(model_name="all-MiniLM-L6-v2")
        loaded = index.load(embeddings_path)
        assert loaded is True


# --- RECOMMENDED_MODELS data integrity ---


class TestRecommendedModels:
    def test_default_model_in_list(self):
        """Default model must be in the recommended list."""
        names = [m["name"] for m in RECOMMENDED_MODELS]
        assert DEFAULT_MODEL in names

    def test_all_models_have_required_fields(self):
        """Each recommended model has name, dims, size, quality, speed."""
        required = {"name", "dims", "size", "quality", "speed"}
        for m in RECOMMENDED_MODELS:
            assert required.issubset(m.keys()), f"Missing fields in {m}"

    def test_at_least_three_models(self):
        """We should offer meaningful choice."""
        assert len(RECOMMENDED_MODELS) >= 3
