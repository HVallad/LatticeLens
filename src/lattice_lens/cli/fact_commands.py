"""lattice fact — add, get, ls, edit, deprecate commands."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import date
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
    from_file: Optional[Path] = typer.Option(None, "--from", help="Create fact from YAML file"),
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

    # Refs — accepts "CODE" (defaults to relates) or "CODE:edge_type"
    refs_input = typer.prompt(
        "Refs (comma-separated, CODE or CODE:edge_type; optional)", default=""
    )
    refs: list[dict | str] = []
    for r in refs_input.split(","):
        r = r.strip()
        if not r:
            continue
        if ":" in r:
            ref_code, rel = r.split(":", 1)
            refs.append({"code": ref_code.strip(), "rel": rel.strip()})
        else:
            refs.append(r)

    # Review by
    review_by_str = typer.prompt("Review by (YYYY-MM-DD, optional)", default="")
    review_by = date.fromisoformat(review_by_str) if review_by_str else None

    # Projects
    projects_input = typer.prompt(
        "Projects (comma-separated, or group:name; empty for global)", default=""
    )
    projects = [p.strip() for p in projects_input.split(",") if p.strip()]

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
            projects=projects,
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

    # Track access (never let tracking failures break core functionality)
    try:
        from lattice_lens.services.access_service import get_tracker

        tracker = get_tracker(store.root)
        tracker.record_access(code, source="cli")
    except Exception:
        pass

    if as_json:
        print(json.dumps(fact.model_dump(mode="json"), indent=2))
        return

    # Rich panel display
    stale_warning = ""
    if is_stale(fact):
        stale_warning = "\n[bold red]⚠ STALE — past review_by date[/bold red]"

    projects_display = ", ".join(fact.projects) if fact.projects else "(global)"

    content = (
        f"[bold]Layer:[/bold] {fact.layer.value}\n"
        f"[bold]Type:[/bold] {fact.type}\n"
        f"[bold]Status:[/bold] {fact.status.value}\n"
        f"[bold]Confidence:[/bold] {fact.confidence.value}\n"
        f"[bold]Version:[/bold] {fact.version}\n"
        f"[bold]Owner:[/bold] {fact.owner}\n"
        f"[bold]Tags:[/bold] {', '.join(fact.tags)}\n"
        f"[bold]Refs:[/bold] {', '.join(f'{r.code} ({r.rel.value})' for r in fact.refs) if fact.refs else '(none)'}\n"
        f"[bold]Projects:[/bold] {projects_display}\n"
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
    project: Optional[str] = typer.Option(None, "--project", help="Filter by project scope"),
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
    if project:
        filters["project"] = project

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
    title: Optional[str] = typer.Option(None, "--title", help="Set fact text (non-interactive)"),
    body: Optional[str] = typer.Option(None, "--body", help="Alias for --title (set fact text)"),
    tags: Optional[str] = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
    layer: Optional[str] = typer.Option(None, "--layer", help="Set layer (WHY/GUARDRAILS/HOW)"),
    status: Optional[str] = typer.Option(None, "--status", help="Set status"),
    confidence: Optional[str] = typer.Option(None, "--confidence", help="Set confidence level"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Set owner"),
    fact_type: Optional[str] = typer.Option(None, "--type", help="Set fact type"),
    review_by: Optional[str] = typer.Option(
        None, "--review-by", help="Set review-by date (YYYY-MM-DD, or empty to clear)"
    ),
    refs: Optional[str] = typer.Option(
        None, "--refs", help="Comma-separated refs (CODE or CODE:edge_type, replaces existing)"
    ),
    projects: Optional[str] = typer.Option(
        None, "--projects", help="Comma-separated projects (replaces existing)"
    ),
    reason: Optional[str] = typer.Option(None, "--reason", help="Changelog reason for the edit"),
    as_json: bool = typer.Option(False, "--json", help="Output result as JSON"),
):
    """Edit a fact. With flags: non-interactive. Without flags: opens $EDITOR."""
    store = require_lattice()
    fact = store.get(code)

    if fact is None:
        err_console.print(f"[red]Error:[/red] Fact '{code}' not found")
        raise typer.Exit(1)

    # Collect flag-based changes
    flag_changes: dict = {}
    fact_text = title or body
    if fact_text is not None:
        flag_changes["fact"] = fact_text
    if tags is not None:
        flag_changes["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if layer is not None:
        flag_changes["layer"] = layer
    if status is not None:
        flag_changes["status"] = status
    if confidence is not None:
        flag_changes["confidence"] = confidence
    if owner is not None:
        flag_changes["owner"] = owner
    if fact_type is not None:
        flag_changes["type"] = fact_type
    if review_by is not None:
        flag_changes["review_by"] = date.fromisoformat(review_by) if review_by else None
    if refs is not None:
        parsed_refs: list[dict | str] = []
        for r in refs.split(","):
            r = r.strip()
            if not r:
                continue
            if ":" in r:
                ref_code, rel = r.split(":", 1)
                parsed_refs.append({"code": ref_code.strip(), "rel": rel.strip()})
            else:
                parsed_refs.append(r)
        flag_changes["refs"] = parsed_refs
    if projects is not None:
        flag_changes["projects"] = [p.strip() for p in projects.split(",") if p.strip()]

    # If any flags were provided, use non-interactive mode
    if flag_changes:
        _edit_non_interactive(store, fact, code, flag_changes, reason, as_json)
    else:
        _edit_interactive(store, fact, code, as_json)


def _edit_non_interactive(
    store, fact: Fact, code: str, changes: dict, reason: str | None, as_json: bool
):
    """Apply flag-based changes without interactive prompts."""
    # Validate the proposed changes by constructing the updated fact
    merged = fact.model_dump(mode="json")
    merged.update(changes)

    try:
        updated_fact = Fact(**merged)
    except ValidationError as e:
        err_console.print(f"[red]Validation error:[/red]\n{e}")
        raise typer.Exit(1)

    # Compute actual diff (some changes may be no-ops after normalization)
    old_data = fact.model_dump(mode="json")
    new_data = updated_fact.model_dump(mode="json")
    actual_changes = {
        k: v
        for k, v in new_data.items()
        if k not in ("version", "updated_at", "created_at") and v != old_data.get(k)
    }

    if not actual_changes:
        if as_json:
            print(json.dumps({"status": "no_changes", "code": code}))
        else:
            console.print("[dim]No changes detected.[/dim]")
        raise typer.Exit(0)

    # Block promotion-direction status changes — use `lattice fact promote`
    if "status" in actual_changes:
        old_status = FactStatus(old_data["status"])
        new_status = FactStatus(actual_changes["status"])
        if PROMOTION_TRANSITIONS.get(old_status) == new_status:
            err_console.print(
                f"[red]Error:[/red] Cannot promote {code} via edit. "
                f'Use [bold]lattice fact promote {code} --reason "..."[/bold] '
                f"to transition {old_status.value} -> {new_status.value}."
            )
            raise typer.Exit(1)

    edit_reason = reason or "Edited via CLI (non-interactive)"
    result = store.update(code, actual_changes, edit_reason)
    warnings = check_refs(store, result.refs)

    if as_json:
        output = result.model_dump(mode="json")
        output["_warnings"] = [str(w) for w in warnings]
        print(json.dumps(output, indent=2))
    else:
        for w in warnings:
            console.print(f"[yellow]Warning:[/yellow] {w}")
        console.print(f"[green]Updated[/green] {result.code} (v{result.version})")


def _edit_interactive(store, fact: Fact, code: str, as_json: bool):
    """Open a fact in $EDITOR, validate on save."""
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
                k: v
                for k, v in new_data.items()
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
                        f'Use [bold]lattice fact promote {code} --reason "..."[/bold] '
                        f"to transition {old_status.value} -> {new_status.value}."
                    )
                    retry = typer.confirm("Re-edit?", default=True)
                    if not retry:
                        console.print("[yellow]Aborted.[/yellow]")
                        raise typer.Exit(0)
                    continue

            result = store.update(code, changes, "Edited via CLI")
            warnings = check_refs(store, result.refs)

            if as_json:
                output = result.model_dump(mode="json")
                output["_warnings"] = [str(w) for w in warnings]
                print(json.dumps(output, indent=2))
            else:
                for w in warnings:
                    console.print(f"[yellow]Warning:[/yellow] {w}")
                console.print(f"[green]Updated[/green] {result.code} (v{result.version})")
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
    console.print(f"[green]Deprecated[/green] {result.code} (v{result.version}): {reason}")


@fact_app.command("stats")
def fact_stats(
    code: Optional[str] = typer.Argument(None, help="Specific fact code to show stats for"),
    cold: bool = typer.Option(False, "--cold", help="Show facts never accessed or stale"),
    hot: bool = typer.Option(False, "--hot", help="Show most accessed facts"),
    days: int = typer.Option(30, "--days", help="Days threshold for cold facts"),
    top: int = typer.Option(10, "--top", help="Number of top facts for --hot"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
):
    """Show access count statistics for facts."""
    from lattice_lens.services.access_service import get_tracker

    store = require_lattice()
    tracker = get_tracker(store.root)

    # Ensure all known facts appear in the output (even if never accessed)
    all_codes = store.all_codes()
    counts = tracker.get_counts()

    if code is not None:
        # Show stats for a specific fact
        if not store.exists(code):
            err_console.print(f"[red]Error:[/red] Fact '{code}' not found")
            raise typer.Exit(1)

        fact = store.get(code)
        entry = counts.get(
            code, {"count": 0, "last_accessed": None, "first_accessed": None, "sources": {}}
        )

        if as_json:
            print(json.dumps({"code": code, **entry}, indent=2))
            return

        sources_display = ", ".join(f"{k}:{v}" for k, v in sorted(entry.get("sources", {}).items()))

        content = (
            f"[bold]Count:[/bold] {entry['count']}\n"
            f"[bold]First accessed:[/bold] {entry.get('first_accessed') or 'never'}\n"
            f"[bold]Last accessed:[/bold] {entry.get('last_accessed') or 'never'}\n"
            f"[bold]Sources:[/bold] {sources_display or '(none)'}"
        )
        title = f"{code}"
        if fact:
            title += f" — {fact.type}"
        console.print(Panel(content, title=f"[bold]{title}[/bold]", border_style="blue"))
        return

    if cold:
        # Show cold facts
        cold_facts = tracker.get_cold_facts(threshold=0, days=days)

        # Also include facts that have never been tracked at all
        tracked_codes = set(counts.keys())
        for c in sorted(all_codes):
            if c not in tracked_codes:
                cold_facts.append(
                    {"code": c, "count": 0, "last_accessed": None, "days_since": None}
                )

        if as_json:
            print(json.dumps(cold_facts, indent=2))
            return

        if not cold_facts:
            console.print("[dim]No cold facts found.[/dim]")
            return

        table = Table(title=f"Cold Facts (threshold=0, days={days})")
        table.add_column("Code", style="bold")
        table.add_column("Title")
        table.add_column("Count", justify="right")
        table.add_column("Last Accessed")

        for item in cold_facts:
            fact = store.get(item["code"])
            title = fact.type if fact else "?"
            last = item.get("last_accessed") or "never"
            count_str = str(item["count"])
            style = "red" if item["count"] == 0 else "yellow"
            table.add_row(
                f"[{style}]{item['code']}[/{style}]",
                title,
                count_str,
                last if last == "never" else _relative_time(last),
            )

        console.print(table)
        return

    if hot:
        # Show hot facts
        hot_facts = tracker.get_hot_facts(top_k=top)

        if as_json:
            print(json.dumps(hot_facts, indent=2))
            return

        if not hot_facts:
            console.print("[dim]No access data recorded yet.[/dim]")
            return

        table = Table(title=f"Hot Facts (top {top})")
        table.add_column("Code", style="bold")
        table.add_column("Title")
        table.add_column("Count", justify="right")
        table.add_column("Last Accessed")
        table.add_column("Sources")

        for item in hot_facts:
            fact = store.get(item["code"])
            title = fact.type if fact else "?"
            sources = ", ".join(f"{k}:{v}" for k, v in sorted(item.get("sources", {}).items()))
            last = item.get("last_accessed") or "never"
            table.add_row(
                f"[green]{item['code']}[/green]",
                title,
                str(item["count"]),
                last if last == "never" else _relative_time(last),
                sources or "-",
            )

        console.print(table)
        return

    # Default: show all facts with their access counts
    rows: list[dict] = []
    for c in sorted(all_codes):
        entry = counts.get(c, {"count": 0, "last_accessed": None, "sources": {}})
        fact = store.get(c)
        rows.append(
            {
                "code": c,
                "title": fact.type if fact else "?",
                "count": entry.get("count", 0),
                "last_accessed": entry.get("last_accessed"),
                "sources": entry.get("sources", {}),
            }
        )

    if as_json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        console.print("[dim]No facts in lattice.[/dim]")
        return

    table = Table(title="Fact Access Statistics")
    table.add_column("Code", style="bold")
    table.add_column("Title")
    table.add_column("Count", justify="right")
    table.add_column("Last Accessed")
    table.add_column("Sources")

    for row in rows:
        sources = ", ".join(f"{k}:{v}" for k, v in sorted(row["sources"].items()))
        last = row["last_accessed"] or "never"
        count = row["count"]

        # Color coding: hot=green, cold=red, middle=default
        if count == 0:
            code_style = "red"
        elif count >= 10:
            code_style = "green"
        else:
            code_style = "yellow"

        table.add_row(
            f"[{code_style}]{row['code']}[/{code_style}]",
            row["title"],
            str(count),
            last if last == "never" else _relative_time(last),
            sources or "-",
        )

    console.print(table)


def _relative_time(iso_str: str) -> str:
    """Convert ISO timestamp to a human-readable relative time string."""
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = seconds // 60
            return f"{mins} min{'s' if mins != 1 else ''} ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            d = seconds // 86400
            return f"{d} day{'s' if d != 1 else ''} ago"
    except Exception:
        return iso_str
