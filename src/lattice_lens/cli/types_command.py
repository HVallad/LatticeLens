"""lattice types — type registry management."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.services.type_service import (
    CANONICAL_TYPES,
    audit_types,
    get_type_description,
    get_type_name,
    read_type_registry,
)

console = Console()
err_console = Console(stderr=True)


def types(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    audit: bool = typer.Option(False, "--audit", help="Show facts with non-canonical types"),
):
    """Show type registry: canonical type mapping per code prefix."""
    store = require_lattice()

    if audit:
        _show_audit(store, as_json)
        return

    # Show the canonical type registry
    registry = read_type_registry(store.root) or CANONICAL_TYPES

    if as_json:
        print(json.dumps(registry, indent=2))
        return

    table = Table(title="Type Registry")
    table.add_column("Prefix", style="bold")
    table.add_column("Layer")
    table.add_column("Canonical Type")
    table.add_column("Description", style="dim")

    for layer, prefixes in registry.items():
        for prefix in prefixes:
            type_name = get_type_name(registry, layer, prefix)
            description = get_type_description(registry, layer, prefix) or ""
            table.add_row(prefix, layer, type_name, description)

    console.print(table)


def _show_audit(store, as_json: bool):
    """Show facts whose type doesn't match the canonical type for their prefix."""
    mismatches = audit_types(store)

    if as_json:
        print(json.dumps(mismatches, indent=2))
        return

    if not mismatches:
        console.print("[green]All facts use canonical types.[/green]")
        return

    table = Table(title="Type Mismatches")
    table.add_column("Code", style="bold")
    table.add_column("Layer")
    table.add_column("Current Type", style="red")
    table.add_column("Canonical Type", style="green")

    for m in mismatches:
        table.add_row(m["code"], m["layer"], m["current_type"], m["canonical_type"])

    console.print(table)
    console.print(
        f"\n[yellow]{len(mismatches)} fact(s)[/yellow] use non-canonical types. "
        "Consider updating them to match the type registry."
    )
