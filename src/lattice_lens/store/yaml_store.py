"""YamlFileStore — reads/writes facts as individual YAML files in .lattice/facts/."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.config import FACTS_DIR, HISTORY_DIR
from lattice_lens.models import Fact
from lattice_lens.services.project_service import fact_matches_project, read_project_registry
from lattice_lens.store.index import FactIndex

yaml = YAML()
yaml.default_flow_style = False


class YamlFileStore:
    def __init__(self, lattice_root: Path):
        self.root = lattice_root
        self.facts_dir = lattice_root / FACTS_DIR
        self.history_dir = lattice_root / HISTORY_DIR
        self._index: FactIndex | None = None

    @property
    def index(self) -> FactIndex:
        if self._index is None:
            self._index = FactIndex.build(self.facts_dir)
        return self._index

    def invalidate_index(self):
        self._index = None

    def get(self, code: str) -> Fact | None:
        path = self.facts_dir / f"{code}.yaml"
        if not path.exists():
            return None
        return self._read_fact(path)

    def list_facts(self, **filters) -> list[Fact]:
        """
        Supported filters:
          layer: str | list[str]
          status: str | list[str]  (default: ["Active"])
          tags_any: list[str]      (match ANY tag)
          tags_all: list[str]      (match ALL tags)
          type: str | list[str]
          text_search: str         (substring match on fact text)
        """
        facts = self.index.all_facts()

        # Apply filters
        layer = filters.get("layer")
        if layer:
            layers = [layer] if isinstance(layer, str) else layer
            facts = [f for f in facts if f.layer.value in layers]

        status = filters.get("status", ["Active"])
        if status:
            statuses = [status] if isinstance(status, str) else status
            facts = [f for f in facts if f.status.value in statuses]

        tags_any = filters.get("tags_any")
        if tags_any:
            facts = [f for f in facts if set(f.tags) & set(tags_any)]

        tags_all = filters.get("tags_all")
        if tags_all:
            tag_set = set(tags_all)
            facts = [f for f in facts if tag_set.issubset(set(f.tags))]

        type_filter = filters.get("type")
        if type_filter:
            types = [type_filter] if isinstance(type_filter, str) else type_filter
            facts = [f for f in facts if f.type in types]

        text_search = filters.get("text_search")
        if text_search:
            query = text_search.lower()
            facts = [f for f in facts if query in f.fact.lower()]

        project = filters.get("project")
        if project:
            registry = read_project_registry(self.root)
            facts = [f for f in facts if fact_matches_project(f.projects, project, registry)]

        return facts

    def create(self, fact: Fact) -> Fact:
        path = self.facts_dir / f"{fact.code}.yaml"
        if path.exists():
            raise FileExistsError(f"Fact {fact.code} already exists")
        self._write_fact(path, fact)
        self._append_changelog("create", fact.code, "Initial creation")
        self.invalidate_index()
        return fact

    def update(self, code: str, changes: dict, reason: str) -> Fact:
        current = self.get(code)
        if current is None:
            raise FileNotFoundError(f"Fact {code} not found")

        # Build updated fact
        data = current.model_dump()
        data.update(changes)
        data["version"] = current.version + 1
        data["updated_at"] = datetime.now()
        updated = Fact(**data)

        self._write_fact(self.facts_dir / f"{code}.yaml", updated)
        self._append_changelog("update", code, reason)
        self.invalidate_index()
        return updated

    def deprecate(self, code: str, reason: str) -> Fact:
        return self.update(code, {"status": "Deprecated"}, reason)

    def exists(self, code: str) -> bool:
        return (self.facts_dir / f"{code}.yaml").exists()

    def all_codes(self) -> list[str]:
        return [p.stem for p in self.facts_dir.glob("*.yaml")]

    def stats(self) -> dict:
        facts = self.index.all_facts()
        by_layer: dict[str, int] = {}
        by_status: dict[str, int] = {}
        stale = 0
        today = datetime.now().date()
        for f in facts:
            by_layer[f.layer.value] = by_layer.get(f.layer.value, 0) + 1
            by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
            if f.review_by and f.review_by < today:
                stale += 1
        return {
            "total": len(facts),
            "by_layer": by_layer,
            "by_status": by_status,
            "stale": stale,
            "backend": "yaml",
        }

    # ── Private helpers ──

    def _read_fact(self, path: Path) -> Fact:
        with open(path) as f:
            data = yaml.load(f)
        return Fact(**data)

    def _write_fact(self, path: Path, fact: Fact):
        data = fact.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.dump(data, f)

    def _append_changelog(self, action: str, code: str, reason: str):
        self.history_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "code": code,
            "reason": reason,
        }
        changelog = self.history_dir / "changelog.jsonl"
        with open(changelog, "a") as f:
            f.write(json.dumps(entry) + "\n")
