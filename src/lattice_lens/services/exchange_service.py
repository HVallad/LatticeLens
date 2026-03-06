"""Import/export service for fact interchange."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.models import Fact
from lattice_lens.store.protocol import LatticeStore

yaml = YAML()
yaml.default_flow_style = False


def export_facts(store: LatticeStore, format: str = "json") -> str:
    """Export all facts from the store as JSON or YAML."""
    facts = store.list_facts(status=None)
    data = [f.model_dump(mode="json") for f in facts]

    if format == "json":
        return json.dumps(data, indent=2, default=str)
    elif format == "yaml":
        buf = StringIO()
        yaml.dump(data, buf)
        return buf.getvalue()
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'json' or 'yaml'.")


def import_facts(
    store: LatticeStore,
    data: str,
    format: str = "json",
    strategy: str = "skip",
) -> dict:
    """Import facts into the store.

    Strategies:
      skip: Skip facts whose code already exists (default)
      overwrite: Overwrite existing facts (preserves created_at, increments version)
      fail: Abort if any code already exists
    """
    if format == "json":
        raw = json.loads(data)
    elif format == "yaml":
        raw = yaml.load(data)
    else:
        raise ValueError(f"Unsupported format: {format}")

    results: dict = {"created": 0, "skipped": 0, "overwritten": 0, "errors": []}

    for item in raw:
        try:
            fact = Fact(**item)
            if store.exists(fact.code):
                if strategy == "skip":
                    results["skipped"] += 1
                elif strategy == "overwrite":
                    # Strip immutable fields per AUP-02/03/05: let store
                    # preserve created_at and auto-increment version.
                    changes = fact.model_dump(mode="json")
                    changes.pop("created_at", None)
                    changes.pop("version", None)
                    store.update(fact.code, changes, "Imported (overwrite)")
                    results["overwritten"] += 1
                elif strategy == "fail":
                    raise FileExistsError(f"Fact {fact.code} already exists")
            else:
                store.create(fact)
                results["created"] += 1
        except FileExistsError:
            raise  # Propagate fail-strategy aborts
        except Exception as e:
            results["errors"].append({"code": item.get("code", "?"), "error": str(e)})

    return results


def detect_format(path: Path) -> str:
    """Auto-detect format from file extension."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    elif suffix in (".yaml", ".yml"):
        return "yaml"
    else:
        raise ValueError(
            f"Cannot detect format from extension '{suffix}'. "
            "Use --format to specify 'json' or 'yaml'."
        )
