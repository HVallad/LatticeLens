"""lattice view — open the interactive web viewer."""

from __future__ import annotations

import typer
from rich.console import Console

from lattice_lens.cli.helpers import is_lens_mode
from lattice_lens.config import find_lattice_root

err_console = Console(stderr=True)


def view(
    port: int = typer.Option(8765, help="Server port"),
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't auto-open browser"),
):
    """Open the interactive web viewer for the knowledge lattice."""
    if is_lens_mode():
        err_console.print(
            "[red]Error:[/red] 'view' is not available in lens mode.\n"
            "Cannot view a remote lens locally."
        )
        raise typer.Exit(1)

    root = find_lattice_root()
    if root is None:
        err_console.print(
            "[red]Error:[/red] No .lattice directory found. Run 'lattice init' first."
        )
        raise typer.Exit(1)

    try:
        import fastapi  # noqa: F401
        import uvicorn
    except ImportError:
        err_console.print(
            "[red]Error:[/red] Viewer dependencies not installed.\n"
            "Run: pip install lattice-lens[viewer]"
        )
        raise typer.Exit(1)

    from lattice_lens.web.app import create_app

    app = create_app(root)

    url = f"http://{host}:{port}"
    err_console.print(
        f"[green]LatticeLens Viewer[/green] {url} lattice={root}",
    )

    if not no_open:
        import webbrowser

        # Open browser after a short delay to let server start
        import threading

        def _open():
            import time

            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
