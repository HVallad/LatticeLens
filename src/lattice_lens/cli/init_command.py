"""lattice init — create .lattice/ directory structure."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from ruamel.yaml import YAML

from lattice_lens.config import (
    CONFIG_FILE,
    FACTS_DIR,
    HISTORY_DIR,
    LATTICE_DIR,
    ROLES_DIR,
)

console = Console()
yaml_writer = YAML()
yaml_writer.default_flow_style = False

DEFAULT_CONFIG = {
    "backend": "yaml",
    "auto_promote": {
        "enabled": False,
        "threshold_days": 14,
    },
}

DEFAULT_ROLES = {
    "planning": {
        "name": "Planning Agent",
        "description": "Strategic planning and roadmap decisions",
        "layers": ["WHY"],
        "tags": ["architecture", "scaling", "performance-requirement"],
        "max_facts": 20,
    },
    "architecture": {
        "name": "Architecture Agent",
        "description": "System design and technical decisions",
        "layers": ["WHY", "GUARDRAILS"],
        "tags": ["architecture", "microservices", "decoupling", "api"],
        "max_facts": 30,
    },
    "implementation": {
        "name": "Implementation Agent",
        "description": "Code-level implementation guidance",
        "layers": ["HOW", "GUARDRAILS"],
        "tags": ["api", "system-prompt", "rate-limiting"],
        "max_facts": 25,
    },
    "qa": {
        "name": "QA Agent",
        "description": "Quality assurance and testing",
        "layers": ["GUARDRAILS", "HOW"],
        "tags": ["security", "compliance", "monitoring"],
        "max_facts": 20,
    },
    "deploy": {
        "name": "Deploy Agent",
        "description": "Deployment and operations",
        "layers": ["HOW"],
        "tags": ["deploy-time", "rollback", "monitoring", "ops-team"],
        "max_facts": 15,
    },
}

GITIGNORE_CONTENT = """# LatticeLens generated files
index.yaml
*.bak/
"""


def init(
    path: Optional[Path] = typer.Option(None, help="Directory to initialize in (default: cwd)"),
):
    """Create .lattice/ directory with default structure."""
    target = (path or Path.cwd()) / LATTICE_DIR

    if target.exists():
        console.print(f"[red]Error:[/red] {target} already exists.")
        raise typer.Exit(1)

    # Create directories
    (target / FACTS_DIR).mkdir(parents=True)
    (target / ROLES_DIR).mkdir(parents=True)
    (target / HISTORY_DIR).mkdir(parents=True)

    # Write config.yaml
    with open(target / CONFIG_FILE, "w") as f:
        yaml_writer.dump(DEFAULT_CONFIG, f)

    # Write role templates
    for role_name, role_data in DEFAULT_ROLES.items():
        with open(target / ROLES_DIR / f"{role_name}.yaml", "w") as f:
            yaml_writer.dump(role_data, f)

    # Write .gitignore
    with open(target / ".gitignore", "w") as f:
        f.write(GITIGNORE_CONTENT)

    console.print(f"[green]Initialized[/green] lattice at [bold]{target}[/bold]")
    console.print("  facts/    — store fact YAML files here")
    console.print("  roles/    — role query templates")
    console.print("  history/  — changelog (auto-managed)")
    console.print("\nNext: run [bold]lattice seed[/bold] to load example facts.")
