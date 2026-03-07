"""lattice serve — start the MCP server."""

from __future__ import annotations


import typer
from rich.console import Console

from lattice_lens.cli.helpers import is_lens_mode
from lattice_lens.config import find_lattice_root

err_console = Console(stderr=True)


def serve(
    stdio: bool = typer.Option(True, help="Use stdio transport (for Claude Desktop/Code)"),
    host: str = typer.Option("127.0.0.1", help="HTTP host (disables stdio)"),
    port: int = typer.Option(3100, help="HTTP port"),
    writable: bool = typer.Option(False, help="Enable write operations"),
):
    """Start the LatticeLens MCP server."""
    if is_lens_mode():
        err_console.print(
            "[red]Error:[/red] 'serve' is not available in lens mode.\n"
            "Cannot serve a lens as an MCP server."
        )
        raise typer.Exit(1)

    root = find_lattice_root()
    if root is None:
        err_console.print(
            "[red]Error:[/red] No .lattice directory found. Run 'lattice init' first."
        )
        raise typer.Exit(1)

    try:
        from lattice_lens.mcp.server import create_server
    except ImportError:
        err_console.print(
            "[red]Error:[/red] MCP dependencies not installed. Run: pip install lattice-lens[mcp]"
        )
        raise typer.Exit(1)

    server = create_server(root, writable=writable)

    # If host/port were explicitly changed from defaults, use HTTP transport
    use_stdio = stdio and host == "127.0.0.1" and port == 3100

    if use_stdio:
        err_console.print(
            f"[green]LatticeLens MCP server[/green] (stdio) lattice={root} writable={writable}",
        )
        server.run(transport="stdio")
    else:
        err_console.print(
            f"[green]LatticeLens MCP server[/green] "
            f"http://{host}:{port} lattice={root} writable={writable}",
        )
        server.run(transport="sse", host=host, port=port)
