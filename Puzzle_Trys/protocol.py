"""Canonical execution helpers for released P3 DoT records."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def _step_number(step_id: str) -> int:
    match = re.search(r"\d+", step_id)
    if not match:
        raise ValueError(f"Malformed step identifier: {step_id!r}")
    return int(match.group())


def canonical_depths(record: dict[str, Any]) -> dict[int, list[str]]:
    serialized = {
        int(depth): sorted(step_ids, key=_step_number)
        for depth, step_ids in record["depths"].items()
    }
    expected = {int(step_id) for step_id in record["steps_dict"]}
    present = {_step_number(step_id) for layer in serialized.values() for step_id in layer}
    if present == expected:
        return dict(sorted(serialized.items()))
    if present - expected:
        raise ValueError(f"DAG contains unknown steps: {sorted(present - expected)}")

    edges = {tuple(map(int, edge)) for edge in record.get("int_edges", [])}
    for node in sorted(expected - present):
        if node - 1 in expected:
            edges.add((node - 1, node))
        elif node + 1 in expected:
            edges.add((node, node + 1))

    indegree = {node: 0 for node in expected}
    children: dict[int, list[int]] = defaultdict(list)
    for source, target in sorted(edges):
        if source not in expected or target not in expected:
            raise ValueError(f"Dependency references unknown step: {(source, target)}")
        children[source].append(target)
        indegree[target] += 1

    frontier = sorted(node for node, degree in indegree.items() if degree == 0)
    layers: dict[int, list[str]] = {}
    visited = 0
    depth = 0
    while frontier:
        layers[depth] = [f"Step {node}" for node in frontier]
        next_frontier: list[int] = []
        for node in frontier:
            visited += 1
            for child in children[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    next_frontier.append(child)
        frontier = sorted(next_frontier)
        depth += 1
    if visited != len(expected):
        raise ValueError("P3 dependency graph contains a cycle")
    return layers


def model_for_step(record: dict[str, Any], number: int) -> str:
    models = record["allo_model"]
    if not 1 <= number <= len(models):
        raise ValueError(f"Invalid Step id {number!r} for {len(models)} model assignments")
    return models[number - 1]
