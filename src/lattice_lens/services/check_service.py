"""CI check engine — composes validation + reconciliation into a single pass/fail."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lattice_lens.services.validate_service import validate_lattice
from lattice_lens.store.protocol import LatticeStore


@dataclass
class CheckItem:
    """A single check finding with optional file location for CI annotations."""

    message: str
    file: str | None = None
    line: int | None = None


@dataclass
class CheckResult:
    """Aggregated result from all check phases."""

    errors: list[CheckItem] = field(default_factory=list)
    warnings: list[CheckItem] = field(default_factory=list)
    coverage_pct: float | None = None  # None if reconciliation not run

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def failed(self, strict: bool = False) -> bool:
        """Return True if the check should fail.

        In strict mode, any warning is also a failure.
        """
        if self.errors:
            return True
        if strict and self.warnings:
            return True
        return False


_STALE_MARKER = "is stale"


def run_check(
    store: LatticeStore,
    *,
    stale_is_error: bool = False,
    reconcile_path: Path | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    min_coverage: int = 0,
) -> CheckResult:
    """Run all checks and return a structured result.

    Composes validate_lattice() and optionally reconcile() into a single
    CheckResult suitable for CI gating.
    """
    result = CheckResult()

    # --- Phase 1: Integrity validation ---
    val = validate_lattice(store.facts_dir)

    for msg in val.errors:
        result.errors.append(CheckItem(message=msg))

    for msg in val.warnings:
        if stale_is_error and _STALE_MARKER in msg.lower():
            result.errors.append(CheckItem(message=msg))
        else:
            result.warnings.append(CheckItem(message=msg))

    # --- Phase 2: Reconciliation (optional) ---
    if reconcile_path is not None:
        from lattice_lens.services.reconcile_service import reconcile

        report = reconcile(
            store,
            reconcile_path,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        )

        result.coverage_pct = report.coverage_pct

        # Violated findings are errors
        for finding in report.violated:
            result.errors.append(
                CheckItem(
                    message=f"Violated: {finding.code} — {finding.description}",
                    file=finding.file,
                    line=finding.line,
                )
            )

        # Orphaned facts are warnings (no code evidence)
        for finding in report.orphaned:
            result.warnings.append(
                CheckItem(
                    message=f"Orphaned: {finding.code} — {finding.description}",
                )
            )

        # Untracked patterns are warnings
        for finding in report.untracked:
            result.warnings.append(
                CheckItem(
                    message=f"Untracked: {finding.description}",
                    file=finding.file,
                    line=finding.line,
                )
            )

        # Coverage gate
        if min_coverage > 0 and report.coverage_pct < min_coverage:
            result.errors.append(
                CheckItem(
                    message=(
                        f"Coverage {report.coverage_pct:.1f}% is below "
                        f"minimum threshold {min_coverage}%"
                    ),
                )
            )

    return result
