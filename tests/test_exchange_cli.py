"""CLI tests for `lattice export` and `lattice import` commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lattice_lens.cli.main import app

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


class TestExportCommand:
    def test_export_json_stdout(self, seeded_dir: Path):
        result = runner.invoke(app, ["export"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 12

    def test_export_json_to_file(self, seeded_dir: Path):
        out = seeded_dir / "facts.json"
        result = runner.invoke(app, ["export", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert len(data) >= 12

    def test_export_yaml_stdout(self, seeded_dir: Path):
        result = runner.invoke(app, ["export", "--format", "yaml"])
        assert result.exit_code == 0
        from ruamel.yaml import YAML

        yaml_rw = YAML()
        data = yaml_rw.load(result.output)
        assert isinstance(data, list)
        assert len(data) >= 12

    def test_export_invalid_format(self, seeded_dir: Path):
        result = runner.invoke(app, ["export", "--format", "xml"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_export_empty_lattice(self, initialized_dir: Path):
        result = runner.invoke(app, ["export"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


class TestImportCommand:
    def test_import_json_skip(self, seeded_dir: Path):
        # Export first
        out = seeded_dir / "export.json"
        runner.invoke(app, ["export", "--output", str(out)])

        # Import into same lattice — should skip all
        result = runner.invoke(app, ["import", str(out)])
        assert result.exit_code == 0
        assert "Import complete" in result.output
        assert "skipped" in result.output

    def test_import_json_overwrite(self, seeded_dir: Path):
        out = seeded_dir / "export.json"
        runner.invoke(app, ["export", "--output", str(out)])

        result = runner.invoke(app, ["import", str(out), "--strategy", "overwrite"])
        assert result.exit_code == 0
        assert "Import complete" in result.output
        assert "overwritten" in result.output

    def test_import_json_fail_strategy(self, seeded_dir: Path):
        out = seeded_dir / "export.json"
        runner.invoke(app, ["export", "--output", str(out)])

        result = runner.invoke(app, ["import", str(out), "--strategy", "fail"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_import_file_not_found(self, initialized_dir: Path):
        result = runner.invoke(app, ["import", "nonexistent.json"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_import_invalid_strategy(self, initialized_dir: Path):
        f = initialized_dir / "facts.json"
        f.write_text("[]")
        result = runner.invoke(app, ["import", str(f), "--strategy", "merge"])
        assert result.exit_code == 1
        assert "Invalid strategy" in result.output

    def test_import_unknown_extension(self, initialized_dir: Path):
        f = initialized_dir / "facts.csv"
        f.write_text("code,fact\nADR-01,test")
        result = runner.invoke(app, ["import", str(f)])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_import_with_explicit_format(self, seeded_dir: Path):
        # Export as JSON, save with .txt extension, import with --format json
        out = seeded_dir / "facts.txt"
        export_result = runner.invoke(app, ["export"])
        out.write_text(export_result.output)

        result = runner.invoke(app, ["import", str(out), "--format", "json"])
        assert result.exit_code == 0
        assert "Import complete" in result.output

    def test_import_with_validation_errors(self, initialized_dir: Path):
        """Import a file with an invalid fact — should report errors."""
        bad_data = json.dumps(
            [
                {
                    "code": "bad-code",
                    "layer": "WHY",
                    "type": "Test",
                    "fact": "x",
                    "tags": [],
                    "owner": "test",
                }
            ]
        )
        f = initialized_dir / "bad.json"
        f.write_text(bad_data)

        result = runner.invoke(app, ["import", str(f)])
        assert result.exit_code == 0
        assert "error" in result.output.lower()
