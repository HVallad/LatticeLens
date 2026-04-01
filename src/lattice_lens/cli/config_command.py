"""lattice config — configuration management commands."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lattice_lens.cli.helpers import is_lens_mode
from lattice_lens.config import find_lattice_root, load_config, save_config
from lattice_lens.services.embedding_service import (
    DEFAULT_MODEL,
    EMBEDDINGS_FILE,
    RECOMMENDED_MODELS,
)

console = Console()
err_console = Console(stderr=True)

config_app = typer.Typer()


@config_app.command("embedding")
def config_embedding(
    model: Optional[str] = typer.Option(None, "--model", help="Set the embedding model."),
    list_models: bool = typer.Option(False, "--list", help="Show recommended models."),
    reset: bool = typer.Option(False, "--reset", help="Reset to the default model."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """Show or change the embedding model used for semantic search."""
    if is_lens_mode():
        err_console.print(
            "[red]Error:[/red] 'config embedding' is not available in lens mode.\n"
            "Configuration must be managed on the remote lattice server."
        )
        raise typer.Exit(1)

    root = find_lattice_root()
    if root is None:
        err_console.print("[red]Error:[/red] No .lattice/ directory found.")
        raise typer.Exit(1)

    config = load_config(root)
    current_model = config.get("embedding", {}).get("model", DEFAULT_MODEL)

    # --list: show recommended models
    if list_models:
        _show_recommended_models(current_model, as_json)
        return

    # --reset: revert to default
    if reset:
        _set_embedding_model(root, config, current_model, DEFAULT_MODEL, as_json)
        return

    # --model: switch model
    if model:
        _set_embedding_model(root, config, current_model, model, as_json)
        return

    # No flags: show current model
    if as_json:
        import json

        print(json.dumps({"model": current_model, "default": DEFAULT_MODEL}, indent=2))
    else:
        console.print(f"[bold]Embedding model:[/bold] {current_model}")
        if current_model == DEFAULT_MODEL:
            console.print("[dim]Using default model.[/dim]")
        else:
            console.print(f"[dim]Default: {DEFAULT_MODEL}[/dim]")
        console.print("\n[dim]Use --list to see recommended models, --model to change.[/dim]")


def _show_recommended_models(current_model: str, as_json: bool) -> None:
    """Display the curated table of recommended embedding models."""
    if as_json:
        import json

        data = {
            "current": current_model,
            "default": DEFAULT_MODEL,
            "models": RECOMMENDED_MODELS,
        }
        print(json.dumps(data, indent=2))
        return

    console.print("\n[bold]Recommended Embedding Models:[/bold]\n")

    table = Table(show_header=True)
    table.add_column("Model", width=40)
    table.add_column("Dims", justify="right", width=6)
    table.add_column("Size", width=8)
    table.add_column("Quality", width=8)
    table.add_column("Speed", width=8)

    for m in RECOMMENDED_MODELS:
        name = m["name"]
        if name == DEFAULT_MODEL:
            name += " (default)"
        style = "bold" if m["name"] == current_model else None
        table.add_row(name, str(m["dims"]), m["size"], m["quality"], m["speed"], style=style)

    console.print(table)
    console.print(f"\n[bold]Current:[/bold] {current_model}")


def _set_embedding_model(
    root, config: dict, current_model: str, new_model: str, as_json: bool
) -> None:
    """Update the embedding model in config and clean up old embeddings."""
    if new_model == current_model:
        if as_json:
            import json

            print(json.dumps({"changed": False, "model": current_model}, indent=2))
        else:
            console.print(f"Already using model [bold]{current_model}[/bold]. Nothing to change.")
        return

    # Update config
    if "embedding" not in config:
        config["embedding"] = {}
    config["embedding"]["model"] = new_model
    save_config(root, config)

    # Delete old embeddings (incompatible with new model)
    embeddings_path = root / EMBEDDINGS_FILE
    deleted_embeddings = False
    if embeddings_path.exists():
        embeddings_path.unlink()
        deleted_embeddings = True

    if as_json:
        import json

        print(
            json.dumps(
                {
                    "changed": True,
                    "previous_model": current_model,
                    "model": new_model,
                    "embeddings_deleted": deleted_embeddings,
                },
                indent=2,
            )
        )
    else:
        console.print(f"[green]Embedding model changed:[/green] {current_model} -> {new_model}")
        if deleted_embeddings:
            console.print("[yellow]Old embeddings deleted (incompatible with new model).[/yellow]")
        console.print("[dim]Embedding model changed. Index will rebuild on next search.[/dim]")
