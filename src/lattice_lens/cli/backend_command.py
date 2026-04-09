"""lattice backend — backend management (status, switch)."""

from __future__ import annotations

from collections import defaultdict

import typer
from rich.console import Console

from lattice_lens.cli.helpers import is_lens_mode, require_lattice
from lattice_lens.config import find_lattice_root, load_config, save_config
from lattice_lens.models import Fact

console = Console()
err_console = Console(stderr=True)

backend_app = typer.Typer()


def _find_duplicate_refs(facts: list[Fact]) -> dict[str, list[str]]:
    """Check facts for duplicate reference targets.

    Returns a dict mapping fact codes to lists of duplicated target codes.
    Empty dict means no duplicates found.
    """
    duplicates: dict[str, list[str]] = {}
    for fact in facts:
        seen: dict[str, int] = defaultdict(int)
        for ref in fact.refs:
            seen[ref.code] += 1
        dupes = [code for code, count in seen.items() if count > 1]
        if dupes:
            duplicates[fact.code] = dupes
    return duplicates


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
    if is_lens_mode():
        err_console.print(
            "[red]Error:[/red] 'backend switch' is not available in lens mode.\n"
            "Backend management must be performed on the remote lattice server."
        )
        raise typer.Exit(1)
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
    from lattice_lens.store.sqlite_store import SqliteStore
    from lattice_lens.store.yaml_store import YamlFileStore

    # Create source store
    if current_backend == "yaml":
        source = YamlFileStore(root)
    else:
        source = SqliteStore(root)

    # Read all facts from source (all statuses)
    all_facts = source.list_facts(status=None)
    console.print(f"Migrating {len(all_facts)} facts from {current_backend} to {target}...")

    # Pre-migration validation: detect duplicate references
    duplicates = _find_duplicate_refs(all_facts)
    if duplicates:
        err_console.print("[red]Error:[/red] Duplicate references detected. Migration aborted.")
        err_console.print("")
        for code, dupes in sorted(duplicates.items()):
            err_console.print(f"  [bold]{code}[/bold] has duplicate refs to: {', '.join(dupes)}")
        err_console.print("")
        err_console.print(
            "[yellow]Fix these facts before retrying the migration.[/yellow]\n"
            "Each fact may only reference a given target once."
        )
        raise typer.Exit(1)

    # Determine db path for cleanup on failure (only relevant for sqlite target)
    db_path = root / "lattice.db" if target == "sqlite" else None
    db_existed_before = db_path.exists() if db_path else False

    try:
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

        # Close SQLite connection before config update
        if target == "sqlite":
            target_store.close()
    except Exception:
        # Clean up partial database if we created it during this migration
        if db_path and not db_existed_before and db_path.exists():
            db_path.unlink()
            # Also clean up WAL/SHM files
            for suffix in ("-wal", "-shm"):
                wal = db_path.parent / (db_path.name + suffix)
                if wal.exists():
                    wal.unlink()
        raise

    # Update config
    config["backend"] = target
    save_config(root, config)

    console.print(f"[green]\u2713[/green] Migrated {migrated} facts to {target} backend.")
    console.print(f"[dim]Original {current_backend} data preserved (not deleted).[/dim]")
