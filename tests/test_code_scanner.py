"""Tests for code_scanner — fact reference and pattern detection."""

from __future__ import annotations

from pathlib import Path

from lattice_lens.services.code_scanner import (
    scan_for_architectural_patterns,
    scan_for_fact_references,
)


def _write_file(root: Path, relpath: str, content: str) -> Path:
    """Helper to create a source file in the temp directory."""
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


class TestScanForFactReferences:
    def test_finds_code_in_comments(self, tmp_path: Path):
        _write_file(tmp_path, "src/main.py", "# See ADR-03 for rationale\nx = 1\n")
        refs = scan_for_fact_references(tmp_path, ["ADR-03"])
        assert len(refs) == 1
        assert refs[0].code == "ADR-03"
        assert refs[0].line == 1
        assert refs[0].match_type == "explicit"

    def test_finds_code_in_strings(self, tmp_path: Path):
        _write_file(tmp_path, "src/check.py", 'msg = "per RISK-07 we must validate"\n')
        refs = scan_for_fact_references(tmp_path, ["RISK-07"])
        assert len(refs) == 1
        assert refs[0].code == "RISK-07"

    def test_ignores_non_code_patterns(self, tmp_path: Path):
        _write_file(tmp_path, "src/util.py", 'x = "ADR"\ny = "RISK"\n')
        refs = scan_for_fact_references(tmp_path, ["ADR-01", "RISK-01"])
        assert len(refs) == 0

    def test_finds_multiple_codes_same_file(self, tmp_path: Path):
        _write_file(
            tmp_path,
            "src/app.py",
            "# ADR-01 and ADR-02 apply here\n# Also see SP-03\n",
        )
        refs = scan_for_fact_references(tmp_path, ["ADR-01", "ADR-02", "SP-03"])
        codes = {r.code for r in refs}
        assert codes == {"ADR-01", "ADR-02", "SP-03"}

    def test_only_matches_known_codes(self, tmp_path: Path):
        _write_file(tmp_path, "src/app.py", "# ADR-99 is referenced\n")
        refs = scan_for_fact_references(tmp_path, ["ADR-01"])
        assert len(refs) == 0

    def test_include_pattern_filtering(self, tmp_path: Path):
        _write_file(tmp_path, "src/main.py", "# ADR-01\n")
        _write_file(tmp_path, "src/style.css", "/* ADR-01 */\n")
        refs = scan_for_fact_references(tmp_path, ["ADR-01"], include=["**/*.py"])
        assert len(refs) == 1
        assert refs[0].file.suffix == ".py"

    def test_exclude_pattern_filtering(self, tmp_path: Path):
        _write_file(tmp_path, "src/main.py", "# ADR-01\n")
        _write_file(tmp_path, ".venv/lib/dep.py", "# ADR-01\n")
        refs = scan_for_fact_references(tmp_path, ["ADR-01"])
        assert len(refs) == 1
        assert ".venv" not in str(refs[0].file)

    def test_context_captured(self, tmp_path: Path):
        _write_file(
            tmp_path,
            "src/app.py",
            "line1\nline2\n# ADR-01 here\nline4\nline5\n",
        )
        refs = scan_for_fact_references(tmp_path, ["ADR-01"])
        assert "line1" in refs[0].context
        assert "ADR-01" in refs[0].context


class TestScanForArchitecturalPatterns:
    def test_detects_framework_import(self, tmp_path: Path):
        _write_file(tmp_path, "src/main.py", "import typer\napp = typer.Typer()\n")
        patterns = scan_for_architectural_patterns(tmp_path)
        assert len(patterns) >= 1
        fw = [p for p in patterns if p.category == "framework"]
        assert len(fw) >= 1
        assert "typer" in fw[0].match

    def test_detects_validation_pattern(self, tmp_path: Path):
        _write_file(
            tmp_path,
            "src/models.py",
            "from pydantic import BaseModel\nclass Foo(BaseModel):\n    x: int\n",
        )
        patterns = scan_for_architectural_patterns(tmp_path)
        cats = {p.category for p in patterns}
        assert "validation" in cats

    def test_detects_storage_pattern(self, tmp_path: Path):
        _write_file(tmp_path, "src/db.py", "import sqlite3\nconn = sqlite3.connect(':memory:')\n")
        patterns = scan_for_architectural_patterns(tmp_path)
        storage = [p for p in patterns if p.category == "storage"]
        assert len(storage) >= 1

    def test_detects_security_pattern(self, tmp_path: Path):
        _write_file(tmp_path, "src/auth.py", "import hashlib\nh = hashlib.sha256(b'x')\n")
        patterns = scan_for_architectural_patterns(tmp_path)
        sec = [p for p in patterns if p.category == "security"]
        assert len(sec) >= 1

    def test_detects_error_handling_pattern(self, tmp_path: Path):
        _write_file(
            tmp_path,
            "src/errors.py",
            "class ValidationError(Exception):\n    pass\n",
        )
        patterns = scan_for_architectural_patterns(tmp_path)
        errs = [p for p in patterns if p.category == "error_handling"]
        assert len(errs) >= 1

    def test_exclude_filtering(self, tmp_path: Path):
        _write_file(tmp_path, "src/main.py", "import typer\n")
        _write_file(tmp_path, "__pycache__/cached.py", "import typer\n")
        patterns = scan_for_architectural_patterns(tmp_path)
        files = {str(p.file) for p in patterns}
        assert not any("__pycache__" in f for f in files)
