"""In-memory index built by scanning .lattice/facts/."""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.models import EdgeType, Fact, FactStatus

yaml = YAML()

# Inverse labels for display (e.g. "drives" → "driven_by")
INVERSE_LABELS: dict[EdgeType, str] = {
    EdgeType.DRIVES: "driven_by",
    EdgeType.CONSTRAINS: "constrained_by",
    EdgeType.MITIGATES: "mitigated_by",
    EdgeType.CONTRADICTS: "contradicted_by",
    EdgeType.IMPLEMENTS: "implemented_by",
    EdgeType.SUPERSEDES: "superseded_by",
    EdgeType.VALIDATES: "validated_by",
    EdgeType.DEPENDS_ON: "depended_on_by",
    EdgeType.RELATES: "related_to",
}


class FactIndex:
    """In-memory index built by scanning .lattice/facts/."""

    def __init__(self):
        self._facts: dict[str, Fact] = {}  # code -> Fact
        self._by_tag: dict[str, set[str]] = {}  # tag -> {codes}
        self._by_layer: dict[str, set[str]] = {}  # layer -> {codes}
        self._refs_forward: dict[str, set[str]] = {}  # code -> {referenced codes}
        self._refs_reverse: dict[str, set[str]] = {}  # code -> {codes that reference this}
        self._edges_forward: dict[str, dict[str, EdgeType]] = {}  # code -> {target: edge_type}
        self._edges_reverse: dict[str, dict[str, EdgeType]] = {}  # code -> {source: edge_type}
        self._by_project: dict[str, set[str]] = {}  # project -> {codes}
        self._global_codes: set[str] = set()  # codes with empty projects (global)

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
        # Ref graph (untyped — backward compat)
        self._refs_forward[fact.code] = set(r.code for r in fact.refs)
        for ref in fact.refs:
            self._refs_reverse.setdefault(ref.code, set()).add(fact.code)
        # Typed edge graph
        self._edges_forward[fact.code] = {r.code: r.rel for r in fact.refs}
        for ref in fact.refs:
            self._edges_reverse.setdefault(ref.code, {})[fact.code] = ref.rel
        # Project index
        if fact.projects:
            for project in fact.projects:
                self._by_project.setdefault(project, set()).add(fact.code)
        else:
            self._global_codes.add(fact.code)

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

    def edges_from(
        self, code: str, edge_types: list[EdgeType] | None = None
    ) -> dict[str, EdgeType]:
        """Return {target_code: edge_type} for outgoing edges from code.

        If edge_types is provided, only return edges matching those types.
        """
        edges = self._edges_forward.get(code, {})
        if edge_types is None:
            return dict(edges)
        return {k: v for k, v in edges.items() if v in edge_types}

    def edges_to(self, code: str, edge_types: list[EdgeType] | None = None) -> dict[str, EdgeType]:
        """Return {source_code: edge_type} for incoming edges to code.

        If edge_types is provided, only return edges matching those types.
        """
        edges = self._edges_reverse.get(code, {})
        if edge_types is None:
            return dict(edges)
        return {k: v for k, v in edges.items() if v in edge_types}

    def neighborhood(
        self,
        seeds: set[str],
        max_depth: int = 1,
        edge_types: list[EdgeType] | None = None,
        excluded_statuses: set[FactStatus] | None = None,
    ) -> dict[str, int]:
        """BFS from seed codes, returning {code: hop_distance}.

        Traverses both forward and reverse edges. Seeds are at distance 0.
        max_depth=-1 means unbounded. Skips facts with excluded statuses.
        """
        if excluded_statuses is None:
            excluded_statuses = set()

        result: dict[str, int] = {}
        for seed in seeds:
            result[seed] = 0

        queue: deque[tuple[str, int]] = deque()
        for seed in seeds:
            queue.append((seed, 0))

        visited = set(seeds)

        while queue:
            code, depth = queue.popleft()
            if max_depth != -1 and depth >= max_depth:
                continue

            # Collect neighbors from both directions
            neighbors: dict[str, EdgeType] = {}
            neighbors.update(self.edges_from(code, edge_types))
            neighbors.update(self.edges_to(code, edge_types))

            for neighbor_code in neighbors:
                if neighbor_code in visited:
                    continue
                visited.add(neighbor_code)

                # Check if the neighbor fact exists and is not excluded
                neighbor_fact = self.get(neighbor_code)
                if neighbor_fact is None:
                    continue
                if neighbor_fact.status in excluded_statuses:
                    continue

                result[neighbor_code] = depth + 1
                queue.append((neighbor_code, depth + 1))

        return result

    def codes_by_project(self, project: str) -> set[str]:
        return self._by_project.get(project, set())

    def global_codes(self) -> set[str]:
        return set(self._global_codes)
