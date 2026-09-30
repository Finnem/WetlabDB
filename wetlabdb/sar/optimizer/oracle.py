"""Exhaustive oracle for tiny SAR depiction selection fixtures."""

from __future__ import annotations

import itertools
from typing import Any

from wetlabdb.sar.optimizer.core import is_feasible, objective_vector, public_selection


def solve_case(case: dict[str, Any], levels: int) -> dict[str, Any]:
    """Enumerate all assignments; return status, optimum, and tied optimal selections."""
    molecule_ids = list(case["molecules"])
    best: tuple[int, ...] | None = None
    solutions: list[dict[str, str]] = []
    evaluated = 0
    feasible = 0
    for combination in itertools.product(*(case["molecules"][m] for m in molecule_ids)):
        evaluated += 1
        selection = dict(zip(molecule_ids, combination))
        if not is_feasible(case, selection):
            continue
        feasible += 1
        value = objective_vector(case, selection, levels)
        pub = public_selection(selection)
        if best is None or value < best:
            best = value
            solutions = [pub]
        elif value == best:
            solutions.append(pub)
    return {
        "id": case["id"],
        "status": "INFEASIBLE" if best is None else "OPTIMAL",
        "optimum": None if best is None else list(best),
        "selections": solutions,
        "evaluated": evaluated,
        "feasible": feasible,
    }


__all__ = ["solve_case"]
