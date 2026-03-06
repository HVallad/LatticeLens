"""lattice extract — LLM-powered fact extraction from documents."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import Settings

console = Console()
err_console = Console(stderr=True)


def extract(
    file: Path = typer.Argument(..., help="Path to document (.md, .txt, .docx)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview extracted facts without writing"
    ),
    model: str = typer.Option(
        "claude-sonnet-4-20250514", "--model", help="Extraction model"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Anthropic API key (default: $LATTICE_ANTHROPIC_API_KEY)",
    ),
):
    """Extract atomic facts from a document using an LLM."""
    # Resolve API key
    resolved_key = api_key or Settings().anthropic_api_key
    if not resolved_key:
        err_console.print(
            "[red]Error:[/red] No API key provided. "
            "Set LATTICE_ANTHROPIC_API_KEY or use --api-key."
        )
        raise typer.Exit(1)

    if not file.exists():
        err_console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    store = require_lattice()
    existing_codes = store.all_codes()

    try:
        from lattice_lens.services.extract_service import extract_facts_from_document
    except ImportError:
        err_console.print(
            "[red]Error:[/red] anthropic package not installed. "
            "Run: pip install lattice-lens[extract]"
        )
        raise typer.Exit(1)

    console.print(f"Extracting facts from [bold]{file.name}[/bold]...")

    try:
        facts = extract_facts_from_document(
            document_path=file,
            api_key=resolved_key,
            model=model,
            existing_codes=existing_codes,
        )
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        err_console.print(f"[red]Extraction failed:[/red] {e}")
        raise typer.Exit(1)

    if not facts:
        console.print("[dim]No facts extracted from document.[/dim]")
        return

    # Display extracted facts
    table = Table(title=f"Extracted Facts ({len(facts)})")
    table.add_column("Code", style="bold")
    table.add_column("Layer")
    table.add_column("Type")
    table.add_column("Confidence")
    table.add_column("Tags")
    table.add_column("Fact")

    for f in facts:
        tags_display = ", ".join(f.tags[:3])
        if len(f.tags) > 3:
            tags_display += f" (+{len(f.tags) - 3})"
        fact_display = f.fact[:60] + "..." if len(f.fact) > 60 else f.fact
        table.add_row(
            f.code,
            f.layer.value,
            f.type,
            f.confidence.value,
            tags_display,
            fact_display,
        )

    console.print(table)

    if dry_run:
        console.print("\n[dim]Dry run — no facts written.[/dim]")
        return

    if not typer.confirm(f"\nWrite {len(facts)} facts to .lattice/facts/?"):
        console.print("[dim]Aborted.[/dim]")
        return

    created = 0
    skipped = 0
    for f in facts:
        if store.exists(f.code):
            console.print(f"[yellow]Skipping {f.code} (already exists)[/yellow]")
            skipped += 1
            continue
        store.create(f)
        created += 1

    console.print(
        f"\n[green]Created[/green] {created} fact(s)"
        + (f", {skipped} skipped (code collisions)" if skipped else "")
        + "."
    )
    console.print("[dim]Run `lattice validate` to check references.[/dim]")
