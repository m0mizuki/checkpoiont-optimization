import copy
import unittest

from model import (
    ProblemError,
    build_roster,
    default_problem,
    demand_distribution,
    solve_problem,
    validate_problem,
)


class CheckpointModelTests(unittest.TestCase):
    def test_current_default_roster_totals(self):
        roster = build_roster(default_problem())
        self.assertEqual(len(roster), 30)
        totals = {key: sum(key in officer["skills"] for officer in roster) for key in "ABCD"}
        self.assertEqual(totals, {"A": 28, "B": 24, "C": 28, "D": 30})

    def test_worked_distribution(self):
        distribution = demand_distribution(8, 0.25, [0.1, 0.2, 0.4, 0.2, 0.1])
        self.assertEqual(distribution, {4: 0.1, 6: 0.2, 8: 0.4, 10: 0.2, 12: 0.1})

    def test_current_default_result(self):
        result = solve_problem(default_problem())
        self.assertAlmostEqual(result["summary"]["nominal"]["total"], 219.0)
        self.assertAlmostEqual(result["summary"]["optimized"]["total"], 169.5)
        self.assertAlmostEqual(result["summary"]["reduction"], 49.5)
        self.assertEqual(result["summary"]["optimized_assignments"], 120)
        self.assertFalse(result["vqe_view"]["executed"])
        self.assertEqual(result["vqe_view"]["logical_qubits"], 440)
        self.assertEqual(result["vqe_view"]["hamiltonian_terms"], 6920)

    def test_decoded_assignments_respect_skills_and_one_slot_rule(self):
        problem = default_problem()
        result = solve_problem(problem)
        roster = {officer["id"]: set(officer["skills"]) for officer in build_roster(problem)}
        for assignment in result["assignments"].values():
            self.assertEqual(len(assignment), len(set(assignment)))
            for officer, skill in assignment.items():
                self.assertIn(skill, roster[officer])

    def test_custom_cost_changes_the_solution(self):
        baseline = solve_problem(default_problem())
        custom = copy.deepcopy(default_problem())
        custom["skills"][3]["open_cost"] = 50.0
        changed = solve_problem(custom)
        baseline_truck = sum(row["cells"][3]["optimized"] for row in baseline["period_results"])
        changed_truck = sum(row["cells"][3]["optimized"] for row in changed["period_results"])
        self.assertLess(changed_truck, baseline_truck)

    def test_probabilities_must_sum_to_one(self):
        problem = default_problem()
        problem["probabilities"] = [0.2] * 5
        problem["probabilities"][0] = 0.3
        with self.assertRaises(ProblemError):
            validate_problem(problem)


if __name__ == "__main__":
    unittest.main()
