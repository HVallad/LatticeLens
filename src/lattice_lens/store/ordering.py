"""Topological ordering for fact insertion to satisfy foreign key constraints.

Facts may reference other facts via `superseded_by`, which has a FOREIGN KEY
constraint in SQLite. When bulk-inserting facts (e.g., during migration), the
referenced fact must be inserted before the fact that references it.

This module provides a topological sort that handles:
- superseded_by references (FOREIGN KEY on facts table)
- Cycles (breaks them gracefully by clearing the offending reference)
"""

from __future__ import annotations

from collections import deque

from lattice_lens.models import Fact


def topological_sort_facts(facts: list[Fact]) -> list[Fact]:
    """Sort facts so that dependencies (superseded_by targets) come first.

    If a cycle is detected, the cycle is broken by clearing superseded_by
    on one of the participating facts (the fact is mutated in place).

    Returns a new list in insertion-safe order.
    """
    if not facts:
        return []

    # Build lookup and dependency graph
    by_code: dict[str, Fact] = {f.code: f for f in facts}
    # in_degree[code] = number of facts that must be inserted before code
    in_degree: dict[str, int] = {f.code: 0 for f in facts}
    # dependents[code] = list of codes that depend on code being inserted first
    dependents: dict[str, list[str]] = {f.code: [] for f in facts}

    for fact in facts:
        dep = fact.superseded_by
        if dep and dep in by_code:
            # fact depends on dep being inserted first
            in_degree[fact.code] += 1
            dependents[dep].append(fact.code)

    # Kahn's algorithm
    queue: deque[str] = deque()
    for code, degree in in_degree.items():
        if degree == 0:
            queue.append(code)

    result: list[Fact] = []
    while queue:
        code = queue.popleft()
        result.append(by_code[code])
        for dependent in dependents[code]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # If not all facts are in result, there's a cycle
    if len(result) < len(facts):
        remaining = {code for code, deg in in_degree.items() if code not in {f.code for f in result}}
        # Break cycles by clearing superseded_by for facts still stuck
        for code in remaining:
            fact = by_code[code]
            if fact.superseded_by and fact.superseded_by in remaining:
                # Clear the reference to break the cycle
                fact.superseded_by = None
        # Re-run on the remaining facts
        remaining_facts = [by_code[code] for code in remaining]
        result.extend(topological_sort_facts(remaining_facts))

    return result
