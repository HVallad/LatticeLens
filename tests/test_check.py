"""Tests for lattice check — CI gate command."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from typer.testing import CliRunner

from lattice_lens.cli.main import app
from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR
from lattice_lens.services.check_service import CheckItem, CheckResult, run_check
from lattice_lens.store.yaml_store import YamlFileStore
from tests.conftest import make_fact

runner = CliRunner()


def _setup_lattice(tmp_path: Path) -> Path:
    """Create a minimal .lattice/ directory."""
    lattice_root = tmp_path / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)
    (lattice_root / "config.yaml").write_text("version: 0.5.0\nbackend: yaml\n")
    return lattice_root


def _add_fact(lattice_root: Path, fact):
    store = YamlFileStore(lattice_root)
    store.create(fact)


# ── Service-level tests ──


class TestCheckResult:
    def test_ok_when_no_errors(self):
        r = CheckResult()
        assert r.ok
        assert not r.failed()

    def test_not_ok_with_errors(self):
        r = CheckResult(errors=[CheckItem(message="bad")])
        assert not r.ok
        assert r.failed()

    def test_strict_fails_on_warnings(self):
        r = CheckResult(warnings=[CheckItem(message="warn")])
        assert r.ok
        assert not r.failed(strict=False)
        assert r.failed(strict=True)


class TestRunCheck:
    def test_clean_lattice_passes(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)
        result = run_check(yaml_store)
        assert result.ok

    def test_validation_error_detected(self, yaml_store: YamlFileStore):
        # Write a malformed YAML file
        bad = yaml_store.facts_dir / "BAD-01.yaml"
        bad.write_text("{{invalid yaml: [")
        result = run_check(yaml_store)
        assert not result.ok
        assert any(
            "YAML parse error" in e.message or "Validation error" in e.message
            for e in result.errors
        )

    def test_stale_is_warning_by_default(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-01", review_by=date.today() - timedelta(days=1))
        yaml_store.create(fact)
        result = run_check(yaml_store)
        assert result.ok  # stale is a warning, not error
        assert any("stale" in w.message.lower() for w in result.warnings)

    def test_stale_is_error_when_flag_set(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-01", review_by=date.today() - timedelta(days=1))
        yaml_store.create(fact)
        result = run_check(yaml_store, stale_is_error=True)
        assert not result.ok
        assert any("stale" in e.message.lower() for e in result.errors)

    def test_reconcile_computes_coverage(self, yaml_store: YamlFileStore, tmp_path):
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)

        # Create source file referencing the fact
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("# ADR-01: architecture decision\n")

        result = run_check(yaml_store, reconcile_path=src)
        assert result.coverage_pct is not None

    def test_min_coverage_enforced(self, yaml_store: YamlFileStore, tmp_path):
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)

        # Source with no references → 0% coverage
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("# nothing here\n")

        result = run_check(yaml_store, reconcile_path=src, min_coverage=80)
        assert not result.ok
        assert any("coverage" in e.message.lower() for e in result.errors)

    def test_no_coverage_pct_without_reconcile(self, yaml_store: YamlFileStore):
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)
        result = run_check(yaml_store)
        assert result.coverage_pct is None


# ── CLI-level tests ──


class TestCheckCli:
    def test_check_clean_lattice(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "passed" in result.output.lower()

    def test_check_validation_error_exits_1(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        bad = lattice_root / FACTS_DIR / "BAD-01.yaml"
        bad.write_text("{{invalid yaml: [")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 1
        assert "failed" in result.output.lower()

    def test_check_strict_fails_on_warnings(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        _add_fact(
            lattice_root,
            make_fact(code="ADR-01", review_by=date.today() - timedelta(days=1)),
        )
        monkeypatch.chdir(tmp_path)

        # Without strict → passes (stale is just a warning)
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0

        # With strict → fails
        result = runner.invoke(app, ["check", "--strict"])
        assert result.exit_code == 1

    def test_check_stale_is_error_flag(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        _add_fact(
            lattice_root,
            make_fact(code="ADR-01", review_by=date.today() - timedelta(days=1)),
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--stale-is-error"])
        assert result.exit_code == 1

    def test_check_json_output(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["passed"] is True
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)

    def test_check_github_format(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        # Add a stale fact to trigger a warning
        _add_fact(
            lattice_root,
            make_fact(code="ADR-01", review_by=date.today() - timedelta(days=1)),
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--format", "github"])
        assert result.exit_code == 0
        assert "::warning" in result.output

    def test_check_github_format_errors(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        bad = lattice_root / FACTS_DIR / "BAD-01.yaml"
        bad.write_text("{{invalid yaml: [")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--format", "github"])
        assert result.exit_code == 1
        assert "::error" in result.output

    def test_check_no_lattice(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 1

    def test_check_min_coverage_requires_reconcile(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--min-coverage", "80"])
        assert result.exit_code == 1
        assert "requires" in result.output.lower()

    def test_check_with_reconcile(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))

        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("# ADR-01 reference\n")

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--reconcile", str(src)])
        assert result.exit_code == 0

    def test_check_json_with_reconcile(self, tmp_path, monkeypatch):
        lattice_root = _setup_lattice(tmp_path)
        _add_fact(lattice_root, make_fact(code="ADR-01"))

        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("# ADR-01 reference\n")

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--reconcile", str(src), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "coverage_pct" in data
        assert data["coverage_pct"] is not None
