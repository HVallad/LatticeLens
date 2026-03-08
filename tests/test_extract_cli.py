"""CLI tests for `lattice extract` command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, LATTICE_DIR
from tests.conftest import make_fact

runner = CliRunner()


@pytest.fixture
def cli_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def initialized_dir(cli_dir: Path):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    return cli_dir


@pytest.fixture
def seeded_dir(initialized_dir: Path):
    import shutil

    seed_src = Path(__file__).resolve().parent.parent / "seed"
    seed_dst = initialized_dir / "seed"
    if seed_src.exists():
        shutil.copytree(seed_src, seed_dst, dirs_exist_ok=True)

    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    return initialized_dir


class TestExtractPromptMode:
    def test_prompt_prints_system_prompt(self, initialized_dir: Path):
        """--prompt prints the extraction system prompt to stdout."""
        result = runner.invoke(app, ["extract", "--prompt"])
        assert result.exit_code == 0
        assert "knowledge extraction engine" in result.output

    def test_prompt_shows_existing_codes(self, seeded_dir: Path):
        """--prompt lists existing fact codes when the lattice has facts."""
        result = runner.invoke(app, ["extract", "--prompt"])
        assert result.exit_code == 0
        assert "Existing codes" in result.output

    def test_prompt_no_file_required(self, initialized_dir: Path):
        """--prompt does not require a file argument."""
        result = runner.invoke(app, ["extract", "--prompt"])
        assert result.exit_code == 0


class TestExtractErrors:
    def test_no_file_no_prompt_errors(self, initialized_dir: Path):
        """No file and no --prompt flag → error exit 1."""
        result = runner.invoke(app, ["extract", "--api-key", "fake-key"])
        assert result.exit_code == 1
        assert "file argument is required" in result.output.lower()

    def test_file_not_found(self, initialized_dir: Path):
        """Nonexistent file path → error exit 1."""
        result = runner.invoke(app, ["extract", "nonexistent.md", "--api-key", "fake-key"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_no_api_key(self, initialized_dir: Path, monkeypatch):
        """No API key and no env var → error exit 1."""
        monkeypatch.delenv("LATTICE_ANTHROPIC_API_KEY", raising=False)
        doc = initialized_dir / "test.md"
        doc.write_text("# Test\nSome content here for extraction.")
        result = runner.invoke(app, ["extract", str(doc)])
        assert result.exit_code == 1
        assert "api key" in result.output.lower()


class TestExtractDryRun:
    def test_dry_run_shows_facts_no_write(self, initialized_dir: Path):
        """--dry-run displays facts but does not write them."""
        doc = initialized_dir / "test.md"
        doc.write_text("# Architecture\nWe use microservices for scalability.")

        extracted = [
            make_fact(code="ADR-01", fact="We use microservices for scalability."),
            make_fact(code="ADR-02", fact="Services communicate via gRPC."),
        ]

        with patch(
            "lattice_lens.services.extract_service.extract_facts_from_document",
            return_value=extracted,
        ):
            result = runner.invoke(app, ["extract", str(doc), "--api-key", "fake-key", "--dry-run"])
        assert result.exit_code == 0
        assert "ADR-01" in result.output
        assert "ADR-02" in result.output
        assert "Dry run" in result.output

        # Verify no facts were written
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        assert not (facts_dir / "ADR-01.yaml").exists()

    def test_no_facts_extracted(self, initialized_dir: Path):
        """Empty extraction result shows message."""
        doc = initialized_dir / "test.md"
        doc.write_text("# Empty\nNothing useful here.")

        with patch(
            "lattice_lens.services.extract_service.extract_facts_from_document",
            return_value=[],
        ):
            result = runner.invoke(app, ["extract", str(doc), "--api-key", "fake-key", "--dry-run"])
        assert result.exit_code == 0
        assert "No facts extracted" in result.output


class TestExtractWrite:
    def test_write_creates_facts(self, initialized_dir: Path):
        """Without --dry-run, facts are written to the store after confirmation."""
        doc = initialized_dir / "test.md"
        doc.write_text("# Test\nSome architecture content here.")

        extracted = [make_fact(code="ADR-01", fact="Test architecture fact with enough length.")]

        with patch(
            "lattice_lens.services.extract_service.extract_facts_from_document",
            return_value=extracted,
        ):
            result = runner.invoke(app, ["extract", str(doc), "--api-key", "fake-key"], input="y\n")
        assert result.exit_code == 0
        assert "Created" in result.output

    def test_write_skips_existing_codes(self, initialized_dir: Path):
        """Existing codes are skipped during write (collision detection)."""
        # Pre-create a fact
        facts_dir = initialized_dir / LATTICE_DIR / FACTS_DIR
        existing = make_fact(code="ADR-01")
        from ruamel.yaml import YAML

        yaml_rw = YAML()
        yaml_rw.default_flow_style = False
        with open(facts_dir / "ADR-01.yaml", "w") as f:
            yaml_rw.dump(existing.model_dump(mode="json"), f)

        doc = initialized_dir / "test.md"
        doc.write_text("# Test\nSome content.")

        extracted = [
            make_fact(code="ADR-01", fact="Duplicate fact that should be skipped."),
            make_fact(code="ADR-02", fact="New fact that should be created successfully."),
        ]

        with patch(
            "lattice_lens.services.extract_service.extract_facts_from_document",
            return_value=extracted,
        ):
            result = runner.invoke(app, ["extract", str(doc), "--api-key", "fake-key"], input="y\n")
        assert result.exit_code == 0
        assert "Skipping ADR-01" in result.output
        assert "1 skipped" in result.output

    def test_write_aborted_by_user(self, initialized_dir: Path):
        """User declining confirmation aborts write."""
        doc = initialized_dir / "test.md"
        doc.write_text("# Test\nContent for extraction.")

        extracted = [make_fact(code="ADR-01")]

        with patch(
            "lattice_lens.services.extract_service.extract_facts_from_document",
            return_value=extracted,
        ):
            result = runner.invoke(app, ["extract", str(doc), "--api-key", "fake-key"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output


class TestExtractExtractionErrors:
    def test_extraction_value_error(self, initialized_dir: Path):
        """ValueError from extraction → error exit 1."""
        doc = initialized_dir / "test.md"
        doc.write_text("# Test\nSome content.")

        with patch(
            "lattice_lens.services.extract_service.extract_facts_from_document",
            side_effect=ValueError("Unsupported file format"),
        ):
            result = runner.invoke(app, ["extract", str(doc), "--api-key", "fake-key"])
        assert result.exit_code == 1
        assert "Unsupported file format" in result.output

    def test_extraction_generic_error(self, initialized_dir: Path):
        """Generic exception from extraction → error exit 1."""
        doc = initialized_dir / "test.md"
        doc.write_text("# Test\nSome content.")

        with patch(
            "lattice_lens.services.extract_service.extract_facts_from_document",
            side_effect=RuntimeError("API timeout"),
        ):
            result = runner.invoke(app, ["extract", str(doc), "--api-key", "fake-key"])
        assert result.exit_code == 1
        assert "Extraction failed" in result.output
