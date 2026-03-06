"""Tests for reconcile_service — bidirectional reconciliation engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import make_fact
from lattice_lens.models import FactStatus
from lattice_lens.services.reconcile_service import reconcile, ReconciliationReport


def _write_file(root: Path, relpath: str, content: str) -> Path:
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


class TestReconcileFactsToCode:
    def test_explicit_code_reference_found(self, yaml_store, tmp_path):
        """Comment '# ADR-03' in source detected as confirmed."""
        fact = make_fact(code="ADR-03", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-03: use Typer\nimport typer\n")

        report = reconcile(yaml_store, code_root)
        assert len(report.confirmed) == 1
        assert report.confirmed[0].code == "ADR-03"

    def test_missing_fact_detected(self, yaml_store, tmp_path):
        """Active fact with no code evidence → orphaned."""
        fact = make_fact(code="ADR-05", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# no references here\nx = 1\n")

        report = reconcile(yaml_store, code_root)
        assert len(report.orphaned) == 1
        assert report.orphaned[0].code == "ADR-05"

    def test_multiple_references_increase_confidence(self, yaml_store, tmp_path):
        """Multiple references to same fact should give higher confidence."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(
            code_root,
            "main.py",
            "# ADR-01\n# See ADR-01 for details\n# Per ADR-01\n",
        )

        report = reconcile(yaml_store, code_root)
        assert len(report.confirmed) == 1
        assert report.confirmed[0].confidence > 0.5

    def test_non_active_facts_excluded(self, yaml_store, tmp_path):
        """Only active facts are checked — draft/deprecated are skipped."""
        fact = make_fact(code="ADR-10", status=FactStatus.DRAFT)
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-10\n")

        report = reconcile(yaml_store, code_root)
        # Draft fact not in active list, so not checked
        assert len(report.confirmed) == 0
        assert len(report.orphaned) == 0


class TestReconcileCodeToFacts:
    def test_untracked_pattern_detected(self, yaml_store, tmp_path):
        """Import without ADR → untracked finding."""
        # No facts in store covering frameworks
        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "import flask\napp = flask.Flask(__name__)\n")

        report = reconcile(yaml_store, code_root)
        assert len(report.untracked) >= 1
        untracked_descs = [f.description.lower() for f in report.untracked]
        assert any("framework" in d for d in untracked_descs)

    def test_covered_pattern_not_flagged(self, yaml_store, tmp_path):
        """Pattern covered by existing fact should not be flagged."""
        fact = make_fact(
            code="ADR-01",
            status=FactStatus.ACTIVE,
            type="Architecture Decision Record",
            tags=["architecture", "cli"],
        )
        yaml_store.create(fact)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "import typer\n")

        report = reconcile(yaml_store, code_root)
        framework_untracked = [
            f for f in report.untracked if "framework" in f.description.lower()
        ]
        assert len(framework_untracked) == 0


class TestReconciliationReport:
    def test_report_summary_counts(self, yaml_store, tmp_path):
        """Summary dict has correct counts."""
        f1 = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        f2 = make_fact(code="ADR-02", status=FactStatus.ACTIVE, layer="WHY")
        yaml_store.create(f1)
        yaml_store.create(f2)

        code_root = tmp_path / "src"
        code_root.mkdir()
        _write_file(code_root, "main.py", "# ADR-01 referenced\n")

        report = reconcile(yaml_store, code_root)
        summary = report.summary()
        assert summary["confirmed"] == 1
        assert summary["orphaned"] == 1
        assert "coverage_pct" in summary

    def test_coverage_calculation(self):
        """coverage_pct = confirmed / total_checked * 100."""
        from lattice_lens.services.reconcile_service import Finding

        report = ReconciliationReport()
        report.confirmed = [
            Finding("confirmed", "A-1", "ok", "f.py", 1, 0.8, "x")
        ] * 3
        report.orphaned = [
            Finding("orphaned", "B-1", "missing", None, None, 0.6, "y")
        ]
        # 3 confirmed, 1 orphaned = 3/4 = 75%
        assert report.coverage_pct == 75.0
        assert report.summary()["coverage_pct"] == 75.0

    def test_empty_report(self):
        """Empty report has 0 coverage."""
        report = ReconciliationReport()
        assert report.coverage_pct == 0.0
        assert report.total_facts_checked == 0

    def test_exclude_patterns_respected(self, yaml_store, tmp_path):
        """Files matching exclude globs are skipped."""
        fact = make_fact(code="ADR-01", status=FactStatus.ACTIVE)
        yaml_store.create(fact)

        code_root = tmp_path / "project"
        code_root.mkdir()
        _write_file(code_root, "src/main.py", "# no refs\n")
        _write_file(code_root, "vendor/lib.py", "# ADR-01\n")

        report = reconcile(
            yaml_store,
            code_root,
            exclude_patterns=["**/vendor/**"],
        )
        # ADR-01 reference is in excluded vendor dir
        assert len(report.confirmed) == 0

    def test_use_llm_raises(self, yaml_store, tmp_path):
        """use_llm=True should raise NotImplementedError."""
        code_root = tmp_path / "src"
        code_root.mkdir()
        with pytest.raises(NotImplementedError):
            reconcile(yaml_store, code_root, use_llm=True)
