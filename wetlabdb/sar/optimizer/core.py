"""Shared discrete selection model (fixture format v0.1)."""

from __future__ import annotations

from typing import Any


def add_vectors(left: tuple[int, ...], right: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    if len(left) != len(right):
        raise ValueError("objective vectors have different lengths")
    return tuple(a + b for a, b in zip(left, right))


def selection_key(selection: dict[str, dict[str, Any]]) -> set[str]:
    return {f"{molecule_id}:{candidate['id']}" for molecule_id, candidate in selection.items()}


def is_feasible(case: dict[str, Any], selection: dict[str, dict[str, Any]]) -> bool:
    chosen = selection_key(selection)
    for forbidden in case.get("forbidden", []):
        if set(forbidden).issubset(chosen):
            return False
    if case.get("require_common_template"):
        templates = {candidate.get("template") for candidate in selection.values()}
        if None in templates or len(templates) != 1:
            return False
    return True


def objective_vector(
    case: dict[str, Any],
    selection: dict[str, dict[str, Any]],
    levels: int,
) -> tuple[int, ...]:
    result = (0,) * levels
    for candidate in selection.values():
        result = add_vectors(result, candidate["cost"])
    for term in case.get("pairwise", []):
        if selection[term["a"]]["id"] != selection[term["b"]]["id"]:
            result = add_vectors(result, term["different_cost"])
    return result


def public_selection(selection: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {molecule_id: candidate["id"] for molecule_id, candidate in selection.items()}


__all__ = [
    "add_vectors",
    "is_feasible",
    "objective_vector",
    "public_selection",
    "selection_key",
]
