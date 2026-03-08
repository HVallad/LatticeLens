"""lattice lens — connect to a remote lattice via MCP."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from lattice_lens.config import LATTICE_DIR, find_lattice_root
from lattice_lens.lens import (
    LensConfig,
    LensConnectionError,
    read_lens_file,
    remove_lens_file,
    write_lens_file,
)

console = Console()
err_console = Console(stderr=True)

lens_app = typer.Typer(no_args_is_help=True)


@lens_app.command()
def connect(
    endpoint: str = typer.Argument(
        help="MCP server endpoint URL (e.g., http://localhost:8080/mcp)"
    ),
    transport: str = typer.Option("sse", "--transport", help="Transport type: sse or stdio."),
    writable: bool = typer.Option(False, "--writable", help="Enable write operations."),
    project: str | None = typer.Option(None, "--project", help="Scope to a specific project."),
):
    """Connect to a remote lattice via MCP.

    Creates a .lattice/.lens file pointing at the remote server. All lattice
    commands will transparently proxy to the remote.
    """
    # Build the config
    config = LensConfig(
        endpoint=endpoint,
        transport=transport,
        writable=writable,
        project=project,
    )

    # Create .lattice/ directory if it doesn't exist
    cwd = Path.cwd()
    lattice_root = find_lattice_root(cwd)
    if lattice_root is None:
        lattice_root = cwd / LATTICE_DIR
        lattice_root.mkdir(exist_ok=True)

    # Check for existing local lattice (facts dir present = full lattice, not lens)
    facts_dir = lattice_root / "facts"
    if facts_dir.exists() and any(facts_dir.iterdir()):
        err_console.print(
            "[red]Error:[/red] This directory already contains a full lattice.\n"
            "Cannot create a lens file alongside existing fact files.\n"
            "Use a separate directory or remove the existing lattice first."
        )
        raise typer.Exit(1)

    # Verify the remote server is reachable
    console.print(f"[dim]Connecting to {endpoint}...[/dim]")
    try:
        from lattice_lens.store.lens_store import LensStore

        temp_store = LensStore(lattice_root, config)
        stats = temp_store.stats()
    except LensConnectionError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ImportError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Write the lens file
    lens_path = write_lens_file(lattice_root, config)
    console.print(f"[green]Connected![/green] Lens file created at {lens_path}")

    # Show remote lattice info
    mode = "[yellow]writable[/yellow]" if writable else "[dim]read-only[/dim]"
    console.print(f"  Mode: {mode}")
    console.print(f"  Endpoint: {endpoint}")
    console.print(f"  Transport: {transport}")
    if project:
        console.print(f"  Project: {project}")
    if isinstance(stats, dict):
        total = stats.get("total", "?")
        backend = stats.get("backend", "?")
        console.print(f"  Remote: {total} facts ({backend} backend)")


@lens_app.command()
def status():
    """Show lens connection status and remote lattice info."""
    root = find_lattice_root()
    if root is None:
        err_console.print("[red]Error:[/red] No .lattice/ directory found.")
        raise typer.Exit(1)

    config = read_lens_file(root)
    if config is None:
        err_console.print("[red]Error:[/red] Not in lens mode. No .lens file found in .lattice/.")
        raise typer.Exit(1)

    console.print("[bold]Lens Configuration[/bold]")
    console.print(f"  Endpoint:  {config.endpoint}")
    console.print(f"  Transport: {config.transport}")
    mode = "[yellow]writable[/yellow]" if config.writable else "[dim]read-only[/dim]"
    console.print(f"  Mode:      {mode}")
    if config.project:
        console.print(f"  Project:   {config.project}")

    # Test connection
    console.print("\n[dim]Checking connection...[/dim]")
    try:
        from lattice_lens.store.lens_store import LensStore

        store = LensStore(root, config)
        stats = store.stats()
        console.print("[green]Connection: OK[/green]")
        if isinstance(stats, dict):
            console.print(f"  Total facts: {stats.get('total', '?')}")
            console.print(f"  Backend:     {stats.get('backend', '?')}")
            by_status = stats.get("by_status", {})
            if by_status:
                parts = [f"{k}: {v}" for k, v in sorted(by_status.items())]
                console.print(f"  By status:   {', '.join(parts)}")
    except LensConnectionError as e:
        err_console.print("[red]Connection: FAILED[/red]")
        err_console.print(f"  {e}")
    except ImportError as e:
        err_console.print(f"[red]Error:[/red] {e}")


@lens_app.command()
def disconnect():
    """Disconnect from a remote lattice (removes .lens file)."""
    root = find_lattice_root()
    if root is None:
        err_console.print("[red]Error:[/red] No .lattice/ directory found.")
        raise typer.Exit(1)

    config = read_lens_file(root)
    if config is None:
        err_console.print("[red]Error:[/red] Not in lens mode. No .lens file found in .lattice/.")
        raise typer.Exit(1)

    removed = remove_lens_file(root)
    if removed:
        console.print(f"[green]Disconnected[/green] from {config.endpoint}")

        # Clean up empty .lattice/ directory
        remaining = list(root.iterdir())
        if not remaining:
            root.rmdir()
            console.print("[dim]Removed empty .lattice/ directory.[/dim]")
    else:
        err_console.print("[red]Error:[/red] Failed to remove .lens file.")
        raise typer.Exit(1)
