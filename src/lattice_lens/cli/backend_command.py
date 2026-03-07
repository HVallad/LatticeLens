"""lattice backend — backend management (status, switch)."""

from __future__ import annotations

import typer
from rich.console import Console

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import find_lattice_root, load_config, save_config

console = Console()
err_console = Console(stderr=True)

backend_app = typer.Typer()


@backend_app.command("status")
def backend_status():
    """Show current backend type, fact count, and advisory thresholds."""
    store = require_lattice()
    stats = store.stats()

    console.print(f"[bold]Backend:[/bold] {stats['backend']}")
    console.print(f"[bold]Total facts:[/bold] {stats['total']}")

    fact_count = stats["total"]
    if fact_count >= 2000:
        console.print(
            "[yellow]\u26a0 2,000+ facts. Consider: lattice backend switch sqlite[/yellow]"
        )
    elif fact_count >= 1500:
        console.print(
            "[dim]\u2139 Approaching scale threshold (1,500 facts). SQLite available.[/dim]"
        )


@backend_app.command("switch")
def backend_switch(
    target: str = typer.Argument(..., help="Target backend: 'sqlite' or 'yaml'."),
):
    """Migrate between YAML and SQLite backends."""
    root = find_lattice_root()
    if root is None:
        err_console.print("[red]Error:[/red] No .lattice/ directory found.")
        raise typer.Exit(1)

    config = load_config(root)
    current_backend = config.get("backend", "yaml")

    if target not in ("yaml", "sqlite"):
        err_console.print(f"[red]Error:[/red] Unknown backend '{target}'. Use 'yaml' or 'sqlite'.")
        raise typer.Exit(1)

    if target == current_backend:
        console.print(f"Already using {target} backend. Nothing to do.")
        return

    # Import both store types
    from lattice_lens.store.yaml_store import YamlFileStore
    from lattice_lens.store.sqlite_store import SqliteStore

    # Create source store
    if current_backend == "yaml":
        source = YamlFileStore(root)
    else:
        source = SqliteStore(root)

    # Read all facts from source (all statuses)
    all_facts = source.list_facts(status=None)
    console.print(f"Migrating {len(all_facts)} facts from {current_backend} to {target}...")

    # Create target store
    if target == "sqlite":
        target_store = SqliteStore(root)
    else:
        target_store = YamlFileStore(root)

    # Write facts to target
    migrated = 0
    for fact in all_facts:
        if not target_store.exists(fact.code):
            target_store.create(fact)
            migrated += 1

    # Update config
    config["backend"] = target
    save_config(root, config)

    console.print(f"[green]\u2713[/green] Migrated {migrated} facts to {target} backend.")
    console.print(f"[dim]Original {current_backend} data preserved (not deleted).[/dim]")
