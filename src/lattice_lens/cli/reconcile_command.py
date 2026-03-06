"""lattice reconcile — bidirectional codebase reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.services.reconcile_service import reconcile, ReconciliationReport

console = Console()


def reconcile_cmd(
    path: Optional[Path] = typer.Option(
        None, "--path", help="Directory to scan (default: project root)."
    ),
    include: Optional[list[str]] = typer.Option(
        None, "--include", help="Glob patterns to include (default: **/*.py)."
    ),
    exclude: Optional[list[str]] = typer.Option(
        None, "--exclude", help="Glob patterns to exclude."
    ),
    llm: bool = typer.Option(
        False, "--llm", help="Enable LLM-assisted analysis (not yet implemented)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output report as JSON."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Show per-fact matching details."
    ),
):
    """Reconcile governance facts against the codebase."""
    store = require_lattice()

    # Default scan path: parent of .lattice/ (project root)
    codebase_root = path or store.root.parent

    try:
        report = reconcile(
            store,
            codebase_root,
            include_patterns=include,
            exclude_patterns=exclude,
            use_llm=llm,
        )
    except NotImplementedError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_output:
        _print_json(report)
    else:
        _print_rich(report, verbose)


def _print_json(report: ReconciliationReport):
    """Print machine-readable JSON report."""
    data = report.summary()
    data["findings"] = {
        "confirmed": [_finding_dict(f) for f in report.confirmed],
        "stale": [_finding_dict(f) for f in report.stale],
        "violated": [_finding_dict(f) for f in report.violated],
        "untracked": [_finding_dict(f) for f in report.untracked],
        "orphaned": [_finding_dict(f) for f in report.orphaned],
    }
    print(json.dumps(data, indent=2, default=str))


def _print_rich(report: ReconciliationReport, verbose: bool):
    """Print Rich-formatted reconciliation report."""
    # Summary table
    table = Table(title="Reconciliation Report")
    table.add_column("Category", style="bold")
    table.add_column("Description")
    table.add_column("Count", justify="right")

    table.add_row("[green]\u2713[/green]", "Confirmed facts", str(len(report.confirmed)))
    table.add_row("[yellow]\u26a0[/yellow]", "Stale facts (code diverged)", str(len(report.stale)))
    table.add_row("[red]\u2717[/red]", "Violated facts", str(len(report.violated)))
    table.add_row("[blue]![/blue]", "Untracked code patterns", str(len(report.untracked)))
    table.add_row("[dim]?[/dim]", "Orphaned facts (no code evidence)", str(len(report.orphaned)))
    table.add_section()
    table.add_row("", "Coverage", f"{report.coverage_pct:.1f}%")

    console.print(table)

    # Detailed findings
    if report.stale:
        console.print("\n[yellow]\u26a0 Stale Facts:[/yellow]")
        for f in report.stale:
            console.print(f"  {f.code} \u2014 {f.description}")
            if f.file:
                console.print(f"           {f.file}:{f.line}")

    if report.violated:
        console.print("\n[red]\u2717 Violated:[/red]")
        for f in report.violated:
            console.print(f"  {f.code} \u2014 {f.description}")
            if f.file:
                console.print(f"           {f.file}:{f.line}")

    if report.untracked:
        console.print("\n[blue]! Untracked Patterns:[/blue]")
        for f in report.untracked:
            console.print(f"  {f.description}")
            if f.file:
                console.print(f"             {f.file}:{f.line}")

    if verbose:
        if report.confirmed:
            console.print("\n[green]\u2713 Confirmed Facts:[/green]")
            for f in report.confirmed:
                console.print(f"  {f.code} \u2014 {f.description}")
                if f.file:
                    console.print(f"           {f.file}:{f.line}")

        if report.orphaned:
            console.print("\n[dim]? Orphaned Facts:[/dim]")
            for f in report.orphaned:
                console.print(f"  {f.code} \u2014 {f.description}")


def _finding_dict(f) -> dict:
    return {
        "category": f.category,
        "code": f.code,
        "description": f.description,
        "file": f.file,
        "line": f.line,
        "confidence": f.confidence,
        "evidence": f.evidence,
    }
