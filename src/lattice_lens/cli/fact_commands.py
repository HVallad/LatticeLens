"""lattice fact — add, get, ls, edit, deprecate commands."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from ruamel.yaml import YAML

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import LAYER_PREFIXES
from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus
from lattice_lens.services.fact_service import (
    PROMOTION_TRANSITIONS,
    check_refs,
    create_fact,
    infer_layer,
    is_stale,
    next_code,
    promote_fact,
)

console = Console()
err_console = Console(stderr=True)
yaml_rw = YAML()
yaml_rw.default_flow_style = False

fact_app = typer.Typer(no_args_is_help=True)


@fact_app.command("add")
def fact_add(
    from_file: Optional[Path] = typer.Option(
        None, "--from", help="Create fact from YAML file"
    ),
):
    """Add a new fact (interactive or from file)."""
    store = require_lattice()

    if from_file:
        _add_from_file(store, from_file)
    else:
        _add_interactive(store)


def _add_from_file(store, path: Path):
    """Create a fact from a YAML file."""
    if not path.exists():
        err_console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(1)

    with open(path) as f:
        data = yaml_rw.load(f)

    try:
        fact = Fact(**data)
    except ValidationError as e:
        err_console.print(f"[red]Validation error:[/red]\n{e}")
        raise typer.Exit(1)

    # AUP-08: Warn when importing a fact that isn't Draft
    if fact.status != FactStatus.DRAFT:
        console.print(
            f"[yellow]Warning:[/yellow] Fact {fact.code} has status '{fact.status.value}'. "
            f"Per AUP-08, new facts should start as Draft and be promoted via "
            f"[bold]lattice fact promote[/bold]."
        )

    try:
        created, warnings = create_fact(store, fact)
    except FileExistsError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for w in warnings:
        console.print(f"[yellow]Warning:[/yellow] {w}")
    console.print(f"[green]Created[/green] {created.code} (v{created.version})")


def _add_interactive(store):
    """Interactive fact creation with Rich prompts."""
    console.print("[bold]Create a new fact[/bold]\n")

    # Code prefix
    all_prefixes = []
    for layer, prefixes in LAYER_PREFIXES.items():
        all_prefixes.extend(prefixes)
    console.print(f"Available prefixes: {', '.join(all_prefixes)}")
    prefix = typer.prompt("Code prefix (e.g., ADR, RISK)")
    prefix = prefix.upper().strip()

    layer_name = infer_layer(prefix)
    if layer_name is None:
        err_console.print(f"[red]Error:[/red] Unknown prefix '{prefix}'")
        raise typer.Exit(1)

    code = next_code(store, prefix)
    console.print(f"Auto-assigned code: [bold]{code}[/bold] (layer: {layer_name})")

    # Type
    fact_type = typer.prompt("Fact type (e.g., Architecture Decision Record)")

    # Fact text
    fact_text = typer.prompt("Fact text (min 10 chars)")

    # Tags
    tags_input = typer.prompt("Tags (comma-separated, min 2)")
    tags = [t.strip() for t in tags_input.split(",") if t.strip()]

    # Owner
    owner = typer.prompt("Owner")

    # Status
    status_str = typer.prompt("Status", default="Draft")

    # Confidence
    confidence_str = typer.prompt("Confidence", default="Confirmed")

    # Refs
    refs_input = typer.prompt("Refs (comma-separated codes, optional)", default="")
    refs = [r.strip() for r in refs_input.split(",") if r.strip()]

    # Review by
    review_by_str = typer.prompt("Review by (YYYY-MM-DD, optional)", default="")
    review_by = date.fromisoformat(review_by_str) if review_by_str else None

    try:
        fact = Fact(
            code=code,
            layer=FactLayer(layer_name),
            type=fact_type,
            fact=fact_text,
            tags=tags,
            status=FactStatus(status_str),
            confidence=FactConfidence(confidence_str),
            refs=refs,
            owner=owner,
            review_by=review_by,
        )
    except (ValidationError, ValueError) as e:
        err_console.print(f"[red]Validation error:[/red]\n{e}")
        raise typer.Exit(1)

    created, warnings = create_fact(store, fact)
    for w in warnings:
        console.print(f"[yellow]Warning:[/yellow] {w}")
    console.print(f"\n[green]Created[/green] {created.code} (v{created.version})")


@fact_app.command("get")
def fact_get(
    code: str = typer.Argument(help="Fact code (e.g., ADR-01)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Display a single fact."""
    store = require_lattice()
    fact = store.get(code)

    if fact is None:
        err_console.print(f"[red]Error:[/red] Fact '{code}' not found")
        raise typer.Exit(1)

    if as_json:
        print(json.dumps(fact.model_dump(mode="json"), indent=2))
        return

    # Rich panel display
    stale_warning = ""
    if is_stale(fact):
        stale_warning = "\n[bold red]⚠ STALE — past review_by date[/bold red]"

    content = (
        f"[bold]Layer:[/bold] {fact.layer.value}\n"
        f"[bold]Type:[/bold] {fact.type}\n"
        f"[bold]Status:[/bold] {fact.status.value}\n"
        f"[bold]Confidence:[/bold] {fact.confidence.value}\n"
        f"[bold]Version:[/bold] {fact.version}\n"
        f"[bold]Owner:[/bold] {fact.owner}\n"
        f"[bold]Tags:[/bold] {', '.join(fact.tags)}\n"
        f"[bold]Refs:[/bold] {', '.join(fact.refs) if fact.refs else '(none)'}\n"
        f"[bold]Review by:[/bold] {fact.review_by or '(not set)'}\n"
        f"[bold]Created:[/bold] {fact.created_at}\n"
        f"[bold]Updated:[/bold] {fact.updated_at}\n"
        f"\n{fact.fact}"
        f"{stale_warning}"
    )

    console.print(Panel(content, title=f"[bold]{fact.code}[/bold]", border_style="blue"))


