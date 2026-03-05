"""lattice status — display lattice summary."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import HISTORY_DIR

console = Console()


def status():
    """Show lattice backend, fact counts, and staleness."""
    store = require_lattice()
    stats = store.stats()

    console.print(f"[bold]Backend:[/bold] {stats['backend']}")
    console.print(f"[bold]Total facts:[/bold] {stats['total']}")

    # By layer
    if stats["by_layer"]:
        table = Table(title="By Layer")
        table.add_column("Layer")
        table.add_column("Count", justify="right")
        for layer, count in sorted(stats["by_layer"].items()):
            table.add_row(layer, str(count))
        console.print(table)

    # By status
    if stats["by_status"]:
        table = Table(title="By Status")
        table.add_column("Status")
        table.add_column("Count", justify="right")
        for st, count in sorted(stats["by_status"].items()):
            table.add_row(st, str(count))
        console.print(table)

    # Stale
    if stats["stale"] > 0:
        console.print(f"[yellow]Stale facts:[/yellow] {stats['stale']}")
    else:
        console.print("[green]No stale facts.[/green]")

    # Last changelog entry
    changelog = store.history_dir / "changelog.jsonl"
    if changelog.exists():
        lines = changelog.read_text().strip().splitlines()
        if lines:
            last = json.loads(lines[-1])
            console.print(f"[bold]Last change:[/bold] {last['timestamp']} — {last['action']} {last['code']}")
