"""lattice upgrade — versioned migration runner for .lattice/ schema changes."""

from __future__ import annotations

import typer
from rich.console import Console
from ruamel.yaml import YAML

from lattice_lens.cli.helpers import require_lattice
from lattice_lens.config import CONFIG_FILE, LATTICE_VERSION, ROLES_DIR

console = Console()
err_console = Console(stderr=True)

yaml_rw = YAML()
yaml_rw.default_flow_style = False


def _read_config(store) -> dict:
    """Read .lattice/config.yaml."""
    config_path = store.root / CONFIG_FILE
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml_rw.load(f) or {}


def _write_config(store, config: dict):
    """Write .lattice/config.yaml."""
    with open(store.root / CONFIG_FILE, "w") as f:
        yaml_rw.dump(config, f)


def _current_version(config: dict) -> str:
    """Get the current lattice version from config, defaulting to 0.1.0."""
    return str(config.get("version", "0.1.0"))


# --- Migrations ---
# Each migration is a (target_version, description, callable) tuple.
# Migrations run in order. A migration is skipped if the lattice is already
# at or past that version.


def _migrate_to_0_2_0(store) -> int:
    """Migrate role templates from flat format to nested query format."""
    roles_dir = store.root / ROLES_DIR
    if not roles_dir.exists():
        return 0

    migrated = 0
    for path in sorted(roles_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml_rw.load(f)
        if data is None:
            continue

        # Detect old flat format: has top-level "layers" but no "query"
        if "layers" in data and "query" not in data:
            query = {
                "layers": data.pop("layers", []),
                "types": [],
                "tags": data.pop("tags", []),
                "max_facts": data.pop("max_facts", 20),
                "extra": [],
            }
            data["query"] = query
            with open(path, "w") as f:
                yaml_rw.dump(data, f)
            console.print(f"  [green]Migrated[/green] {path.name}")
            migrated += 1

    return migrated


def _migrate_to_0_3_0(store) -> int:
    """Seed type registry and fix non-canonical type strings in role templates."""
    changed = 0

    # Seed types.yaml if missing
    types_path = store.root / "types.yaml"
    if not types_path.exists():
        from lattice_lens.services.type_service import write_type_registry

        write_type_registry(store.root)
        console.print("  [green]Created[/green] types.yaml (canonical type registry)")
        changed += 1

    # Fix non-canonical type strings in role templates
    roles_dir = store.root / ROLES_DIR
    if roles_dir.exists():
        replacements = {
            "Risk Assessment Finding": "Risk Register Entry",
            "Runbook Entry": "Runbook Procedure",
            "API Contract": "API Specification",
            "Standard Procedure": "System Prompt Rule",
            "Monitoring Check": "Monitoring Rule",
        }
        for path in sorted(roles_dir.glob("*.yaml")):
            with open(path) as f:
                data = yaml_rw.load(f)
            if data is None or "query" not in data:
                continue
            types_list = data["query"].get("types", [])
            updated = False
            for i, t in enumerate(types_list):
                if t in replacements:
                    types_list[i] = replacements[t]
                    updated = True
            if updated:
                with open(path, "w") as f:
                    yaml_rw.dump(data, f)
                console.print(f"  [green]Fixed types in[/green] {path.name}")
                changed += 1

    return changed


def _migrate_to_0_4_0(store) -> int:
    """Upgrade types.yaml to enriched format with descriptions."""
    from lattice_lens.services.type_service import is_enriched_registry, read_type_registry, write_type_registry

    registry = read_type_registry(store.root)

    if registry is None:
        # types.yaml missing entirely — write enriched from scratch
        write_type_registry(store.root)
        console.print("  [green]Created[/green] types.yaml (enriched with descriptions)")
        return 1

    if is_enriched_registry(registry):
        return 0  # Already enriched

    # Flat format detected — regenerate with descriptions
    write_type_registry(store.root)
    console.print("  [green]Upgraded[/green] types.yaml (added type descriptions)")
    return 1


# Ordered list of migrations. Add new entries at the bottom for future phases.
MIGRATIONS: list[tuple[str, str, callable]] = [
    ("0.2.0", "Nested query format for role templates", _migrate_to_0_2_0),
    ("0.3.0", "Type registry and canonical type names in role templates", _migrate_to_0_3_0),
    ("0.4.0", "Enriched type registry with descriptions", _migrate_to_0_4_0),
]


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a version string like '0.2.0' into a comparable tuple."""
    return tuple(int(x) for x in v.split("."))


def upgrade():
    """Upgrade lattice to the latest schema version."""
    store = require_lattice()
    config = _read_config(store)
    current = _current_version(config)

    if _version_tuple(current) >= _version_tuple(LATTICE_VERSION):
        console.print(
            f"[dim]Lattice is already at v{current} (latest: v{LATTICE_VERSION}). "
            f"Nothing to upgrade.[/dim]"
        )
        return

    console.print(f"Upgrading lattice from v{current} to v{LATTICE_VERSION}...\n")

    applied = 0
    for target_version, description, migration_fn in MIGRATIONS:
        if _version_tuple(current) >= _version_tuple(target_version):
            continue  # Already past this migration

        console.print(f"[bold]v{target_version}:[/bold] {description}")
        count = migration_fn(store)
        if count:
            console.print(f"  {count} file(s) changed")
        else:
            console.print("  [dim]No changes needed[/dim]")
        applied += 1

    # Stamp the new version
    config["version"] = LATTICE_VERSION
    _write_config(store, config)

    console.print(
        f"\n[green]Upgrade complete:[/green] v{current} -> v{LATTICE_VERSION} "
        f"({applied} migration(s) applied)"
    )
