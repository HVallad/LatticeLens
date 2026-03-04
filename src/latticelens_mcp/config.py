"""Configuration for the LatticeLens MCP server (per RUN-14)."""

import os
from dataclasses import dataclass


@dataclass
class MCPConfig:
    """MCP server configuration, loaded from LATTICELENS_* environment variables."""

    api_url: str = "http://localhost:8000/api/v1"
    transport: str = "stdio"  # "stdio" or "streamable-http"
    host: str = "0.0.0.0"  # HTTP transport only
    port: int = 8080  # HTTP transport only
    default_owner: str = "claude-agent"
    request_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "MCPConfig":
        return cls(
            api_url=os.environ.get("LATTICELENS_API_URL", cls.api_url),
            transport=os.environ.get("LATTICELENS_MCP_TRANSPORT", cls.transport),
            host=os.environ.get("LATTICELENS_MCP_HOST", cls.host),
            port=int(os.environ.get("LATTICELENS_MCP_PORT", str(cls.port))),
            default_owner=os.environ.get("LATTICELENS_MCP_OWNER", cls.default_owner),
            request_timeout=float(os.environ.get("LATTICELENS_MCP_TIMEOUT", str(cls.request_timeout))),
        )
