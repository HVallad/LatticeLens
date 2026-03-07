"""Lens file model — points a .lattice/ directory at a remote MCP server."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from lattice_lens.config import LENS_FILE


class LensConfig(BaseModel):
    """Parsed .lens file configuration.

    A lens file allows a project to connect to a remote lattice via MCP
    instead of hosting a full local .lattice/ directory.
    """

    version: str = "1.0"
    endpoint: str = Field(..., min_length=1)
    transport: str = Field(default="sse", pattern=r"^(sse|stdio)$")
    writable: bool = False
    project: str | None = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate the endpoint format based on expected transports."""
        # Allow HTTP(S) URLs (for SSE) and command paths (for stdio)
        if not v.startswith(("http://", "https://", "/")):
            raise ValueError(
                "Endpoint must be an HTTP(S) URL for SSE transport "
                "or an absolute command path for stdio transport"
            )
        return v


class LensModeError(Exception):
    """Raised when an operation is not supported in lens mode."""

    pass


class LensConnectionError(Exception):
    """Raised when the MCP connection to a remote lattice fails."""

    pass


def read_lens_file(lattice_root: Path) -> LensConfig | None:
    """Read and parse .lens file from a .lattice/ directory.

    Returns None if the file does not exist.
    """
    from ruamel.yaml import YAML

    lens_path = lattice_root / LENS_FILE
    if not lens_path.exists():
        return None
    yaml = YAML()
    with open(lens_path) as f:
        data = yaml.load(f)
    if data is None:
        return None
    return LensConfig(**data)


def write_lens_file(lattice_root: Path, config: LensConfig) -> Path:
    """Write a .lens file to the .lattice/ directory."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    lens_path = lattice_root / LENS_FILE
    with open(lens_path, "w") as f:
        yaml.dump(config.model_dump(mode="json", exclude_none=True), f)
    return lens_path


def remove_lens_file(lattice_root: Path) -> bool:
    """Remove .lens file. Returns True if the file existed and was removed."""
    lens_path = lattice_root / LENS_FILE
    if lens_path.exists():
        lens_path.unlink()
        return True
    return False
