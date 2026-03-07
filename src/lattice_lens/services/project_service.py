"""Project registry — project scoping and group resolution for multi-project lattices."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

yaml_rw = YAML()
yaml_rw.default_flow_style = False

PROJECTS_FILE = "projects.yaml"

GROUP_PREFIX = "group:"


def read_project_registry(lattice_root: Path) -> dict | None:
    """Read the project registry from .lattice/projects.yaml.

    Returns {"projects": [...], "groups": {...}} or None if file missing.
    """
    path = lattice_root / PROJECTS_FILE
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml_rw.load(f)
    if data is None:
        return None
    return {
        "projects": list(data.get("projects", [])),
        "groups": dict(data.get("groups", {})),
    }


def write_project_registry(
    lattice_root: Path,
    projects: list[str],
    groups: dict[str, list[str]] | None = None,
) -> Path:
    """Write the project registry to .lattice/projects.yaml."""
    path = lattice_root / PROJECTS_FILE
    data: dict = {"projects": sorted(projects)}
    if groups:
        data["groups"] = {k: sorted(v) for k, v in sorted(groups.items())}
    with open(path, "w") as f:
        yaml_rw.dump(data, f)
    return path


def is_scoping_enabled(lattice_root: Path) -> bool:
    """True if projects.yaml exists, enabling project scoping."""
    return (lattice_root / PROJECTS_FILE).exists()


def resolve_projects(entries: list[str], registry: dict | None) -> set[str]:
    """Expand group: references and return a flat set of project names.

    - Plain strings pass through as literal project names.
    - "group:xxx" expands to the group's member list from the registry.
    - If registry is None (no projects.yaml), returns the entries as-is
      with group: prefixes stripped (best-effort).

    Raises ValueError if a group: reference doesn't exist in the registry.
    """
    if not entries:
        return set()

    resolved: set[str] = set()
    for entry in entries:
        if entry.startswith(GROUP_PREFIX):
            group_name = entry[len(GROUP_PREFIX):]
            if registry is None:
                raise ValueError(
                    f"Group reference '{entry}' used but no projects.yaml exists"
                )
            groups = registry.get("groups", {})
            if group_name not in groups:
                raise ValueError(
                    f"Unknown group '{group_name}' in '{entry}'. "
                    f"Available groups: {sorted(groups.keys())}"
                )
            resolved.update(groups[group_name])
        else:
            resolved.add(entry)

    return resolved


def fact_matches_project(
    fact_projects: list[str],
    active_project: str,
    registry: dict | None = None,
) -> bool:
    """Check if a fact is visible to the given active project.

    Rules:
    - Empty fact_projects (global fact) → always visible
    - Otherwise, resolve the fact's project entries and check membership
    """
    if not fact_projects:
        return True  # Global fact — visible everywhere

    resolved = resolve_projects(fact_projects, registry)
    return active_project in resolved


def validate_project_registry(registry: dict) -> list[str]:
    """Validate a project registry for consistency.

    Returns a list of error strings (empty = valid).

    Checks:
    - All group members must exist in the projects list
    - No group name may collide with a project name
    """
    errors: list[str] = []
    projects = set(registry.get("projects", []))
    groups = registry.get("groups", {})

    # Check for name collisions
    for group_name in groups:
        if group_name in projects:
            errors.append(
                f"Group name '{group_name}' collides with a project name. "
                "Groups and projects must have distinct names."
            )

    # Check that all group members are known projects
    for group_name, members in groups.items():
        for member in members:
            if member not in projects:
                errors.append(
                    f"Group '{group_name}' references unknown project '{member}'. "
                    f"Known projects: {sorted(projects)}"
                )

    return errors


def validate_fact_projects(
    fact_projects: list[str],
    registry: dict,
) -> list[str]:
    """Validate a fact's projects field against the registry.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []
    projects = set(registry.get("projects", []))
    groups = registry.get("groups", {})

    for entry in fact_projects:
        if entry.startswith(GROUP_PREFIX):
            group_name = entry[len(GROUP_PREFIX):]
            if group_name not in groups:
                errors.append(
                    f"Unknown group reference '{entry}'. "
                    f"Available groups: {sorted(groups.keys())}"
                )
        else:
            if entry not in projects:
                errors.append(
                    f"Unknown project '{entry}'. "
                    f"Known projects: {sorted(projects)}"
                )

    return errors
