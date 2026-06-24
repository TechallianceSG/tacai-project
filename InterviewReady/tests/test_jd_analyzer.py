import unittest

from core.jd_analyzer import JDAnalyzer


class TestJDAnalyzer(unittest.TestCase):
    def test_jd_analyzer_extracts_core_outputs(self):
        jd = """
        Senior Python backend engineer required for AWS microservices.
        Must work with PostgreSQL, Docker, client stakeholders, and Japanese/English teams.
        Experience with system design and production incidents is preferred.
        """

        analysis = JDAnalyzer().analyze(jd, source="unit-test")
        breakdown = analysis["jd_breakdown"]

        skill_names = {skill["name"] for skill in breakdown["required_skills"]}
        self.assertIn("Python", skill_names)
        self.assertIn("AWS", skill_names)
        self.assertIn("PostgreSQL", skill_names)
        self.assertTrue(breakdown["hidden_expectations"])
        self.assertTrue(breakdown["interview_focus_areas"])
        self.assertTrue(breakdown["risk_points"])
        self.assertTrue(analysis["interview_questions"]["technical"])
        self.assertTrue(analysis["suggested_answers"]["jp"])


if __name__ == "__main__":
    unittest.main()
