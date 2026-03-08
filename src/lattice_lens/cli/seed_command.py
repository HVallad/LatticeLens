"""lattice seed — load example facts."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from ruamel.yaml import YAML

from lattice_lens.cli.helpers import require_local_lattice
from lattice_lens.models import Fact, FactConfidence, FactLayer, FactStatus

console = Console()
err_console = Console(stderr=True)
yaml_rw = YAML()
yaml_rw.default_flow_style = False


def _find_seed_file() -> Path | None:
    """Look for seed/example_facts.yaml relative to package or cwd."""
    candidates = [
        Path.cwd() / "seed" / "example_facts.yaml",
        Path(__file__).resolve().parent.parent.parent.parent / "seed" / "example_facts.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# Placeholder facts for missing ref targets
PLACEHOLDER_CODES = {
    "RISK-03": ("GUARDRAILS", "Risk Assessment Finding"),
    "RISK-05": ("GUARDRAILS", "Risk Assessment Finding"),
    "RISK-02": ("GUARDRAILS", "Risk Assessment Finding"),
    "ETH-01": ("WHY", "Ethics Principle"),
    "ETH-02": ("WHY", "Ethics Principle"),
    "AUP-01": ("GUARDRAILS", "Acceptable Use Policy Rule"),
    "AUP-02": ("GUARDRAILS", "Acceptable Use Policy Rule"),
    "SP-03": ("HOW", "System Prompt Rule"),
    "MON-04": ("HOW", "Monitoring Rule"),
    "DG-03": ("GUARDRAILS", "Data Governance Rule"),
    "COMP-01": ("GUARDRAILS", "Compliance Requirement"),
    "COMP-04": ("GUARDRAILS", "Compliance Requirement"),
    "MON-03": ("HOW", "Monitoring Rule"),
    "ML-01": ("HOW", "ML Pipeline Rule"),
    "PRD-02": ("WHY", "Product Requirement"),
}


def seed(
    force: bool = typer.Option(False, "--force", help="Overwrite existing facts"),
):
    """Load 12 example facts + placeholder drafts into .lattice/facts/."""
    store = require_local_lattice()

    seed_file = _find_seed_file()
    if seed_file is None:
        err_console.print(
            "[red]Error:[/red] seed/example_facts.yaml not found. Run from the project root."
        )
        raise typer.Exit(1)

    with open(seed_file) as f:
        seed_data = yaml_rw.load(f)

    if not isinstance(seed_data, list):
        err_console.print("[red]Error:[/red] Seed file must be a YAML list of facts")
        raise typer.Exit(1)

    created = 0
    skipped = 0

    for item in seed_data:
        code = item.get("code", "UNKNOWN")
        if store.exists(code) and not force:
            console.print(f"[dim]Skipping {code} (exists)[/dim]")
            skipped += 1
            continue

        try:
            fact = Fact(**item)
        except Exception as e:
            err_console.print(f"[red]Error in {code}:[/red] {e}")
            continue

        if store.exists(code) and force:
            # Remove existing and recreate
            (store.facts_dir / f"{code}.yaml").unlink()
            store.invalidate_index()

        store.create(fact)
        created += 1

    # Create placeholder drafts for missing ref targets
    placeholder_count = 0
    for code, (layer_name, fact_type) in PLACEHOLDER_CODES.items():
        if store.exists(code) and not force:
            continue

        if store.exists(code) and force:
            (store.facts_dir / f"{code}.yaml").unlink()
            store.invalidate_index()

        try:
            placeholder = Fact(
                code=code,
                layer=FactLayer(layer_name),
                type=fact_type,
                fact=f"Placeholder for {code} — to be filled in.",
                tags=["placeholder", "draft"],
                status=FactStatus.DRAFT,
                confidence=FactConfidence.PROVISIONAL,
                owner="system",
            )
            store.create(placeholder)
            placeholder_count += 1
        except Exception as e:
            err_console.print(f"[red]Error creating placeholder {code}:[/red] {e}")

    console.print(
        f"\n[green]Seeded[/green] {created} fact(s), "
        f"{placeholder_count} placeholder(s), "
        f"{skipped} skipped."
    )
