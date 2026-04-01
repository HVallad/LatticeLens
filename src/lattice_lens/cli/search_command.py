"""lattice search — semantic similarity search for facts."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import require_lattice

console = Console()
err_console = Console(stderr=True)


def search(
    query: Optional[str] = typer.Argument(None, help="Natural language query for semantic search"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter results by tag"),
    layer: Optional[str] = typer.Option(
        None, "--layer", help="Filter results by layer (WHY/GUARDRAILS/HOW)"
    ),
    status: Optional[str] = typer.Option(None, "--status", help="Filter results by status"),
    project: Optional[str] = typer.Option(None, "--project", help="Filter results by project"),
    top: int = typer.Option(10, "--top", help="Number of results to return"),
    threshold: float = typer.Option(0.3, "--threshold", help="Minimum similarity score (0-1)"),
    rebuild_index: bool = typer.Option(
        False, "--rebuild-index", help="Force rebuild the embedding index"
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Semantic search across lattice facts using embeddings."""
    try:
        from lattice_lens.services.embedding_service import (
            HAS_SENTENCE_TRANSFORMERS,
            semantic_search,
        )
    except Exception:
        err_console.print(
            "[red]Error:[/red] Failed to load embedding service. "
            "Install with: [bold]pip install lattice-lens\\[semantic][/bold]"
        )
        raise typer.Exit(1)

    if not HAS_SENTENCE_TRANSFORMERS:
        err_console.print(
            "[red]Error:[/red] sentence-transformers is not installed. "
            "Install with: [bold]pip install lattice-lens\\[semantic][/bold]"
        )
        raise typer.Exit(1)

    if not query and not rebuild_index:
        err_console.print("[red]Error:[/red] Provide a search query or use --rebuild-index.")
        raise typer.Exit(1)

    store = require_lattice()

    # Get all facts (all statuses for indexing, filter in search)
    all_facts = store.list_facts(
        status=["Active", "Under Review", "Draft", "Deprecated", "Superseded"]
    )

    if not all_facts:
        err_console.print("[yellow]No facts found in lattice.[/yellow]")
        raise typer.Exit(1)

    lattice_root = store.root

    if rebuild_index and not query:
        # Just rebuild, no search
        from lattice_lens.services.embedding_service import EmbeddingIndex, EMBEDDINGS_FILE

        idx = EmbeddingIndex()
        idx.build_index(all_facts)
        idx.save(lattice_root / EMBEDDINGS_FILE)

        if as_json:
            print(
                json.dumps(
                    {
                        "action": "rebuild",
                        "facts_indexed": len(all_facts),
                        "path": str(lattice_root / EMBEDDINGS_FILE),
                    },
                    indent=2,
                )
            )
        else:
            console.print(
                f"[green]Rebuilt embedding index:[/green] {len(all_facts)} facts indexed."
            )
        return

    results = semantic_search(
        facts=all_facts,
        query=query,
        lattice_root=lattice_root,
        top_k=top,
        threshold=threshold,
        force_rebuild=rebuild_index,
        tag=tag,
        layer=layer,
        status=status,
        project=project,
    )

    if as_json:
        print(json.dumps({"query": query, "results": results}, indent=2))
        return

    if not results:
        console.print(f"[dim]No facts matched query '{query}' above threshold {threshold}.[/dim]")
        return

    console.print(f'\n[bold]Semantic search:[/bold] "{query}"')
    console.print(f"[dim]Showing top {len(results)} results (threshold >= {threshold})[/dim]\n")

    table = Table(show_header=True)
    table.add_column("Score", style="bold cyan", justify="right", width=7)
    table.add_column("Code", style="bold", width=8)
    table.add_column("Type", width=30)
    table.add_column("Layer", width=12)
    table.add_column("Tags", width=20)
    table.add_column("Snippet", width=50)

    for r in results:
        score_str = f"{r['score']:.3f}"
        tags_str = ", ".join(r["tags"][:3])
        if len(r["tags"]) > 3:
            tags_str += "..."
        table.add_row(
            score_str,
            r["code"],
            r["type"],
            r["layer"],
            tags_str,
            r["snippet"][:80] + ("..." if len(r["snippet"]) > 80 else ""),
        )

    console.print(table)
