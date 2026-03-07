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

        assert len(tool_names) == 8
        assert "fact_get" in tool_names
        assert "fact_query" in tool_names
        assert "fact_list" in tool_names
        assert "context_assemble" in tool_names
        assert "graph_impact" in tool_names
        assert "graph_orphans" in tool_names
        assert "lattice_status" in tool_names
        assert "reconcile" in tool_names
        # Write tools should NOT be present
        assert "fact_create" not in tool_names
        assert "fact_update" not in tool_names
        assert "fact_deprecate" not in tool_names

    def test_writable(self, tmp_lattice):
        from lattice_lens.mcp.server import create_server

        _write_role_templates(tmp_lattice / "roles")
        server = create_server(tmp_lattice, writable=True)
        tools = _run(server.list_tools())
        tool_names = [t.name for t in tools]

        assert len(tool_names) == 11
        assert "fact_create" in tool_names
        assert "fact_update" in tool_names
        assert "fact_deprecate" in tool_names


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
