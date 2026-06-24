import tempfile
import unittest
from pathlib import Path

from core.document_loader import DocumentLoader
from core.japan_risk_engine import JapanInterviewRiskEngine
from core.mock_interview_engine import MockInterviewEngine
from core.resume_matcher import ResumeMatcher


JD = """
Senior Python backend engineer required for AWS microservices.
Must work with PostgreSQL, Docker, client stakeholders, and Japanese/English teams.
Experience with system design and production incidents is preferred.
"""

RESUME = """
Candidate: Test Engineer
Led Python backend projects on AWS using PostgreSQL and Docker.
Designed microservices, coordinated with client stakeholders, and documented incidents.
Japanese/English bilingual. Improved deployment time by 30% for 12 engineers.
"""


class TestEngines(unittest.TestCase):
    def test_document_loader_reads_text_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "resume.txt"
            md = Path(tmp) / "jd.md"
            txt.write_text("Python resume", encoding="utf-8")
            md.write_text("# JD\nAWS role", encoding="utf-8")

            loader = DocumentLoader()
            self.assertIn("Python", loader.load(txt))
            self.assertIn("AWS", loader.load(md))

    def test_resume_matcher_scores_candidate(self):
        analysis = ResumeMatcher().match(RESUME, JD, candidate_name="Test Engineer", source="unit-test")
        self.assertGreaterEqual(analysis["candidate_fit_score"], 70)
        self.assertEqual(analysis["resume_match"]["overall_score"], analysis["candidate_fit_score"])
        self.assertTrue(analysis["resume_match"]["matched_skills"])
        self.assertTrue(analysis["resume_match"]["matching_points"])
        self.assertLessEqual(len(analysis["resume_match"]["matching_points"]), 10)
        self.assertTrue(analysis["resume_match"]["gap_points"])
        self.assertLessEqual(len(analysis["resume_match"]["gap_points"]), 10)
        self.assertTrue(analysis["resume_match"]["improvement_suggestions"])

    def test_mock_interview_generates_questions(self):
        analysis = MockInterviewEngine().generate(JD, RESUME, candidate_name="Test Engineer", source="unit-test")
        self.assertTrue(analysis["mock_interview"]["technical_questions"])
        self.assertTrue(analysis["mock_interview"]["behavioral_questions"])

    def test_japan_risk_engine_detects_risks(self):
        answer = "We did various things and I just helped. No numbers, maybe it was okay."
        analysis = JapanInterviewRiskEngine().analyze(answer, JD, candidate_name="Test Engineer", source="unit-test")
        self.assertGreater(analysis["japan_risk"]["communication_risk_score"], 20)
        self.assertTrue(analysis["japan_risk"]["detected_risks"])


if __name__ == "__main__":
    unittest.main()
