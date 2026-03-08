"""lattice context — role-based context assembly for agent prompts."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import ROLES_DIR
from lattice_lens.services.context_service import assemble_context, estimate_fact_tokens
from lattice_lens.services.graph_service import load_role_templates

console = Console()
err_console = Console(stderr=True)


def context(
    role: str = typer.Argument(help="Role name (matches .lattice/roles/{role}.yaml)"),
    budget: Optional[int] = typer.Option(
        None, "--budget", help="Token budget (omit for unlimited)"
    ),
    project: Optional[str] = typer.Option(None, "--project", help="Filter facts by project scope"),
    depth: Optional[int] = typer.Option(
        None, "--depth", help="Graph traversal depth (0=off, 1=default, -1=unbounded)"
    ),
    as_json: bool = typer.Option(False, "--json", help="Output assembled context as JSON"),
):
    """Assemble governed, token-budgeted facts for an agent role."""
    store = require_lattice()
    roles_dir = store.root / ROLES_DIR

    templates = load_role_templates(roles_dir)
    if not templates:
        err_console.print(
            "[red]Error:[/red] No role templates found in .lattice/roles/. "
            "Run [bold]lattice init[/bold] to create them."
        )
        raise typer.Exit(1)

    if role not in templates:
        available = ", ".join(sorted(templates.keys()))
        err_console.print(
            f"[red]Error:[/red] Role '{role}' not found. Available roles: {available}"
        )
        raise typer.Exit(1)

    template = templates[role]
    result = assemble_context(
        store.index, role, template, budget=budget, project=project, graph_depth=depth
    )

    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    # Rich output
    role_name = template.get("name", role)
    role_desc = template.get("description", "")

    header = f"[bold]{role_name}[/bold]"
    if role_desc:
        header += f"\n[dim]{role_desc}[/dim]"

    summary_parts = [f"Facts loaded: [bold]{len(result.loaded_facts)}[/bold]"]
    summary_parts.append(f"Estimated tokens: [bold]{result.total_tokens}[/bold]")
    if result.budget is not None:
        summary_parts.append(f"Budget: {result.budget}")
        if result.budget_exhausted:
            summary_parts.append("[yellow]Budget exhausted[/yellow]")
    console.print(Panel(header + "\n" + " | ".join(summary_parts), border_style="blue"))

    if not result.loaded_facts:
        console.print("[dim]No facts matched this role's query.[/dim]")
        return

    # Facts table
    graph_set = set(result.graph_facts)
    table = Table(title="Assembled Facts")
    table.add_column("Code", style="bold")
    table.add_column("Layer")
    table.add_column("Type")
    table.add_column("Confidence")
    table.add_column("Source")
    table.add_column("Tokens", justify="right")

    for fact in result.loaded_facts:
        source = "graph" if fact.code in graph_set else "direct"
        table.add_row(
            fact.code,
            fact.layer.value,
            fact.type,
            fact.confidence.value,
            source,
            str(estimate_fact_tokens(fact)),
        )

    console.print(table)

    # Ref pointers
    if result.ref_pointers:
        console.print("\n[dim]Additional facts not loaded (REFS pointers):[/dim]")
        for ptr in result.ref_pointers:
            console.print(f"  [dim]- {ptr}[/dim]")
