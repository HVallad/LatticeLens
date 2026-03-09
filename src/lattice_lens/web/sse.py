"""Server-Sent Events for live change detection."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse


def _compute_dir_hash(facts_dir: Path) -> str:
    """Hash of {filename: mtime} for all YAML files in facts/."""
    entries = {}
    if facts_dir.exists():
        for p in sorted(facts_dir.glob("*.yaml")):
            try:
                entries[p.name] = p.stat().st_mtime
            except OSError:
                continue
    return hashlib.md5(json.dumps(entries).encode()).hexdigest()


def create_sse_router() -> APIRouter:
    router = APIRouter(tags=["sse"])

    @router.get("/events")
    async def events(request: Request):
        """SSE stream — pushes lattice_changed events when facts directory changes."""
        facts_dir = request.app.state.facts_dir
        store = request.app.state.store

        async def event_generator():
            last_hash = _compute_dir_hash(facts_dir)
            # Send initial connected event
            yield f"event: connected\ndata: {json.dumps({'hash': last_hash})}\n\n"

            while True:
                await asyncio.sleep(2.0)

                # Check if client disconnected
                if await request.is_disconnected():
                    break

                current_hash = _compute_dir_hash(facts_dir)
                if current_hash != last_hash:
                    last_hash = current_hash
                    store.invalidate_index()
                    yield (
                        f"event: lattice_changed\ndata: {json.dumps({'hash': current_hash})}\n\n"
                    )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
