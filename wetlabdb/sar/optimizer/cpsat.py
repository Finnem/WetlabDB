"""CP-SAT lexicographic solver for the discrete depiction selection model."""

from __future__ import annotations

from typing import Any, Callable

from wetlabdb.sar.hardening.completion import (
    infeasible_in_template_set,
    optimization_incomplete,
    optimizer_result_from_policy,
)
from wetlabdb.sar.hardening.limits import MAX_OPTIMIZER_TIME_SECONDS
from wetlabdb.sar.optimizer.core import public_selection
from wetlabdb.sar.optimizer.oracle import solve_case as oracle_solve_case

try:
    from ortools.sat.python import cp_model as _cp_model_check
except ImportError:  # pragma: no cover
    _cp_model_check = None  # type: ignore[assignment,misc]


class OptimizerCancelled(Exception):
    """Raised when a solve is cancelled before completion."""


def _build_selection(
    case: dict[str, Any],
    assignment: dict[tuple[str, int], int],
) -> dict[str, dict[str, Any]]:
    selection: dict[str, dict[str, Any]] = {}
    for mol_id, candidates in case["molecules"].items():
        for idx, candidate in enumerate(candidates):
            if assignment.get((mol_id, idx), 0):
                selection[mol_id] = candidate
                break
    return selection


def _require_ortools():
    if _cp_model_check is None:
        raise ImportError(
            "ortools is required for CP-SAT optimization. "
            "Install with: pip install ortools"
        )
    return _cp_model_check


def _make_collector_class():
    cm = _require_ortools()

    class SolutionCollector(cm.CpSolverSolutionCallback):
        def __init__(
            self,
            case: dict[str, Any],
            x: dict[tuple[str, int], Any],
        ) -> None:
            cm.CpSolverSolutionCallback.__init__(self)
            self._case = case
            self._x = x
            self.selections: list[dict[str, str]] = []

        def on_solution_callback(self) -> None:
            assignment = {key: self.Value(var) for key, var in self._x.items()}
            selection = _build_selection(self._case, assignment)
            self.selections.append(public_selection(selection))

    return SolutionCollector


def _pairwise_penalty_var(
    model: Any,
    lit_a: Any,
    lit_b: Any,
) -> Any:
    z = model.NewBoolVar("pair_penalty")
    model.Add(z <= lit_a)
    model.Add(z <= lit_b)
    model.Add(z >= lit_a + lit_b - 1)
    return z


def _add_constraints(
    model: Any,
    case: dict[str, Any],
    x: dict[tuple[str, int], Any],
) -> list[Any]:
    mismatch_vars: list[Any] = []
    for mol_id, candidates in case["molecules"].items():
        model.AddExactlyOne(x[(mol_id, idx)] for idx in range(len(candidates)))

    for forbidden in case.get("forbidden", []):
        lits = []
        for tag in forbidden:
            mol_id, cand_id = tag.split(":", 1)
            for idx, candidate in enumerate(case["molecules"][mol_id]):
                if candidate["id"] == cand_id:
                    lits.append(x[(mol_id, idx)])
                    break
            else:
                raise ValueError(f"Unknown forbidden tag {tag!r}")
        if len(lits) >= 2:
            model.Add(sum(lits) <= len(lits) - 1)

    if case.get("require_common_template"):
        templates: set[str] = set()
        for candidates in case["molecules"].values():
            for candidate in candidates:
                template = candidate.get("template")
                if template is not None:
                    templates.add(str(template))
        template_list = sorted(templates)
        for t1 in template_list:
            for t2 in template_list:
                if t1 >= t2:
                    continue
                for mol_a, cands_a in case["molecules"].items():
                    for idx_a, ca in enumerate(cands_a):
                        if ca.get("template") != t1:
                            continue
                        for mol_b, cands_b in case["molecules"].items():
                            for idx_b, cb in enumerate(cands_b):
                                if cb.get("template") != t2:
                                    continue
                                model.Add(x[(mol_a, idx_a)] + x[(mol_b, idx_b)] <= 1)

    for term in case.get("pairwise", []):
        mol_a = term["a"]
        mol_b = term["b"]
        for idx_a, ca in enumerate(case["molecules"][mol_a]):
            for idx_b, cb in enumerate(case["molecules"][mol_b]):
                if ca["id"] == cb["id"]:
                    continue
                mismatch_vars.append(
                    _pairwise_penalty_var(model, x[(mol_a, idx_a)], x[(mol_b, idx_b)])
                )
    return mismatch_vars


