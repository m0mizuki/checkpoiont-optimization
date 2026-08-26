"""Core checkpoint staffing model, adapted from checkpoint_counter_final.ipynb.

The module deliberately keeps the optimization backend independent of a web
framework.  It reproduces the notebook's demand distribution, QAE payoff
encoding, quadratic shortfall surrogate, and officer eligibility constraints.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
from math import ceil, pi
from typing import Any

import numpy as np


SKILL_KEYS = ("A", "B", "C", "D")
DEFAULT_PROBABILITIES = (0.1, 0.2, 0.4, 0.2, 0.1)


class ProblemError(ValueError):
    """Raised when a submitted problem is inconsistent or unsafe to solve."""


def default_problem() -> dict[str, Any]:
    return {
        "title": "Checkpoint Counter Staffing",
        "skills": [
            {"key": "A", "label": "Human", "cv": 0.20, "open_cost": 1.0, "shortage_penalty": 10.0},
            {"key": "B", "label": "Motorcycle", "cv": 0.30, "open_cost": 1.0, "shortage_penalty": 15.0},
            {"key": "C", "label": "Car", "cv": 0.25, "open_cost": 1.0, "shortage_penalty": 10.0},
            {"key": "D", "label": "Truck", "cv": 0.35, "open_cost": 1.0, "shortage_penalty": 10.0},
        ],
        "periods": ["Morning", "Lunch", "Afternoon", "Night"],
        "demand": {
            "Morning": {"A": 6, "B": 4, "C": 4, "D": 10},
            "Lunch": {"A": 7, "B": 4, "C": 6, "D": 8},
            "Afternoon": {"A": 6, "B": 5, "C": 5, "D": 8},
            "Night": {"A": 5, "B": 3, "C": 7, "D": 9},
        },
        "officer_classes": [
            {"name": "Class 1", "count": 23, "skills": ["A", "B", "C", "D"]},
            {"name": "Class 2", "count": 3, "skills": ["A", "C", "D"]},
            {"name": "Class 3", "count": 1, "skills": ["B", "C", "D"]},
            {"name": "Class 4", "count": 2, "skills": ["A", "D"]},
            {"name": "Class 5", "count": 1, "skills": ["C", "D"]},
        ],
        "probabilities": list(DEFAULT_PROBABILITIES),
        "solver": {
            "epsilon_target": 0.01,
            "alpha": 0.05,
            "alpha_open": 0.05,
            "one_officer_penalty": 20.0,
            "seed": 7,
        },
    }


def _number(value: Any, name: str, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ProblemError(f"{name} must be numeric.") from exc
    if not np.isfinite(parsed) or parsed < low or parsed > high:
        raise ProblemError(f"{name} must be between {low:g} and {high:g}.")
    return parsed


def validate_problem(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProblemError("The problem must be a JSON object.")
    problem = raw
    skills = problem.get("skills")
    periods = problem.get("periods")
    classes = problem.get("officer_classes")
    if not isinstance(skills, list) or [item.get("key") for item in skills if isinstance(item, dict)] != list(SKILL_KEYS):
        raise ProblemError("The four skill keys must remain A, B, C, and D.")
    if not isinstance(periods, list) or not 1 <= len(periods) <= 12:
        raise ProblemError("Provide between 1 and 12 time periods.")
    normalized_periods: list[str] = []
    for index, period in enumerate(periods):
        name = str(period).strip()
        if not name or len(name) > 40:
            raise ProblemError(f"Period {index + 1} needs a name of at most 40 characters.")
        if name in normalized_periods:
            raise ProblemError(f"Period names must be unique: {name}.")
        normalized_periods.append(name)
    problem["periods"] = normalized_periods

    normalized_skills = []
    for item in skills:
        key = item["key"]
        normalized_skills.append({
            "key": key,
            "label": str(item.get("label", key)).strip()[:40] or key,
            "cv": _number(item.get("cv"), f"CV for {key}", 0.01, 2.0),
            "open_cost": _number(item.get("open_cost"), f"Open cost for {key}", 0.0, 100000.0),
            "shortage_penalty": _number(item.get("shortage_penalty"), f"Shortage penalty for {key}", 0.0, 100000.0),
        })
    problem["skills"] = normalized_skills

    demand = problem.get("demand")
    if not isinstance(demand, dict):
        raise ProblemError("Demand must be provided for every period.")
    normalized_demand = {}
    for period in normalized_periods:
        row = demand.get(period)
        if not isinstance(row, dict):
            raise ProblemError(f"Demand is missing for {period}.")
        normalized_demand[period] = {
            key: int(_number(row.get(key), f"Demand {period}/{key}", 0, 100)) for key in SKILL_KEYS
        }
    problem["demand"] = normalized_demand

    if not isinstance(classes, list) or not 1 <= len(classes) <= 30:
        raise ProblemError("Provide between 1 and 30 officer classes.")
    normalized_classes = []
    total_officers = 0
    for index, officer_class in enumerate(classes):
        if not isinstance(officer_class, dict):
            raise ProblemError(f"Officer class {index + 1} is invalid.")
        count = int(_number(officer_class.get("count"), f"Count for class {index + 1}", 0, 100))
        allowed = [key for key in SKILL_KEYS if key in set(officer_class.get("skills") or [])]
        if count and not allowed:
            raise ProblemError(f"Officer class {index + 1} has officers but no skills.")
        total_officers += count
        normalized_classes.append({
            "name": str(officer_class.get("name", f"Class {index + 1}")).strip()[:40] or f"Class {index + 1}",
            "count": count,
            "skills": allowed,
        })
    if not 1 <= total_officers <= 100:
        raise ProblemError("The roster must contain between 1 and 100 officers.")
    problem["officer_classes"] = normalized_classes

    probabilities = problem.get("probabilities", DEFAULT_PROBABILITIES)
    if not isinstance(probabilities, list) or len(probabilities) != 5:
        raise ProblemError("The demand distribution needs exactly five probabilities.")
    probabilities = [_number(value, "Scenario probability", 0.0, 1.0) for value in probabilities]
    total_probability = sum(probabilities)
    if abs(total_probability - 1.0) > 1e-6:
        raise ProblemError("The five scenario probabilities must sum to 1.")
    problem["probabilities"] = probabilities

    solver = problem.get("solver") or {}
    problem["solver"] = {
        "epsilon_target": _number(solver.get("epsilon_target", 0.01), "QAE epsilon", 0.001, 0.25),
        "alpha": _number(solver.get("alpha", 0.05), "QAE alpha", 0.001, 0.5),
        "alpha_open": _number(solver.get("alpha_open", 0.05), "Open-cost search weight", 0.0, 10.0),
        "one_officer_penalty": _number(solver.get("one_officer_penalty", 20.0), "One-officer penalty", 0.0, 100000.0),
        "seed": int(_number(solver.get("seed", 7), "Seed", 0, 2147483647)),
    }
    return problem


def build_roster(problem: dict[str, Any]) -> list[dict[str, Any]]:
    roster = []
    officer_id = 1
    for officer_class in problem["officer_classes"]:
        for _ in range(officer_class["count"]):
            roster.append({
                "id": f"O{officer_id}",
                "class": officer_class["name"],
                "skills": tuple(officer_class["skills"]),
            })
            officer_id += 1
    return roster


def demand_distribution(base: int, cv: float, probabilities: list[float]) -> dict[int, float]:
    spread = max(1, round(base * cv))
    offsets = (-2 * spread, -spread, 0, spread, 2 * spread)
    distribution: dict[int, float] = {}
    for offset, probability in zip(offsets, probabilities):
        value = max(0, base + offset)
        distribution[value] = distribution.get(value, 0.0) + probability
    return dict(sorted(distribution.items()))


def expected_shortfall(distribution: dict[int, float], capacity: int) -> float:
    return sum(probability * max(0, value - capacity) for value, probability in distribution.items())


def qae_statevector_estimate(
    distribution: dict[int, float], capacity: int, epsilon_target: float, alpha: float
) -> dict[str, Any]:
    """Evaluate the notebook's exact payoff-ancilla amplitude without Qiskit.

    The state-preparation amplitudes are sqrt(p_x), and the controlled rotations
    make the ancilla-one probability E[g]/g_max.  We report that noiseless
    statevector value directly and an epsilon-target envelope.  This preserves
    the circuit mathematics while keeping the local app dependency-light.
    """

    values = np.array(list(distribution.keys()), dtype=float)
    probabilities = np.array(list(distribution.values()), dtype=float)
    payoff = np.maximum(values - capacity, 0.0)
    g_max = float(payoff.max()) if payoff.max() > 0 else 1.0
    normalized_payoff = payoff / g_max
    ancilla_probability = float(np.dot(probabilities, normalized_payoff))
    estimation = ancilla_probability * g_max
    radius = epsilon_target * g_max
    oracle_queries = max(1, ceil(pi / (2 * epsilon_target)))
    return {
        "estimate": estimation,
        "confidence_interval": [max(0.0, estimation - radius), min(g_max, estimation + radius)],
        "ancilla_probability": ancilla_probability,
        "g_max": g_max,
        "oracle_query_budget": oracle_queries,
        "alpha": alpha,
        "method": "analytical statevector payoff encoding",
    }


def _reachable_counts(roster: list[dict[str, Any]], caps: tuple[int, int, int, int]) -> set[tuple[int, int, int, int]]:
    states = {(0, 0, 0, 0)}
    for officer in roster:
        next_states = set(states)
        for state in states:
            for key in officer["skills"]:
                index = SKILL_KEYS.index(key)
                if state[index] >= caps[index]:
                    continue
                candidate = list(state)
                candidate[index] += 1
                next_states.add(tuple(candidate))
        states = next_states
        if len(states) > 450_000:
            raise ProblemError("This custom roster creates too many feasible staffing combinations; reduce officers or demand.")
    return states


@dataclass
class _Edge:
    to: int
    rev: int
    capacity: int


def _assignment_for_counts(roster: list[dict[str, Any]], targets: tuple[int, int, int, int]) -> dict[str, str]:
    officer_count = len(roster)
    source = 0
    officer_offset = 1
    skill_offset = officer_offset + officer_count
    sink = skill_offset + len(SKILL_KEYS)
    graph: list[list[_Edge]] = [[] for _ in range(sink + 1)]

    def add_edge(start: int, end: int, capacity: int) -> None:
        forward = _Edge(end, len(graph[end]), capacity)
        backward = _Edge(start, len(graph[start]), 0)
        graph[start].append(forward)
        graph[end].append(backward)

    officer_skill_edges: list[tuple[int, str, _Edge]] = []
    for officer_index, officer in enumerate(roster):
        node = officer_offset + officer_index
        add_edge(source, node, 1)
        for key in officer["skills"]:
            skill_node = skill_offset + SKILL_KEYS.index(key)
            add_edge(node, skill_node, 1)
            officer_skill_edges.append((officer_index, key, graph[node][-1]))
    for index, target in enumerate(targets):
        add_edge(skill_offset + index, sink, target)

    flow = 0
    while True:
        level = [-1] * len(graph)
        level[source] = 0
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for edge in graph[node]:
                if edge.capacity and level[edge.to] < 0:
                    level[edge.to] = level[node] + 1
                    queue.append(edge.to)
        if level[sink] < 0:
            break
        cursor = [0] * len(graph)

        def send(node: int, pushed: int) -> int:
            if node == sink:
                return pushed
            while cursor[node] < len(graph[node]):
                edge = graph[node][cursor[node]]
                if edge.capacity and level[edge.to] == level[node] + 1:
                    amount = send(edge.to, min(pushed, edge.capacity))
                    if amount:
                        edge.capacity -= amount
                        graph[edge.to][edge.rev].capacity += amount
                        return amount
                cursor[node] += 1
            return 0

        while True:
            pushed = send(source, 1_000_000)
            if not pushed:
                break
            flow += pushed
    if flow != sum(targets):
        raise ProblemError("Could not decode a feasible officer assignment for the selected counter counts.")
    assignment = {}
    for officer_index, key, edge in officer_skill_edges:
        if edge.capacity == 0:
            assignment[roster[officer_index]["id"]] = key
    return assignment


def solve_problem(raw_problem: dict[str, Any]) -> dict[str, Any]:
    problem = validate_problem(raw_problem)
    roster = build_roster(problem)
    skills_by_key = {item["key"]: item for item in problem["skills"]}
    max_counters = {key: sum(key in officer["skills"] for officer in roster) for key in SKILL_KEYS}
    distributions: dict[tuple[str, str], dict[int, float]] = {}
    qae_results: dict[tuple[str, str], dict[str, Any]] = {}
    loss_curves: dict[tuple[str, str], dict[str, Any]] = {}

    for period in problem["periods"]:
        for key in SKILL_KEYS:
            base = problem["demand"][period][key]
            distribution = demand_distribution(base, skills_by_key[key]["cv"], problem["probabilities"])
            distributions[(period, key)] = distribution
            qae_results[(period, key)] = qae_statevector_estimate(
                distribution,
                base,
                problem["solver"]["epsilon_target"],
                problem["solver"]["alpha"],
            )
            n_max = min(max_counters[key], max(distribution))
            n_grid = np.arange(0, n_max + 1, dtype=float)
            loss_values = np.array([expected_shortfall(distribution, int(n)) for n in n_grid])
            if len(n_grid) >= 3:
                coefficients = np.polyfit(n_grid, loss_values, deg=2)
            elif len(n_grid) == 2:
                slope = loss_values[1] - loss_values[0]
                coefficients = np.array([0.0, slope, loss_values[0]])
            else:
                coefficients = np.array([0.0, 0.0, loss_values[0]])
            loss_curves[(period, key)] = {
                "n_grid": n_grid,
                "loss_values": loss_values,
                "coefficients": coefficients,
            }

    caps = tuple(
        min(max_counters[key], max(max(distributions[(period, key)]) for period in problem["periods"]))
        for key in SKILL_KEYS
    )
    reachable = _reachable_counts(roster, caps)

    optimized_counts: dict[tuple[str, str], int] = {}
    nominal_counts: dict[tuple[str, str], int] = {}
    assignments: dict[str, dict[str, str]] = {}
    surrogate_scores: dict[str, float] = {}
    warnings: list[str] = []

    for period in problem["periods"]:
        def surrogate_score(counts: tuple[int, int, int, int]) -> float:
            score = 0.0
            for index, key in enumerate(SKILL_KEYS):
                n = counts[index]
                skill = skills_by_key[key]
                a2, a1, a0 = loss_curves[(period, key)]["coefficients"]
                score += problem["solver"]["alpha_open"] * skill["open_cost"] * n
                score += skill["shortage_penalty"] * (a2 * n * n + a1 * n + a0)
            return float(score)

        best_counts = min(reachable, key=lambda counts: (surrogate_score(counts), -sum(counts), counts))
        surrogate_scores[period] = surrogate_score(best_counts)
        assignment = _assignment_for_counts(roster, best_counts)
        assignments[period] = assignment
        for index, key in enumerate(SKILL_KEYS):
            optimized_counts[(period, key)] = best_counts[index]
            nominal_counts[(period, key)] = problem["demand"][period][key]

        nominal_tuple = tuple(problem["demand"][period][key] for key in SKILL_KEYS)
        if nominal_tuple not in reachable:
            warnings.append(f"The nominal demand target in {period} is not feasible for the submitted roster; it remains a cost benchmark only.")

    def score_plan(counts: dict[tuple[str, str], int]) -> dict[str, float]:
        open_cost = 0.0
        shortfall_cost = 0.0
        for period, key in product(problem["periods"], SKILL_KEYS):
            n = counts[(period, key)]
            skill = skills_by_key[key]
            open_cost += skill["open_cost"] * n
            shortfall_cost += skill["shortage_penalty"] * expected_shortfall(distributions[(period, key)], n)
        return {
            "open_cost": open_cost,
            "shortfall_cost": shortfall_cost,
            "total": open_cost + shortfall_cost,
        }

    nominal_score = score_plan(nominal_counts)
    optimized_score = score_plan(optimized_counts)
    reduction = nominal_score["total"] - optimized_score["total"]
    reduction_percent = (100 * reduction / nominal_score["total"]) if nominal_score["total"] else 0.0

    period_results = []
    for period in problem["periods"]:
        cells = []
        for key in SKILL_KEYS:
            distribution = distributions[(period, key)]
            qae = qae_results[(period, key)]
            cells.append({
                "skill": key,
                "label": skills_by_key[key]["label"],
                "demand": problem["demand"][period][key],
                "nominal": nominal_counts[(period, key)],
                "optimized": optimized_counts[(period, key)],
                "expected_shortfall_nominal": expected_shortfall(distribution, nominal_counts[(period, key)]),
                "expected_shortfall_optimized": expected_shortfall(distribution, optimized_counts[(period, key)]),
                "distribution": [{"value": value, "probability": probability} for value, probability in distribution.items()],
                "qae": qae,
                "quadratic_coefficients": [float(value) for value in loss_curves[(period, key)]["coefficients"]],
            })
        period_results.append({
            "period": period,
            "cells": cells,
            "assigned_officers": len(assignments[period]),
            "idle_officers": len(roster) - len(assignments[period]),
            "surrogate_score": surrogate_scores[period],
        })

    skill_totals = []
    for key in SKILL_KEYS:
        skill_totals.append({
            "key": key,
            "label": skills_by_key[key]["label"],
            "qualified_officers": max_counters[key],
            "nominal_counters": sum(nominal_counts[(period, key)] for period in problem["periods"]),
            "optimized_counters": sum(optimized_counts[(period, key)] for period in problem["periods"]),
        })

    # VQE-ready scale summary.  The local build does not pretend to execute a
    # variational quantum circuit: these counts explain how the same QUBO would
    # map to an Ising Hamiltonian and why a VQE run needs an ansatz, repeated
    # measurements, and a classical parameter-update loop.
    eligible_edges = sum(len(officer["skills"]) for officer in roster)
    logical_qubits = eligible_edges * len(problem["periods"])
    one_officer_couplers = len(problem["periods"]) * sum(
        len(officer["skills"]) * (len(officer["skills"]) - 1) // 2 for officer in roster
    )
    shortfall_couplers = len(problem["periods"]) * sum(
        max_counters[key] * (max_counters[key] - 1) // 2 for key in SKILL_KEYS
    )
    hamiltonian_terms = logical_qubits + one_officer_couplers + shortfall_couplers

    return {
        "summary": {
            "total_officers": len(roster),
            "officer_classes": len(problem["officer_classes"]),
            "periods": len(problem["periods"]),
            "nominal": nominal_score,
            "optimized": optimized_score,
            "reduction": reduction,
            "reduction_percent": reduction_percent,
            "optimized_assignments": sum(len(value) for value in assignments.values()),
        },
        "skill_totals": skill_totals,
        "period_results": period_results,
        "warnings": warnings,
        "method": {
            "optimizer": "Exact feasible search over the notebook's quadratic QUBO surrogate",
            "qae": "Analytical statevector evaluation of the notebook's exact payoff-ancilla encoding",
            "evaluation": "Exact discrete expected-shortfall curve",
            "one_officer_penalty": problem["solver"]["one_officer_penalty"],
            "note": "The one-officer penalty is shown for notebook parity; feasibility is enforced directly by the exact roster search.",
        },
        "vqe_view": {
            "executed": False,
            "status": "Exact reference - VQE not executed",
            "logical_qubits": logical_qubits,
            "hamiltonian_terms": hamiltonian_terms,
            "linear_terms": logical_qubits,
            "pairwise_terms": one_officer_couplers + shortfall_couplers,
            "reference_exact_loss": optimized_score["total"],
            "reference_surrogate_energy": sum(surrogate_scores.values()),
            "loop": [
                "Prepare a parameterized ansatz state",
                "Measure the Hamiltonian expectation value",
                "Update circuit parameters classically",
                "Repeat, then sample the lowest-energy bitstring",
            ],
            "explanation": (
                "VQE could target the Ising Hamiltonian made from this QUBO. "
                "Its characteristic output is an energy-convergence trace and sampled bitstrings; "
                "the local app reports a deterministic exact reference instead."
            ),
        },
        "assignments": assignments,
    }
