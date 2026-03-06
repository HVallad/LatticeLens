"""lattice tags — tag registry management."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.services.tag_service import build_tag_registry, write_tag_registry

console = Console()


def tags(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    rebuild: bool = typer.Option(False, "--rebuild", help="Regenerate tags.yaml from current facts"),
):
    """Show tag registry: all tags with usage counts and vocabulary categories."""
    store = require_lattice()
    registry = build_tag_registry(store)

    if rebuild:
        path = write_tag_registry(store.root, registry)
        console.print(f"[green]Rebuilt[/green] tag registry at [bold]{path}[/bold]")

    if as_json:
        print(json.dumps(registry, indent=2))
        return

    if not registry:
        console.print("[dim]No tags found.[/dim]")
        return

    table = Table(title="Tag Registry")
    table.add_column("Tag", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Category")

    for entry in registry:
        category = entry["category"]
        cat_style = "dim" if category == "free" else "cyan"
        table.add_row(entry["tag"], str(entry["count"]), f"[{cat_style}]{category}[/{cat_style}]")

    console.print(table)

    # Warn about free tags with 3+ usages per DG-07
    frequent_free = [e for e in registry if e["category"] == "free" and e["count"] >= 3]
    if frequent_free:
        console.print(
            f"\n[yellow]Note:[/yellow] {len(frequent_free)} free tag(s) appear in 3+ facts. "
            "Consider adding them to the controlled vocabulary (DG-07):"
        )
        for entry in frequent_free:
            console.print(f"  - {entry['tag']} ({entry['count']} uses)")
