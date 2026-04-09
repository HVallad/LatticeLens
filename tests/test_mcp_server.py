"""Tests for MCP server integration (requires mcp package)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from tests.conftest import make_fact

yaml_rw = YAML()
yaml_rw.default_flow_style = False

try:
    from mcp.server.fastmcp import FastMCP  # noqa: F401

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

pytestmark = pytest.mark.skipif(not HAS_MCP, reason="mcp package not installed")


def _write_role_templates(roles_dir: Path):
    """Write standard role templates for testing."""
    roles_dir.mkdir(parents=True, exist_ok=True)
    template = {
        "name": "Planning Agent",
        "query": {
            "layers": ["WHY"],
            "types": ["Architecture Decision Record"],
            "tags": ["architecture"],
            "extra": [],
        },
    }
    with open(roles_dir / "planning.yaml", "w") as f:
        yaml_rw.dump(template, f)


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _call_tool_text(server, name, args):
    """Call a tool and return the text content string."""
    # call_tool returns (content_list, is_error) tuple
    content_list, _is_error = _run(server.call_tool(name, args))
    return content_list[0].text


class TestListTools:
    def test_readonly(self, tmp_lattice):
        from lattice_lens.mcp.server import create_server

        _write_role_templates(tmp_lattice / "roles")
        server = create_server(tmp_lattice, writable=False)
        tools = _run(server.list_tools())
        tool_names = [t.name for t in tools]

        assert len(tool_names) == 12
        assert "fact_get" in tool_names
        assert "fact_query" in tool_names
        assert "fact_list" in tool_names
        assert "context_assemble" in tool_names
        assert "graph_impact" in tool_names
        assert "graph_orphans" in tool_names
        assert "lattice_status" in tool_names
        assert "reconcile" in tool_names
        # Phase 7a read-only tools
        assert "graph_contradictions" in tool_names
        assert "lattice_validate" in tool_names
        assert "fact_exists" in tool_names
        assert "all_codes" in tool_names
        # Write tools should NOT be present
        assert "fact_create" not in tool_names
        assert "fact_update" not in tool_names
        assert "fact_deprecate" not in tool_names
        assert "fact_promote" not in tool_names

    def test_writable(self, tmp_lattice):
        from lattice_lens.mcp.server import create_server

        _write_role_templates(tmp_lattice / "roles")
        server = create_server(tmp_lattice, writable=True)
        tools = _run(server.list_tools())
        tool_names = [t.name for t in tools]

        assert len(tool_names) == 16
        assert "fact_create" in tool_names
        assert "fact_update" in tool_names
        assert "fact_deprecate" in tool_names
        assert "fact_promote" in tool_names


class TestCallTool:
    def test_fact_get(self, seeded_store):
        from lattice_lens.mcp.server import create_server

        _write_role_templates(seeded_store.root / "roles")
        server = create_server(seeded_store.root, writable=False)

        text = _call_tool_text(server, "fact_get", {"code": "ADR-01"})
        data = json.loads(text)
        assert data["code"] == "ADR-01"

    def test_index_refreshed_on_call(self, yaml_store):
        from lattice_lens.mcp.server import create_server

        _write_role_templates(yaml_store.root / "roles")
        server = create_server(yaml_store.root, writable=False)

        # Create a fact AFTER server creation
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)

        text = _call_tool_text(server, "fact_get", {"code": "ADR-01"})
        data = json.loads(text)
        assert data["code"] == "ADR-01"

    def test_promote_roundtrip(self, yaml_store):
        from lattice_lens.mcp.server import create_server
        from lattice_lens.models import FactStatus

        _write_role_templates(yaml_store.root / "roles")
        server = create_server(yaml_store.root, writable=True)

        # Create a Draft fact
        fact = make_fact(code="ADR-01", status=FactStatus.DRAFT)
        yaml_store.create(fact)

        # Promote via MCP tool
        text = _call_tool_text(server, "fact_promote", {"code": "ADR-01", "reason": "ready"})
        data = json.loads(text)
        assert data["status"] == "Under Review"

    def test_fact_exists_roundtrip(self, seeded_store):
        from lattice_lens.mcp.server import create_server

        _write_role_templates(seeded_store.root / "roles")
        server = create_server(seeded_store.root, writable=False)

        text = _call_tool_text(server, "fact_exists", {"code": "ADR-01"})
        data = json.loads(text)
        assert data["exists"] is True

        text = _call_tool_text(server, "fact_exists", {"code": "ZZZ-99"})
        data = json.loads(text)
        assert data["exists"] is False

    def test_all_codes_roundtrip(self, seeded_store):
        from lattice_lens.mcp.server import create_server

        _write_role_templates(seeded_store.root / "roles")
        server = create_server(seeded_store.root, writable=False)

        text = _call_tool_text(server, "all_codes", {})
        codes = json.loads(text)
        assert isinstance(codes, list)
        assert "ADR-01" in codes

    # --- New tests ---

    def test_fact_get_missing(self, yaml_store):
        """Getting a nonexistent fact returns an error dict."""
        from lattice_lens.mcp.server import create_server

        _write_role_templates(yaml_store.root / "roles")
        server = create_server(yaml_store.root, writable=False)

        text = _call_tool_text(server, "fact_get", {"code": "ZZZ-99"})
        data = json.loads(text)
        assert "error" in data

    def test_fact_query_by_layer(self, seeded_store):
        """Querying with a layer filter returns only matching facts."""
        from lattice_lens.mcp.server import create_server

        _write_role_templates(seeded_store.root / "roles")
        server = create_server(seeded_store.root, writable=False)

        text = _call_tool_text(server, "fact_query", {"layer": "WHY"})
        data = json.loads(text)
        assert isinstance(data, list)
        for fact in data:
            assert fact["layer"] == "WHY"

    def test_lattice_status(self, seeded_store):
        """lattice_status returns a dict with summary counts."""
        from lattice_lens.mcp.server import create_server

        _write_role_templates(seeded_store.root / "roles")
        server = create_server(seeded_store.root, writable=False)

        text = _call_tool_text(server, "lattice_status", {})
        data = json.loads(text)
        assert isinstance(data, dict)
        assert "total" in data or "total_facts" in data or len(data) > 0

    def test_fact_create_roundtrip(self, yaml_store):
        """Create a fact via MCP, then retrieve it."""
        from lattice_lens.mcp.server import create_server

        _write_role_templates(yaml_store.root / "roles")
        server = create_server(yaml_store.root, writable=True)

        create_text = _call_tool_text(
            server,
            "fact_create",
            {
                "code": "ADR-01",
                "layer": "WHY",
                "type": "Architecture Decision Record",
                "fact": "We chose FastMCP for the MCP server implementation.",
                "tags": ["architecture", "api"],
                "owner": "platform-team",
            },
        )
        create_data = json.loads(create_text)
        assert create_data.get("code") == "ADR-01" or "error" not in create_data

        # Retrieve it back
        get_text = _call_tool_text(server, "fact_get", {"code": "ADR-01"})
        get_data = json.loads(get_text)
        assert get_data["code"] == "ADR-01"
        assert "FastMCP" in get_data["fact"]

    def test_fact_update_persists_changes(self, yaml_store):
        """fact_update via MCP persists field changes, not just version bump."""
        from lattice_lens.mcp.server import create_server

        _write_role_templates(yaml_store.root / "roles")
        server = create_server(yaml_store.root, writable=True)

        # Create a fact first
        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)
        original_text = fact.fact

        # Update the fact text via MCP tool
        update_text = _call_tool_text(
            server,
            "fact_update",
            {
                "code": "ADR-01",
                "reason": "clarify wording",
                "changes": {"fact": "Updated fact text via MCP tool."},
            },
        )
        update_data = json.loads(update_text)
        assert "error" not in update_data
        assert update_data["fact"] == "Updated fact text via MCP tool."
        assert update_data["version"] == 2

        # Verify the change persisted by reading back
        get_text = _call_tool_text(server, "fact_get", {"code": "ADR-01"})
        get_data = json.loads(get_text)
        assert get_data["fact"] == "Updated fact text via MCP tool."
        assert get_data["fact"] != original_text

    def test_fact_update_persists_tags(self, yaml_store):
        """fact_update via MCP persists tag changes."""
        from lattice_lens.mcp.server import create_server

        _write_role_templates(yaml_store.root / "roles")
        server = create_server(yaml_store.root, writable=True)

        fact = make_fact(code="ADR-01", tags=["old-tag", "keep-tag"])
        yaml_store.create(fact)

        update_text = _call_tool_text(
            server,
            "fact_update",
            {
                "code": "ADR-01",
                "reason": "update tags",
                "changes": {"tags": ["new-tag", "keep-tag"]},
            },
        )
        update_data = json.loads(update_text)
        assert "error" not in update_data
        assert "new-tag" in update_data["tags"]
        assert "old-tag" not in update_data["tags"]

        # Verify persistence
        get_text = _call_tool_text(server, "fact_get", {"code": "ADR-01"})
        get_data = json.loads(get_text)
        assert "new-tag" in get_data["tags"]
        assert "old-tag" not in get_data["tags"]

    def test_fact_update_multiple_fields(self, yaml_store):
        """fact_update via MCP persists multiple field changes at once."""
        from lattice_lens.mcp.server import create_server

        _write_role_templates(yaml_store.root / "roles")
        server = create_server(yaml_store.root, writable=True)

        fact = make_fact(code="ADR-01")
        yaml_store.create(fact)

        update_text = _call_tool_text(
            server,
            "fact_update",
            {
                "code": "ADR-01",
                "reason": "major revision",
                "changes": {
                    "fact": "Completely rewritten fact text.",
                    "tags": ["revised", "architecture"],
                    "owner": "new-team",
                },
            },
        )
        update_data = json.loads(update_text)
        assert "error" not in update_data
        assert update_data["fact"] == "Completely rewritten fact text."
        assert "revised" in update_data["tags"]
        assert update_data["owner"] == "new-team"
        assert update_data["version"] == 2
