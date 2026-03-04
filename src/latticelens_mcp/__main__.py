"""LatticeLens MCP Server entry point (per RUN-14).

Usage:
  python -m latticelens_mcp                      # stdio (default)
  python -m latticelens_mcp --transport stdio     # explicit stdio
  python -m latticelens_mcp --transport http      # streamable-http
"""

import sys

from latticelens_mcp.config import MCPConfig
from latticelens_mcp.server import create_server


def main():
    config = MCPConfig.from_env()

    # Allow CLI override for transport
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            config.transport = sys.argv[idx + 1]

    server = create_server(config)

    if config.transport == "stdio":
        server.run(transport="stdio")
    elif config.transport in ("http", "streamable-http"):
        server.run(
            transport="streamable-http",
            host=config.host,
            port=config.port,
        )
    else:
        print(f"Unknown transport: {config.transport}", file=sys.stderr)
        print("Valid options: stdio, http, streamable-http", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
