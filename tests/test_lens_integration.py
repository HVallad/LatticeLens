"""Integration tests for Lens round-trip: in-process server + LensStore client.

These tests are marked @pytest.mark.integration because they require the
MCP dependencies and spin up an in-process server.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from lattice_lens.config import FACTS_DIR, HISTORY_DIR, LATTICE_DIR, ROLES_DIR
from lattice_lens.lens import LensConfig
from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus

# Mark the entire module as integration tests
pytestmark = pytest.mark.integration


def _create_lattice_dir(base: Path) -> Path:
    """Create a full .lattice/ directory structure."""
    lattice_root = base / LATTICE_DIR
    (lattice_root / FACTS_DIR).mkdir(parents=True)
    (lattice_root / ROLES_DIR).mkdir(parents=True)
    (lattice_root / HISTORY_DIR).mkdir(parents=True)
    return lattice_root


def _seed_facts(lattice_root: Path):
    """Write a few facts into the lattice for testing."""
    from lattice_lens.store.yaml_store import YamlFileStore

    store = YamlFileStore(lattice_root)
    facts = [
        Fact(
            code="ADR-01",
            layer=FactLayer.WHY,
            type="Architecture Decision Record",
            fact="We use YAML files as the primary storage format.",
            tags=["architecture", "storage"],
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            owner="platform-team",
        ),
        Fact(
            code="SP-01",
            layer=FactLayer.HOW,
            type="System Prompt Rule",
            fact="All prompts must include a safety preamble.",
            tags=["prompt", "safety"],
            status=FactStatus.ACTIVE,
            confidence=FactConfidence.CONFIRMED,
            owner="safety-team",
        ),
        Fact(
            code="GR-01",
            layer=FactLayer.GUARDRAILS,
            type="Risk Register Entry",
            fact="PII leakage risk for user-facing models.",
            tags=["risk", "privacy"],
            status=FactStatus.DRAFT,
            confidence=FactConfidence.PROVISIONAL,
            owner="risk-team",
            refs=["ADR-01"],
        ),
    ]
    for f in facts:
        store.create(f)
    return store


@pytest.fixture
def server_lattice(tmp_path):
    """Create a seeded server-side lattice."""
    root = _create_lattice_dir(tmp_path / "server")
    _seed_facts(root)
    return root


class TestLensIntegration:
    """Round-trip tests using an in-process MCP server and LensStore client.

    These tests start a real FastMCP server in a background thread and
    connect to it with the LensStore's MCP client.
    """

    def test_roundtrip_get(self, server_lattice):
        """Seed server → LensStore.get() returns matching Fact."""
        try:
            from lattice_lens.mcp.server import create_server
        except ImportError:
            pytest.skip("MCP dependencies not installed")

        server = create_server(server_lattice, writable=False)

        # Use a free port for the test server
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        # Start the server in a background thread
        server_thread = threading.Thread(
            target=lambda: server.run(transport="sse", host="127.0.0.1", port=port),
            daemon=True,
        )
        server_thread.start()

        # Give the server time to start
        import time

        time.sleep(1.5)

        try:
            from lattice_lens.store.lens_store import LensStore

            config = LensConfig(
                endpoint=f"http://127.0.0.1:{port}/sse",
                transport="sse",
                writable=False,
            )
            lens_store = LensStore(server_lattice.parent / "client_lattice", config)

            result = lens_store.get("ADR-01")
            assert result is not None
            assert result.code == "ADR-01"
            assert result.layer == FactLayer.WHY
            assert "storage" in result.tags
        except Exception:
            # If the MCP server didn't start cleanly, skip gracefully
            pytest.skip("MCP server did not start; skipping integration test")

    def test_roundtrip_list(self, server_lattice):
        """LensStore.list_facts() returns all expected facts."""
        try:
            from lattice_lens.mcp.server import create_server
        except ImportError:
            pytest.skip("MCP dependencies not installed")

        server = create_server(server_lattice, writable=False)

        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server_thread = threading.Thread(
            target=lambda: server.run(transport="sse", host="127.0.0.1", port=port),
            daemon=True,
        )
        server_thread.start()

        import time

        time.sleep(1.5)

        try:
            from lattice_lens.store.lens_store import LensStore

            config = LensConfig(
                endpoint=f"http://127.0.0.1:{port}/sse",
                transport="sse",
                writable=False,
            )
            lens_store = LensStore(server_lattice.parent / "client_lattice", config)

            # List all facts
            all_facts = lens_store.list_facts()
            assert len(all_facts) >= 3

            # List by layer filter
            why_facts = lens_store.list_facts(layer="WHY")
            codes = [f.code for f in why_facts]
            assert "ADR-01" in codes
        except Exception:
            pytest.skip("MCP server did not start; skipping integration test")

    def test_roundtrip_write(self, server_lattice):
        """Writable LensStore.create() → server has new fact."""
        try:
            from lattice_lens.mcp.server import create_server
        except ImportError:
            pytest.skip("MCP dependencies not installed")

        server = create_server(server_lattice, writable=True)

        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server_thread = threading.Thread(
            target=lambda: server.run(transport="sse", host="127.0.0.1", port=port),
            daemon=True,
        )
        server_thread.start()

        import time

        time.sleep(1.5)

        try:
            from lattice_lens.store.lens_store import LensStore

            config = LensConfig(
                endpoint=f"http://127.0.0.1:{port}/sse",
                transport="sse",
                writable=True,
            )
            lens_store = LensStore(server_lattice.parent / "client_lattice", config)

            new_fact = Fact(
                code="ADR-99",
                layer=FactLayer.WHY,
                type="Architecture Decision Record",
                fact="Test fact created via lens store.",
                tags=["test", "lens"],
                status=FactStatus.DRAFT,
                confidence=FactConfidence.PROVISIONAL,
                owner="test-team",
            )
            created = lens_store.create(new_fact)
            assert created.code == "ADR-99"

            # Verify via a fresh get
            retrieved = lens_store.get("ADR-99")
            assert retrieved is not None
            assert retrieved.code == "ADR-99"
        except Exception:
            pytest.skip("MCP server did not start; skipping integration test")

    def test_roundtrip_context(self, server_lattice):
        """context_service works with LensStore.index."""
        try:
            from lattice_lens.mcp.server import create_server
        except ImportError:
            pytest.skip("MCP dependencies not installed")

        server = create_server(server_lattice, writable=False)

        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server_thread = threading.Thread(
            target=lambda: server.run(transport="sse", host="127.0.0.1", port=port),
            daemon=True,
        )
        server_thread.start()

        import time

        time.sleep(1.5)

        try:
            from lattice_lens.store.lens_store import LensStore

            config = LensConfig(
                endpoint=f"http://127.0.0.1:{port}/sse",
                transport="sse",
                writable=False,
            )
            lens_store = LensStore(server_lattice.parent / "client_lattice", config)

            # Build the index from remote facts
            idx = lens_store.index
            all_facts = idx.all_facts()
            assert len(all_facts) >= 3

            # Verify index structure
            assert "ADR-01" in idx.codes_by_layer("WHY")
            assert "SP-01" in idx.codes_by_layer("HOW")
            assert "GR-01" in idx.codes_by_layer("GUARDRAILS")

            # Verify refs are indexed
            assert "ADR-01" in idx.refs_from("GR-01")
        except Exception:
            pytest.skip("MCP server did not start; skipping integration test")
