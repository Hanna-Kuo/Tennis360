"""Prevent missing labels, refusals and wrong arms from inflating accuracy."""
import unittest
from tennispose.evaluation import summarize_photo_results


def row(preparation=True, verdict=None, truth=None, status="analyzed", green=True, arm="right"):
    return {"label": {"preparation": preparation, "arm": "right", "coach_verdict": verdict,
                      "measured_angle_degrees": truth, "angle_convention": "shoulder-elbow-wrist interior",
                      "angle_source": "independent test reference" if truth is not None else None},
            "report": {"status": status, "arm": arm, "in_demo_range": green, "angle_degrees": 100.0}}


class EvidenceMetricsTests(unittest.TestCase):
    def test_missing_gold_is_null_instead_of_perfect_accuracy(self):
        r = summarize_photo_results([row(), row(False, status="cannot_analyze")])
        self.assertEqual(r["accepted_coverage"], .5)
        self.assertEqual(r["unsuitable_false_acceptance_rate"], 0)
        self.assertIsNone(r["coach_proxy"]["agreement_among_accepted"])
        self.assertIsNone(r["measured_3d"]["mean_absolute_error_degrees"])

    def test_refusal_coverage_is_separate_from_selective_coach_agreement(self):
        r = summarize_photo_results([row(verdict="correct"), row(verdict="correct", status="cannot_analyze"),
                                    row(verdict="incorrect"), row(verdict="incorrect", green=False)])
        self.assertEqual(r["coach_proxy"]["refused"], 1)
        self.assertEqual(r["coach_proxy"]["precision"], .5)
        self.assertAlmostEqual(r["coach_proxy"]["agreement_among_accepted"], 2/3)

    def test_wrong_arm_cannot_support_true_3d_accuracy(self):
        r = summarize_photo_results([row(truth=95), row(truth=80, arm="left")])
        self.assertEqual(r["accepted_wrong_arm"], 1)
        self.assertEqual(r["measured_3d"]["labelled"], 2)
        self.assertEqual(r["measured_3d"]["accepted_same_arm"], 1)
        self.assertEqual(r["measured_3d"]["mean_absolute_error_degrees"], 5)

    def test_empty_and_unknown_phase_denominators_are_null(self):
        for rows in ([], [row(preparation=None)]):
            r = summarize_photo_results(rows)
            self.assertIsNone(r["preparation_coverage"])
            self.assertIsNone(r["unsuitable_false_acceptance_rate"])

    def test_measured_angles_require_finite_values_and_independent_convention(self):
        for value in (float("nan"), float("inf"), -1, 181, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                summarize_photo_results([row(truth=value)])
        sample = row(truth=90)
        sample["label"]["angle_convention"] = "ISB segment flexion"
        with self.assertRaises(ValueError):
            summarize_photo_results([sample])

    def test_player_tier_is_not_a_coach_label(self):
        sample = row(verdict="HP")
        with self.assertRaises(ValueError):
            summarize_photo_results([sample])

    def test_wrong_arm_cannot_be_a_correct_negative_coach_verdict(self):
        r = summarize_photo_results([row(verdict="incorrect", arm="left")])
        self.assertEqual(r["coach_proxy"]["tn"], 0)
        self.assertEqual(r["coach_proxy"]["wrong_or_unknown_arm_excluded"], 1)
        self.assertEqual(r["coach_proxy"]["refused"], 0)
        self.assertIsNone(r["coach_proxy"]["agreement_among_accepted"])

    def test_unknown_label_arm_cannot_support_coach_or_true_angle_agreement(self):
        sample=row(verdict="correct",truth=100)
        sample["label"]["arm"]=None
        r=summarize_photo_results([sample])
        self.assertEqual(r["accepted_unknown_label_arm"],1)
        self.assertEqual(r["measured_3d"]["accepted_same_arm"],0)
        self.assertIsNone(r["measured_3d"]["mean_absolute_error_degrees"])
        self.assertIsNone(r["coach_proxy"]["agreement_among_accepted"])


if __name__ == "__main__":
    unittest.main()
