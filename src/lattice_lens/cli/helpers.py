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
    """Find .lattice/ root and return the appropriate store based on config.

    Detection order:
    1. If .lattice/.lens exists → LensStore (remote MCP)
    2. If config.yaml backend == "sqlite" → SqliteStore
    3. Otherwise → YamlFileStore (default)
    """
    root = find_lattice_root(path)
    if root is None:
        err_console.print(
            "[red]Error:[/red] No .lattice/ directory found. Run [bold]lattice init[/bold] first."
        )
        raise typer.Exit(1)

    # Check for lens mode first
    from lattice_lens.lens import read_lens_file

    lens_config = read_lens_file(root)
    if lens_config is not None:
        from lattice_lens.store.lens_store import LensStore

        return LensStore(root, lens_config)

    # Existing config-based backend selection
    config = load_config(root)
    backend = config.get("backend", "yaml")
    if backend == "sqlite":
        from lattice_lens.store.sqlite_store import SqliteStore

        return SqliteStore(root)
    return YamlFileStore(root)


def is_lens_mode(path: Path | None = None) -> bool:
    """Check if the current lattice is in lens mode (has a .lens file)."""
    root = find_lattice_root(path)
    if root is None:
        return False
    from lattice_lens.lens import read_lens_file

    return read_lens_file(root) is not None


def require_local_lattice(path: Path | None = None) -> LatticeStore:
    """Like require_lattice() but rejects lens mode with a clear error.

    Use this for commands that require local filesystem access (e.g., backend
    switch, git diff, serve, seed).
    """
    if is_lens_mode(path):
        err_console.print(
            "[red]Error:[/red] This command is not available in lens mode.\n"
            "This operation must be performed on the remote lattice server."
        )
        raise typer.Exit(1)
    return require_lattice(path)
