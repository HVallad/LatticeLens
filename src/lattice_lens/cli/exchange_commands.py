"""lattice export / lattice import — fact interchange commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.services.exchange_service import (
    detect_format,
    export_facts,
    import_facts,
)

console = Console()
err_console = Console(stderr=True)


def export_cmd(
    format: str = typer.Option("json", "--format", help="Output format: json or yaml"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file (default: stdout)"
    ),
):
    """Export all facts as JSON or YAML."""
    store = require_lattice()

    try:
        result = export_facts(store, format=format)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if output:
        output.write_text(result, encoding="utf-8")
        err_console.print(
            f"[green]Exported[/green] to {output} ({format})"
        )
    else:
        print(result)


def import_cmd(
    file: Path = typer.Argument(..., help="File to import (.json or .yaml)"),
    format: Optional[str] = typer.Option(
        None, "--format", help="File format (auto-detected if omitted)"
    ),
    strategy: str = typer.Option(
        "skip", "--strategy", help="Merge strategy: skip, overwrite, fail"
    ),
):
    """Import facts from a JSON or YAML file."""
    if not file.exists():
        err_console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    if strategy not in ("skip", "overwrite", "fail"):
        err_console.print(
            f"[red]Error:[/red] Invalid strategy '{strategy}'. "
            "Use: skip, overwrite, fail"
        )
        raise typer.Exit(1)

    # Auto-detect format from extension if not specified
    resolved_format = format
    if resolved_format is None:
        try:
            resolved_format = detect_format(file)
        except ValueError as e:
            err_console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    store = require_lattice()
    data = file.read_text(encoding="utf-8")

    try:
        results = import_facts(store, data, format=resolved_format, strategy=strategy)
    except FileExistsError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f"[green]Import complete:[/green] "
        f"{results['created']} created, "
        f"{results['skipped']} skipped, "
        f"{results['overwritten']} overwritten."
    )
    if results["errors"]:
        err_console.print(f"\n[yellow]{len(results['errors'])} error(s):[/yellow]")
        for err in results["errors"]:
            err_console.print(f"  {err['code']}: {err['error']}")
