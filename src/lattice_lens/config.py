"""Settings and lattice directory discovery."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


LATTICE_DIR = ".lattice"
FACTS_DIR = "facts"
ROLES_DIR = "roles"
HISTORY_DIR = "history"
CONFIG_FILE = "config.yaml"
INDEX_FILE = "index.yaml"

# Schema version — minor version tracks phases, patch for fixes within a phase.
# "0.1.0" = Phase 1 (flat role templates)
# "0.2.0" = Phase 2 (nested query role templates, graph + git commands)
# "0.3.0" = Phase 5 (type registry, canonical types in role templates)
LATTICE_VERSION = "0.3.0"

LAYER_PREFIXES: dict[str, list[str]] = {
    "WHY": ["ADR", "PRD", "ETH", "DES"],
    "GUARDRAILS": ["MC", "AUP", "RISK", "DG", "COMP"],
    "HOW": ["SP", "API", "RUN", "ML", "MON"],
}


class Settings(BaseSettings):
    """Runtime settings. Resolved from env vars or config.yaml."""

    model_config = SettingsConfigDict(env_prefix="LATTICE_")

    lattice_root: Path | None = None  # auto-discovered from cwd upward

    # For LLM-powered extraction (Phase 4)
    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-4-20250514"


def find_lattice_root(start: Path | None = None) -> Path | None:
    """Walk up from start (default: cwd) looking for .lattice/ directory."""
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / LATTICE_DIR).is_dir():
            return parent / LATTICE_DIR
        if parent == parent.parent:
            break
    return None
