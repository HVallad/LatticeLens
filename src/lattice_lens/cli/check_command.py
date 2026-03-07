"""lattice check — CI-friendly integrity gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import load_config
from lattice_lens.services.check_service import CheckResult, run_check

console = Console()
err_console = Console(stderr=True)


def _print_text(result: CheckResult) -> None:
    """Rich console output (default)."""
    if result.errors:
        console.print(f"\n[red]Errors ({len(result.errors)}):[/red]")
        for item in result.errors:
            loc = ""
            if item.file:
                loc = f" ({item.file}"
                if item.line:
                    loc += f":{item.line}"
                loc += ")"
            console.print(f"  [red]\u2717[/red] {item.message}{loc}")

    if result.warnings:
        console.print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
        for item in result.warnings:
            loc = ""
            if item.file:
                loc = f" ({item.file}"
                if item.line:
                    loc += f":{item.line}"
                loc += ")"
            console.print(f"  [yellow]\u2022[/yellow] {item.message}{loc}")

    if result.coverage_pct is not None:
        console.print(f"\nCoverage: {result.coverage_pct:.1f}%")


def _print_json(result: CheckResult, passed: bool) -> None:
    """Machine-readable JSON output."""
    data = {
        "passed": passed,
        "errors": [{"message": i.message, "file": i.file, "line": i.line} for i in result.errors],
        "warnings": [
            {"message": i.message, "file": i.file, "line": i.line} for i in result.warnings
        ],
        "coverage_pct": result.coverage_pct,
    }
    sys.stdout.write(json.dumps(data, indent=2) + "\n")


def _print_github(result: CheckResult) -> None:
    """GitHub Actions annotation format."""
    for item in result.errors:
        parts = ["::error"]
        attrs = []
        if item.file:
            attrs.append(f"file={item.file}")
        if item.line:
            attrs.append(f"line={item.line}")
        if attrs:
            parts[0] += " " + ",".join(attrs)
        sys.stdout.write(f"{parts[0]}::{item.message}\n")

    for item in result.warnings:
        parts = ["::warning"]
        attrs = []
        if item.file:
            attrs.append(f"file={item.file}")
        if item.line:
            attrs.append(f"line={item.line}")
        if attrs:
            parts[0] += " " + ",".join(attrs)
        sys.stdout.write(f"{parts[0]}::{item.message}\n")


def check(
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as errors"),
    stale_is_error: bool = typer.Option(
        False, "--stale-is-error", help="Treat stale facts as errors"
    ),
    reconcile_path: Optional[Path] = typer.Option(
        None, "--reconcile", help="Run reconciliation against codebase at PATH"
    ),
    include: Optional[list[str]] = typer.Option(
        None, "--include", help="Glob patterns for reconciliation"
    ),
    exclude: Optional[list[str]] = typer.Option(
        None, "--exclude", help="Glob exclusions for reconciliation"
    ),
    min_coverage: int = typer.Option(
        0, "--min-coverage", help="Minimum coverage %% (requires --reconcile)"
    ),
    output_format: str = typer.Option("text", "--format", help="Output format: text, json, github"),
):
    """CI gate: run all integrity checks and exit 0 (pass) or 1 (fail)."""
    store = require_lattice()

    # Load config-file defaults, CLI flags override
    config = load_config(store.root)
    check_config = config.get("check", {})

    effective_strict = strict or check_config.get("strict", False)
    effective_stale = stale_is_error or check_config.get("stale_is_error", False)
    effective_min_cov = min_coverage or check_config.get("min_coverage", 0)

    if reconcile_path is None:
        cfg_path = check_config.get("reconcile_path")
        if cfg_path:
            reconcile_path = Path(cfg_path)

    if min_coverage and not reconcile_path:
        err_console.print("[red]Error:[/red] --min-coverage requires --reconcile")
        raise typer.Exit(1)

    result = run_check(
        store,
        stale_is_error=effective_stale,
        reconcile_path=reconcile_path,
        include_patterns=include,
        exclude_patterns=exclude,
        min_coverage=effective_min_cov,
    )

    passed = not result.failed(strict=effective_strict)

    # Render output
    if output_format == "json":
        _print_json(result, passed)
    elif output_format == "github":
        _print_github(result)
    else:
        _print_text(result)
        if passed:
            console.print("\n[green]Check passed.[/green]")
        else:
            n_err = len(result.errors)
            n_warn = len(result.warnings)
            console.print(f"\n[red]Check failed.[/red] {n_err} error(s), {n_warn} warning(s).")

    if not passed:
        raise typer.Exit(1)
