"""lattice graph — impact analysis, orphan detection, contradiction candidates."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import ROLES_DIR
from lattice_lens.store.index import FactIndex
from lattice_lens.services.graph_service import (
    find_contradiction_candidates,
    find_orphans,
    impact_analysis,
    load_role_templates,
)

console = Console()
err_console = Console(stderr=True)

graph_app = typer.Typer(no_args_is_help=True)


def _build_index(store) -> FactIndex:
    """Get the FactIndex from the store (works for all backends including lens)."""
    return store.index


@graph_app.command("impact")
def graph_impact(
    code: str = typer.Argument(help="Fact code to analyze (e.g., ADR-03)"),
    depth: int = typer.Option(3, "--depth", help="Max traversal depth"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show facts affected by changing a given fact."""
    store = require_lattice()
    index = _build_index(store)

    if index.get(code) is None:
        err_console.print(f"[red]Error:[/red] Fact '{code}' not found")
        raise typer.Exit(1)

    roles_dir = store.root / ROLES_DIR
    role_templates = load_role_templates(roles_dir)

    result = impact_analysis(index, code, max_depth=depth, role_templates=role_templates)

    if as_json:
        print(
            json.dumps(
                {
                    "source_code": result.source_code,
                    "directly_affected": result.directly_affected,
                    "transitively_affected": result.transitively_affected,
                    "all_affected": result.all_affected,
                    "affected_roles": result.affected_roles,
                    "depth_reached": result.depth_reached,
                },
                indent=2,
            )
        )
        return

    # Rich tree output
    fact = index.get(code)
    tree = Tree(f"[bold]{code}[/bold] ({fact.type})")

    if result.directly_affected:
        direct_branch = tree.add("[bold]Directly affected[/bold]")
        for c in result.directly_affected:
            f = index.get(c)
            if f:
                # Show how this fact references the source
                edges = index.edges_to(code)
                edge_label = ""
                if c in edges:
                    edge_label = f" [{edges[c].value}]"
                label = f"[cyan]{c}[/cyan]{edge_label} — {f.type}"
            else:
                label = f"[dim]{c}[/dim] (not found)"
            direct_branch.add(label)
    else:
        tree.add("[dim]No directly affected facts[/dim]")

    if result.transitively_affected:
        trans_branch = tree.add("[bold]Transitively affected[/bold]")
        for c in result.transitively_affected:
            f = index.get(c)
            label = f"[yellow]{c}[/yellow] — {f.type}" if f else f"[dim]{c}[/dim] (not found)"
            trans_branch.add(label)

    console.print(tree)

    if result.affected_roles:
        console.print(f"\n[bold]Affected roles:[/bold] {', '.join(result.affected_roles)}")
    else:
        console.print("\n[dim]No affected roles[/dim]")

    console.print(
        f"\n[dim]Total affected: {len(result.all_affected)} facts "
        f"(depth={result.depth_reached})[/dim]"
    )


@graph_app.command("orphans")
def graph_orphans(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List facts with no references in or out (disconnected from the graph)."""
    store = require_lattice()
    index = _build_index(store)

    orphan_codes = find_orphans(index)

    if as_json:
        print(json.dumps(orphan_codes, indent=2))
        return

    if not orphan_codes:
        console.print("[green]No orphaned facts found.[/green] All facts are connected.")
        return

    table = Table(title="Orphaned Facts")
    table.add_column("Code", style="bold")
    table.add_column("Layer")
    table.add_column("Type")
    table.add_column("Status")

    for c in orphan_codes:
        fact = index.get(c)
        if fact:
            table.add_row(c, fact.layer.value, fact.type, fact.status.value)
        else:
            table.add_row(c, "?", "?", "?")

    console.print(table)
    console.print(f"\n[dim]{len(orphan_codes)} orphaned fact(s) found.[/dim]")


@graph_app.command("contradictions")
def graph_contradictions(
    min_tags: int = typer.Option(2, "--min-tags", help="Minimum shared tags to flag"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Find pairs of active facts that may contradict each other."""
    store = require_lattice()
    index = _build_index(store)

    candidates = find_contradiction_candidates(index, min_shared_tags=min_tags)

    if as_json:
        print(
            json.dumps(
                [{"fact_a": a, "fact_b": b, "shared_tags": tags} for a, b, tags in candidates],
                indent=2,
            )
        )
        return

    if not candidates:
        console.print("[green]No contradiction candidates found.[/green]")
        return

    table = Table(title="Contradiction Candidates")
    table.add_column("Fact A", style="bold")
    table.add_column("Fact B", style="bold")
    table.add_column("Shared Tags")
    table.add_column("Layers")

    for a, b, shared_tags in candidates:
        fact_a = index.get(a)
        fact_b = index.get(b)
        layers = ""
        if fact_a and fact_b:
            layers = f"{fact_a.layer.value} / {fact_b.layer.value}"
        table.add_row(a, b, ", ".join(shared_tags), layers)

    console.print(table)
    console.print(
        f"\n[dim]{len(candidates)} candidate pair(s) found. "
        f"Review manually — these are not confirmed contradictions.[/dim]"
    )
