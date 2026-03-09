"""FastAPI application factory for the LatticeLens web viewer."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lattice_lens.config import FACTS_DIR, ROLES_DIR, load_config
from lattice_lens.store.yaml_store import YamlFileStore
from lattice_lens.web.api.facts import create_facts_router
from lattice_lens.web.api.graph import create_graph_router
from lattice_lens.web.api.meta import create_meta_router
from lattice_lens.web.sse import create_sse_router


def create_app(lattice_root: Path) -> FastAPI:
    """Create and configure the LatticeLens web viewer FastAPI app.

    Args:
        lattice_root: Path to the .lattice/ directory.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="LatticeLens Viewer",
        description="Interactive knowledge graph viewer for LatticeLens",
        version="1.0.0",
    )

    # CORS for development (Vite dev server on different port)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize store based on config
    config = load_config(lattice_root)
    backend = config.get("backend", "yaml")
    if backend == "sqlite":
        from lattice_lens.store.sqlite_store import SqliteStore

        store = SqliteStore(lattice_root)
    else:
        store = YamlFileStore(lattice_root)

    facts_dir = lattice_root / FACTS_DIR
    roles_dir = lattice_root / ROLES_DIR

    # Store references on app state for access by routers
    app.state.store = store
    app.state.lattice_root = lattice_root
    app.state.facts_dir = facts_dir
    app.state.roles_dir = roles_dir

    # Middleware to invalidate index on each request (picks up external changes)
    @app.middleware("http")
    async def refresh_index(request: Request, call_next):
        store.invalidate_index()
        response = await call_next(request)
        return response

    # Register API routers
    app.include_router(create_facts_router(), prefix="/api")
    app.include_router(create_graph_router(), prefix="/api")
    app.include_router(create_meta_router(), prefix="/api")
    app.include_router(create_sse_router(), prefix="/api")

    # Serve static frontend assets
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and (static_dir / "index.html").exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve the SPA — try static file first, fall back to index.html."""
            file_path = static_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(static_dir / "index.html"))

    return app
