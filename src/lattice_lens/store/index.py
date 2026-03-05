"""In-memory index built by scanning .lattice/facts/."""

from __future__ import annotations

import sys
from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.models import Fact

yaml = YAML()


class FactIndex:
    """In-memory index built by scanning .lattice/facts/."""

    def __init__(self):
        self._facts: dict[str, Fact] = {}  # code -> Fact
        self._by_tag: dict[str, set[str]] = {}  # tag -> {codes}
        self._by_layer: dict[str, set[str]] = {}  # layer -> {codes}
        self._refs_forward: dict[str, set[str]] = {}  # code -> {referenced codes}
        self._refs_reverse: dict[str, set[str]] = {}  # code -> {codes that reference this}

    @classmethod
    def build(cls, facts_dir: Path) -> FactIndex:
        idx = cls()
        if not facts_dir.exists():
            return idx
        for path in sorted(facts_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.load(f)
                fact = Fact(**data)
                idx._add(fact)
            except Exception as e:
                # Log but don't crash — partial index is better than no index
                print(f"Warning: skipping {path.name}: {e}", file=sys.stderr)
        return idx

    def _add(self, fact: Fact):
        self._facts[fact.code] = fact
        # Tag index
        for tag in fact.tags:
            self._by_tag.setdefault(tag, set()).add(fact.code)
        # Layer index
        self._by_layer.setdefault(fact.layer.value, set()).add(fact.code)
        # Ref graph
        self._refs_forward[fact.code] = set(fact.refs)
        for ref in fact.refs:
            self._refs_reverse.setdefault(ref, set()).add(fact.code)

    def all_facts(self) -> list[Fact]:
        return list(self._facts.values())

    def get(self, code: str) -> Fact | None:
        return self._facts.get(code)

    def codes_by_tag(self, tag: str) -> set[str]:
        return self._by_tag.get(tag, set())

    def codes_by_layer(self, layer: str) -> set[str]:
        return self._by_layer.get(layer, set())

    def refs_from(self, code: str) -> set[str]:
        return self._refs_forward.get(code, set())

    def refs_to(self, code: str) -> set[str]:
        return self._refs_reverse.get(code, set())