def _level_cost(
    case: dict[str, Any],
    x: dict[tuple[str, int], Any],
    mismatch_vars: list[Any],
    level: int,
    pairwise_terms: list[dict[str, Any]],
) -> Any:
    terms: list[Any] = []
    for mol_id, candidates in case["molecules"].items():
        for idx, candidate in enumerate(candidates):
            cost = int(candidate["cost"][level])
            if cost:
                terms.append(x[(mol_id, idx)] * cost)

    mismatch_idx = 0
    for term in pairwise_terms:
        mol_a = term["a"]
        mol_b = term["b"]
        diff_cost = int(term["different_cost"][level])
        for idx_a, ca in enumerate(case["molecules"][mol_a]):
            for idx_b, cb in enumerate(case["molecules"][mol_b]):
                if ca["id"] == cb["id"]:
                    continue
                if diff_cost:
                    terms.append(mismatch_vars[mismatch_idx] * diff_cost)
                mismatch_idx += 1
    if not terms:
        return 0
    return sum(terms)  # type: ignore[return-value]


def solve_case(
    case: dict[str, Any],
    levels: int,
    *,
    cancel_flag: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Lexicographic CP-SAT solve with full optimal-set enumeration."""
    cp_model = _require_ortools()
    SolutionCollector = _make_collector_class()
    audit = oracle_solve_case(case, levels)
    pairwise_terms = list(case.get("pairwise", []))

    fixed_prefix: list[int] = []
    best: tuple[int, ...] | None = None

    for level in range(levels):
        if cancel_flag and cancel_flag():
            raise OptimizerCancelled("cancelled during lexicographic solve")

        model = cp_model.CpModel()
        x_level: dict[tuple[str, int], Any] = {}
        for mol_id, candidates in case["molecules"].items():
            for idx in range(len(candidates)):
                x_level[(mol_id, idx)] = model.NewBoolVar(f"x_{mol_id}_{idx}")
        mismatch_level = _add_constraints(model, case, x_level)

        for prior, value in enumerate(fixed_prefix):
            expr = _level_cost(case, x_level, mismatch_level, prior, pairwise_terms)
            model.Add(expr == value)

        obj = _level_cost(case, x_level, mismatch_level, level, pairwise_terms)
        model.Minimize(obj)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = MAX_OPTIMIZER_TIME_SECONDS
        status = solver.Solve(model)
        if status == cp_model.FEASIBLE:
            return optimizer_result_from_policy(
                case["id"],
                optimization_incomplete(),
                audit=audit,
            )
        if status != cp_model.OPTIMAL:
            return optimizer_result_from_policy(
                case["id"],
                infeasible_in_template_set(),
                audit=audit,
            )

        fixed_prefix.append(int(solver.ObjectiveValue()))

    best = tuple(fixed_prefix)

    enum_model = cp_model.CpModel()
    x_enum: dict[tuple[str, int], Any] = {}
    for mol_id, candidates in case["molecules"].items():
        for idx in range(len(candidates)):
            x_enum[(mol_id, idx)] = enum_model.NewBoolVar(f"x_{mol_id}_{idx}")
    mismatch_enum = _add_constraints(enum_model, case, x_enum)
    for level_idx in range(levels):
        expr = _level_cost(case, x_enum, mismatch_enum, level_idx, pairwise_terms)
        enum_model.Add(expr == best[level_idx])

    collector = SolutionCollector(case, x_enum)
    enum_solver = cp_model.CpSolver()
    enum_solver.parameters.enumerate_all_solutions = True
    enum_solver.SearchForAllSolutions(enum_model, collector)

    if not collector.selections:
        return optimizer_result_from_policy(
            case["id"],
            infeasible_in_template_set(),
            audit=audit,
        )

    return {
        "id": case["id"],
        "status": "OPTIMAL",
        "optimum": list(best),
        "selections": collector.selections,
        "evaluated": audit["evaluated"],
        "feasible": audit["feasible"],
    }


__all__ = ["OptimizerCancelled", "solve_case"]
