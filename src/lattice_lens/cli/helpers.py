"""Shared CLI helpers."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from lattice_lens.config import find_lattice_root, load_config
from lattice_lens.store.protocol import LatticeStore
from lattice_lens.store.yaml_store import YamlFileStore

console = Console()
err_console = Console(stderr=True)


def require_lattice(path: Path | None = None) -> LatticeStore:
    """Find .lattice/ root and return the appropriate store based on config."""
    root = find_lattice_root(path)
    if root is None:
        err_console.print(
            "[red]Error:[/red] No .lattice/ directory found. "
            "Run [bold]lattice init[/bold] first."
        )
        raise typer.Exit(1)

    config = load_config(root)
    backend = config.get("backend", "yaml")
    if backend == "sqlite":
        from lattice_lens.store.sqlite_store import SqliteStore

        return SqliteStore(root)
    return YamlFileStore(root)
