"""LensStore — LatticeStore protocol implementation backed by a remote MCP server.

Proxies all store operations to a remote LatticeLens MCP server. Read-only by
default; set writable=True in the LensConfig to enable write operations.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from lattice_lens.lens import LensConfig, LensConnectionError, LensModeError
from lattice_lens.models import Fact
from lattice_lens.store.index import FactIndex

# Timeout for individual MCP tool calls (seconds).
CALL_TIMEOUT = 30


class LensStore:
    """LatticeStore implementation that proxies to a remote MCP server.

    Uses a background asyncio event loop with a persistent MCP client session
    to bridge async MCP calls to the synchronous LatticeStore protocol.
    """

    def __init__(self, lattice_root: Path, lens_config: LensConfig):
        self.root = lattice_root
        self.facts_dir = lattice_root / "facts"  # sentinel — no local files
        self.history_dir = lattice_root / "history"  # sentinel — no local files
        self._config = lens_config
        self._writable = lens_config.writable
        self._index: FactIndex | None = None

        # Background event loop (lazy init)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

        # MCP client state (managed on the background loop)
        self._session = None  # ClientSession once connected
        self._connected = False
        self._context_stack = None  # Holds the async context managers

    # ── Async / Sync Bridge ──

    def _ensure_loop(self):
        """Start a background event loop thread if not already running."""
        if self._loop is None or not self._loop.is_running():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()

    def _run_sync(self, coro):
        """Run a coroutine on the background event loop and return the result."""
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=CALL_TIMEOUT)
        except TimeoutError:
            raise LensConnectionError(
                f"MCP call timed out after {CALL_TIMEOUT}s (endpoint: {self._config.endpoint})"
            )
        except Exception as e:
            # Unwrap connection-level errors
            msg = str(e)
            if "connect" in msg.lower() or "refused" in msg.lower() or "closed" in msg.lower():
                raise LensConnectionError(
                    f"Failed to connect to remote lattice at {self._config.endpoint}: {msg}"
                ) from e
            raise

    async def _ensure_connected(self):
        """Establish MCP connection if not already connected."""
        if self._session is not None and self._connected:
            return self._session

        try:
            # mcp >=1.26 moved ClientSession to mcp.client.session
            try:
                from mcp.client.session import ClientSession
            except ImportError:
                from mcp.client import ClientSession  # mcp <1.26 fallback
            import mcp.client.sse  # noqa: F401 — verify sse module available
        except ImportError:
            raise ImportError("MCP client not installed. Run: pip install lattice-lens[mcp]")

        try:
            read_stream, write_stream = await self._enter_sse(self._config.endpoint)
            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            await self._session.initialize()
            self._connected = True
            return self._session
        except ImportError:
            raise
        except Exception as e:
            self._connected = False
            self._session = None
            raise LensConnectionError(
                f"Failed to connect to remote lattice at {self._config.endpoint}: {e}"
            ) from e

    async def _enter_sse(self, url: str):
        """Open an SSE transport and return (read, write) streams.

        Keeps the async context manager alive for the session duration.
        """
        from mcp.client.sse import sse_client

        cm = sse_client(url)
        read_stream, write_stream = await cm.__aenter__()
        self._context_stack = cm  # keep alive
        return read_stream, write_stream

    async def _call_tool(self, name: str, arguments: dict | None = None) -> str:
        """Call a remote MCP tool and return the text response."""
        session = await self._ensure_connected()
        result = await session.call_tool(name, arguments or {})
        if not result.content:
            return "{}"
        return result.content[0].text

    def _call(self, name: str, arguments: dict | None = None) -> str:
        """Synchronous wrapper around _call_tool."""
        return self._run_sync(self._call_tool(name, arguments))

    def _call_json(self, name: str, arguments: dict | None = None) -> dict | list:
        """Call a tool and parse the JSON response."""
        text = self._call(name, arguments)
        return json.loads(text)

    # ── Write Guard ──

    def _require_writable(self):
        """Raise LensModeError if the lens is not writable."""
        if not self._writable:
            raise LensModeError(
                "This lattice is in read-only lens mode. "
                "Set 'writable: true' in .lattice/.lens to enable writes, "
                "or reconnect with: lattice lens connect --writable <endpoint>"
            )

    # ── LatticeStore Protocol Methods ──

    def get(self, code: str) -> Fact | None:
        """Get a single fact by its code."""
        data = self._call_json("fact_get", {"code": code})
        if isinstance(data, dict) and "error" in data:
            return None
        return Fact.model_validate(data)

    def list_facts(self, **filters) -> list[Fact]:
        """Query facts with filters."""
        # Map filter kwargs to tool arguments
        args: dict = {}
        if "layer" in filters:
            args["layer"] = filters["layer"]
        if "tags_any" in filters:
            args["tags"] = filters["tags_any"]
        elif "tags" in filters:
            args["tags"] = filters["tags"]
        if "status" in filters:
            status = filters["status"]
            if isinstance(status, list):
                args["status"] = status[0] if len(status) == 1 else None
            else:
                args["status"] = status
        if "type" in filters:
            args["type"] = filters["type"]
        if "text_search" in filters:
            args["text_search"] = filters["text_search"]
        # Remove None values
        args = {k: v for k, v in args.items() if v is not None}

        data = self._call_json("fact_query", args)
        if isinstance(data, dict) and "error" in data:
            return []
        return [Fact.model_validate(item) for item in data]

    def create(self, fact: Fact) -> Fact:
        """Create a new fact remotely."""
        self._require_writable()
        fact_data = fact.model_dump(mode="json")
        data = self._call_json("fact_create", fact_data)
        if isinstance(data, dict) and "error" in data:
            raise ValueError(data["error"])
        return Fact.model_validate(data)

    def update(self, code: str, changes: dict, reason: str) -> Fact:
        """Update a fact remotely."""
        self._require_writable()
        data = self._call_json("fact_update", {"code": code, "reason": reason, **changes})
        if isinstance(data, dict) and "error" in data:
            raise ValueError(data["error"])
        return Fact.model_validate(data)

    def deprecate(self, code: str, reason: str) -> Fact:
        """Deprecate a fact remotely."""
        self._require_writable()
        data = self._call_json("fact_deprecate", {"code": code, "reason": reason})
        if isinstance(data, dict) and "error" in data:
            raise ValueError(data["error"])
        return Fact.model_validate(data)

    def exists(self, code: str) -> bool:
        """Check if a fact code exists."""
        data = self._call_json("fact_exists", {"code": code})
        return data.get("exists", False)

    def all_codes(self) -> list[str]:
        """Return all fact codes."""
        data = self._call_json("all_codes")
        if isinstance(data, list):
            return data
        return []

    def stats(self) -> dict:
        """Get lattice summary statistics."""
        data = self._call_json("lattice_status")
        if isinstance(data, dict):
            return data
        return {}

    # ── Non-Protocol Properties ──

    @property
    def index(self) -> FactIndex:
        """Build an in-memory FactIndex by fetching all facts from the remote."""
        if self._index is None:
            # Fetch all facts (no status filter to get everything)
            all_facts = self.list_facts()
            self._index = FactIndex()
            for fact in all_facts:
                self._index._add(fact)
        return self._index

    def invalidate_index(self):
        """Clear the cached index, forcing a re-fetch on next access."""
        self._index = None
