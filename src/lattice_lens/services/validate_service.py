"""Schema and integrity validation for the lattice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML

from lattice_lens.config import LAYER_PREFIXES
from lattice_lens.models import Fact

yaml = YAML()


@dataclass
class ValidationResult:
    """Collects errors and warnings from a validation run."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)


def validate_lattice(facts_dir: Path) -> ValidationResult:
    """Run all integrity checks on the .lattice/facts/ directory."""
    result = ValidationResult()

    if not facts_dir.exists():
        result.add_error(f"Facts directory does not exist: {facts_dir}")
        return result

    yaml_files = sorted(facts_dir.glob("*.yaml"))
    if not yaml_files:
        result.add_warning("No fact files found")
        return result

    seen_codes: dict[str, str] = {}  # code -> filename
    all_codes: set[str] = set()
    all_facts: list[Fact] = []
    today = datetime.now().date()

    for path in yaml_files:
        # Check YAML parsing
        try:
            with open(path) as f:
                data = yaml.load(f)
        except Exception as e:
            result.add_error(f"{path.name}: YAML parse error: {e}")
            continue

        if data is None:
            result.add_error(f"{path.name}: Empty YAML file")
            continue

        # Check Pydantic validation
        try:
            fact = Fact(**data)
        except ValidationError as e:
            result.add_error(f"{path.name}: Validation error: {e}")
            continue

        # Check for duplicate codes
        if fact.code in seen_codes:
            result.add_error(
                f"{path.name}: Duplicate code '{fact.code}' (also in {seen_codes[fact.code]})"
            )
        else:
            seen_codes[fact.code] = path.name

        all_codes.add(fact.code)
        all_facts.append(fact)

        # Check code-layer prefix consistency
        prefix = fact.code.split("-")[0]
        allowed = LAYER_PREFIXES.get(fact.layer.value, [])
        if prefix not in allowed:
            result.add_error(
                f"{path.name}: Code prefix '{prefix}' not valid for layer "
                f"{fact.layer.value} (allowed: {allowed})"
            )

        # Superseded consistency is checked after all facts are loaded (see below)

        # Check staleness
        if fact.review_by and fact.review_by < today:
            result.add_warning(
                f"{path.name}: Fact '{fact.code}' is stale (review_by: {fact.review_by})"
            )

    # Check ref integrity (soft warnings)
    for fact in all_facts:
        for ref in fact.refs:
            if ref.code not in all_codes:
                result.add_warning(f"{fact.code}: Reference target '{ref.code}' does not exist")

    # Check superseded consistency — requires all facts to be loaded
    # Superseded facts need either superseded_by field OR an inbound supersedes edge
    from lattice_lens.models import EdgeType

    supersedes_targets: set[str] = set()
    for fact in all_facts:
        for ref in fact.refs:
            if ref.rel == EdgeType.SUPERSEDES:
                supersedes_targets.add(ref.code)

    for fact in all_facts:
        if fact.status.value == "Superseded":
            has_field = bool(fact.superseded_by)
            has_edge = fact.code in supersedes_targets
            if not has_field and not has_edge:
                result.add_error(
                    f"{fact.code}: Superseded fact has neither "
                    "superseded_by field nor inbound supersedes edge"
                )

    # Check type canonicality (RISK-03 mitigation)
    from lattice_lens.services.type_service import canonical_type_for_prefix

    for fact in all_facts:
        prefix = fact.code.split("-")[0]
        canonical = canonical_type_for_prefix(prefix)
        if canonical and fact.type != canonical:
            result.add_warning(
                f"{fact.code}: Type '{fact.type}' differs from canonical "
                f"'{canonical}' for prefix {prefix}"
            )

    # Check for frequent free tags (DG-07)
    from lattice_lens.services.tag_service import categorize_tag

    tag_counts: dict[str, int] = {}
    for fact in all_facts:
        for tag in fact.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    for tag, count in tag_counts.items():
        if count >= 3 and categorize_tag(tag) == "free":
            result.add_warning(
                f"Free tag '{tag}' appears in {count} facts. "
                "Consider adding to controlled vocabulary (DG-07)."
            )

    # Check project scoping consistency
    from lattice_lens.services.project_service import (
        is_scoping_enabled,
        read_project_registry,
        validate_fact_projects,
        validate_project_registry,
    )

    lattice_root = facts_dir.parent
    if is_scoping_enabled(lattice_root):
        registry = read_project_registry(lattice_root)
        if registry is not None:
            # Validate the registry itself
            for err in validate_project_registry(registry):
                result.add_error(f"projects.yaml: {err}")

            # Validate each fact's projects field
            for fact in all_facts:
                if fact.projects:
                    for err in validate_fact_projects(fact.projects, registry):
                        result.add_warning(f"{fact.code}: {err}")

    return result


def fix_lattice(facts_dir: Path) -> tuple[ValidationResult, int]:
    """Auto-correct fixable issues. Returns (result, files_fixed)."""
    result = ValidationResult()
    files_fixed = 0

    if not facts_dir.exists():
        result.add_error(f"Facts directory does not exist: {facts_dir}")
        return result, 0

    for path in sorted(facts_dir.glob("*.yaml")):
        try:
            with open(path) as f:
                data = yaml.load(f)
        except Exception:
            continue

        if data is None:
            continue

        changed = False

        # Fix tag normalization
        if "tags" in data and isinstance(data["tags"], list):
            original_tags = list(data["tags"])
            normalized = sorted(set(t.lower().strip() for t in data["tags"]))
            if normalized != original_tags:
                data["tags"] = normalized
                changed = True

        if changed:
            data["updated_at"] = datetime.now().isoformat()
            writer = YAML()
            writer.default_flow_style = False
            with open(path, "w") as f:
                writer.dump(data, f)
            files_fixed += 1
            result.add_warning(f"{path.name}: Auto-fixed tags")

    return result, files_fixed
