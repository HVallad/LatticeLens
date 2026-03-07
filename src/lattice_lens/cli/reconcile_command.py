"""lattice reconcile — bidirectional codebase reconciliation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import Settings
from lattice_lens.services.reconcile_service import (
    ReconciliationReport,
    reconcile,
    render_reconciliation_prompt,
)

console = Console()
err_console = Console(stderr=True)


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
        False, "--llm", help="Enable LLM-assisted analysis via Anthropic API."
    ),
    llm_prompt: bool = typer.Option(
        False,
        "--llm-prompt",
        help="Print reconciliation prompt to stdout for agent integration.",
    ),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", help="Model for LLM analysis."
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Anthropic API key (default: $LATTICE_ANTHROPIC_API_KEY).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output report as JSON."),
    verbose: bool = typer.Option(False, "--verbose", help="Show per-fact matching details."),
):
    """Reconcile governance facts against the codebase."""
    # Mutual exclusion check
    if llm and llm_prompt:
        err_console.print("[red]Error:[/red] --llm and --llm-prompt are mutually exclusive.")
        raise typer.Exit(1)

    store = require_lattice()

    # Default scan path: parent of .lattice/ (project root)
    codebase_root = path or store.root.parent

    # ── Prompt mode: run rule-based, render prompt, exit ──
    if llm_prompt:
        report = reconcile(
            store,
            codebase_root,
            include_patterns=include,
            exclude_patterns=exclude,
        )
        active_facts = store.list_facts(status=["Active"])
        prompt_text = render_reconciliation_prompt(report, active_facts)
        sys.stdout.buffer.write(prompt_text.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        return

    # ── Direct LLM mode: resolve API key ──
    if llm:
        resolved_key = api_key or Settings().anthropic_api_key
        if not resolved_key:
            err_console.print(
                "[red]Error:[/red] No API key provided. "
                "Set LATTICE_ANTHROPIC_API_KEY or use --api-key."
            )
            raise typer.Exit(1)
    else:
        resolved_key = None

    # ── Run reconciliation ──
    try:
        report = reconcile(
            store,
            codebase_root,
            include_patterns=include,
            exclude_patterns=exclude,
            use_llm=llm,
            api_key=resolved_key,
            model=model,
        )
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
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
            if verbose and f.llm_reasoning:
                console.print(f"           [dim]LLM: {f.llm_reasoning}[/dim]")

    if report.violated:
        console.print("\n[red]\u2717 Violated:[/red]")
        for f in report.violated:
            console.print(f"  {f.code} \u2014 {f.description}")
            if f.file:
                console.print(f"           {f.file}:{f.line}")
            if verbose and f.llm_reasoning:
                console.print(f"           [dim]LLM: {f.llm_reasoning}[/dim]")

    if report.untracked:
        console.print("\n[blue]! Untracked Patterns:[/blue]")
        for f in report.untracked:
            console.print(f"  {f.description}")
            if f.file:
                console.print(f"             {f.file}:{f.line}")
            if verbose and f.llm_reasoning:
                console.print(f"             [dim]LLM: {f.llm_reasoning}[/dim]")

    if verbose:
        if report.confirmed:
            console.print("\n[green]\u2713 Confirmed Facts:[/green]")
            for f in report.confirmed:
                console.print(f"  {f.code} \u2014 {f.description}")
                if f.file:
                    console.print(f"           {f.file}:{f.line}")
                if f.llm_reasoning:
                    console.print(f"           [dim]LLM: {f.llm_reasoning}[/dim]")

        if report.orphaned:
            console.print("\n[dim]? Orphaned Facts:[/dim]")
            for f in report.orphaned:
                console.print(f"  {f.code} \u2014 {f.description}")
                if f.llm_reasoning:
                    console.print(f"           [dim]LLM: {f.llm_reasoning}[/dim]")


def _finding_dict(f) -> dict:
    d = {
        "category": f.category,
        "code": f.code,
        "description": f.description,
        "file": f.file,
        "line": f.line,
        "confidence": f.confidence,
        "evidence": f.evidence,
    }
    if f.llm_reasoning:
        d["llm_reasoning"] = f.llm_reasoning
    return d