@fact_app.command("ls")
def fact_ls(
    layer: Optional[str] = typer.Option(None, "--layer", help="Filter by layer"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    fact_type: Optional[str] = typer.Option(None, "--type", help="Filter by type"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List facts matching filters."""
    store = require_lattice()

    filters: dict = {}
    if layer:
        filters["layer"] = layer
    if tag:
        filters["tags_any"] = [tag]
    if status:
        filters["status"] = [status]
    else:
        filters["status"] = ["Active", "Draft", "Under Review"]
    if fact_type:
        filters["type"] = fact_type

    facts = store.list_facts(**filters)

    if as_json:
        print(json.dumps([f.model_dump(mode="json") for f in facts], indent=2))
        return

    if not facts:
        console.print("[dim]No facts found matching filters.[/dim]")
        return

    table = Table(title="Facts")
    table.add_column("Code", style="bold")
    table.add_column("Layer")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Tags")
    table.add_column("Ver", justify="right")

    for f in sorted(facts, key=lambda x: x.code):
        tags_display = ", ".join(f.tags[:3])
        if len(f.tags) > 3:
            tags_display += f" (+{len(f.tags) - 3})"
        table.add_row(
            f.code,
            f.layer.value,
            f.type,
            f.status.value,
            tags_display,
            str(f.version),
        )

    console.print(table)


@fact_app.command("edit")
def fact_edit(
    code: str = typer.Argument(help="Fact code to edit"),
):
    """Open a fact in $EDITOR, validate on save."""
    store = require_lattice()
    fact = store.get(code)

    if fact is None:
        err_console.print(f"[red]Error:[/red] Fact '{code}' not found")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "notepad"))

    # Write current fact to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix=f"{code}_", delete=False
    ) as tmp:
        yaml_rw.dump(fact.model_dump(mode="json"), tmp)
        tmp_path = tmp.name

    try:
        while True:
            subprocess.run([editor, tmp_path], check=True)

            # Read back and validate
            with open(tmp_path) as f:
                data = yaml_rw.load(f)

            try:
                updated_fact = Fact(**data)
            except ValidationError as e:
                err_console.print(f"[red]Validation error:[/red]\n{e}")
                retry = typer.confirm("Re-edit?", default=True)
                if not retry:
                    console.print("[yellow]Aborted.[/yellow]")
                    raise typer.Exit(0)
                continue

            # Ensure code hasn't changed
            if updated_fact.code != code:
                err_console.print("[red]Error:[/red] Code cannot be changed")
                retry = typer.confirm("Re-edit?", default=True)
                if not retry:
                    console.print("[yellow]Aborted.[/yellow]")
                    raise typer.Exit(0)
                continue

            # Compute changes
            old_data = fact.model_dump(mode="json")
            new_data = updated_fact.model_dump(mode="json")
            changes = {
                k: v for k, v in new_data.items()
                if k not in ("version", "updated_at", "created_at") and v != old_data.get(k)
            }

            if not changes:
                console.print("[dim]No changes detected.[/dim]")
                raise typer.Exit(0)

            # Block promotion-direction status changes — use `lattice fact promote`
            if "status" in changes:
                old_status = FactStatus(old_data["status"])
                new_status = FactStatus(changes["status"])
                if PROMOTION_TRANSITIONS.get(old_status) == new_status:
                    err_console.print(
                        f"[red]Error:[/red] Cannot promote {code} via edit. "
                        f"Use [bold]lattice fact promote {code} --reason \"...\"[/bold] "
                        f"to transition {old_status.value} → {new_status.value}."
                    )
                    retry = typer.confirm("Re-edit?", default=True)
                    if not retry:
                        console.print("[yellow]Aborted.[/yellow]")
                        raise typer.Exit(0)
                    continue

            result = store.update(code, changes, "Edited via CLI")
            warnings = check_refs(store, result.refs)
            for w in warnings:
                console.print(f"[yellow]Warning:[/yellow] {w}")
            console.print(
                f"[green]Updated[/green] {result.code} (v{result.version})"
            )
            break
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@fact_app.command("promote")
def fact_promote(
    code: str = typer.Argument(help="Fact code to promote"),
    reason: str = typer.Option(..., "--reason", help="Reason for promotion"),
):
    """Promote a fact: Draft -> Under Review -> Active."""
    store = require_lattice()

    try:
        result = promote_fact(store, code, reason)
    except FileNotFoundError:
        err_console.print(f"[red]Error:[/red] Fact '{code}' not found")
        raise typer.Exit(1)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f"[green]Promoted[/green] {result.code} to {result.status.value} "
        f"(v{result.version}): {reason}"
    )


@fact_app.command("deprecate")
def fact_deprecate(
    code: str = typer.Argument(help="Fact code to deprecate"),
    reason: str = typer.Option(..., "--reason", help="Reason for deprecation"),
):
    """Deprecate a fact (soft delete)."""
    store = require_lattice()

    if not store.exists(code):
        err_console.print(f"[red]Error:[/red] Fact '{code}' not found")
        raise typer.Exit(1)

    result = store.deprecate(code, reason)
    console.print(
        f"[green]Deprecated[/green] {result.code} (v{result.version}): {reason}"
    )
