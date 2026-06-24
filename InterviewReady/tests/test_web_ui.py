import tempfile
import unittest
from pathlib import Path

import app.web as web_module
from app.web import InterviewReadyHandler
from core.report_writer import ReportWriter


class TestWebUIHelpers(unittest.TestCase):
    def test_collect_input_combines_four_files_and_text_only(self):
        handler = InterviewReadyHandler.__new__(InterviewReadyHandler)
        form = {
            "jd_file_1_text": "first JD",
            "jd_file_1_name": "one.txt",
            "jd_file_2_text": "second JD",
            "jd_file_2_name": "two.txt",
            "jd_file_3_text": "third JD",
            "jd_file_3_name": "three.txt",
            "jd_file_4_text": "fourth JD",
            "jd_file_4_name": "four.md",
            "jd_file_5_text": "should be ignored",
            "jd_text": "pasted JD",
        }

        combined = handler._collect_input(form, "jd_file", "jd_text")

        self.assertIn("first JD", combined)
        self.assertIn("second JD", combined)
        self.assertIn("third JD", combined)
        self.assertIn("fourth JD", combined)
        self.assertIn("pasted JD", combined)
        self.assertNotIn("should be ignored", combined)

    def test_report_writer_includes_jd_insight_benchmark(self):
        analysis = {
            "summary": "JD Insight summary",
            "candidate_fit_score": None,
            "jd_breakdown": {
                "required_skills": [],
                "hidden_expectations": [],
                "interview_focus_areas": [],
                "risk_points": [],
            },
            "jd_insight": {
                "target_company": "Sample Company",
                "benchmark_input_provided": True,
                "benchmark_signals": [{"signal": "Japanese enterprise style", "evidence": "documentation"}],
                "consultant_notes": ["Adjust candidate coaching to company style."],
            },
            "strengths": [],
            "weaknesses": [],
            "interview_questions": {},
            "suggested_answers": {},
        }

        rendered = ReportWriter().render(analysis, candidate_name=None, source="unit-test")

        self.assertIn("JD Insight benchmark analysis", rendered)
        self.assertIn("Sample Company", rendered)
        self.assertIn("Japanese enterprise style", rendered)

    def test_record_analysis_run_writes_history_and_report_index(self):
        handler = InterviewReadyHandler.__new__(InterviewReadyHandler)
        original_runs = web_module.ANALYSIS_RUNS_FILE
        original_index = web_module.REPORT_INDEX_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                web_module.ANALYSIS_RUNS_FILE = tmp_path / "analysis_runs.json"
                web_module.REPORT_INDEX_FILE = tmp_path / "report_index.json"
                report_path = tmp_path / "report.md"
                report_path.write_text("# Report", encoding="utf-8")

                record = handler._record_analysis_run(
                    user={
                        "user_id": "USR-TEST",
                        "email": "hr@example.com",
                        "display_name": "HR User",
                        "entity": {"entity_id": "ENT-0001", "entity_code": "TAKK", "entity_name_en": "Tech Alliance KK"},
                    },
                    form={"jd_text": "JD", "resume_text": "Resume"},
                    analysis={"summary": "OK", "candidate_fit_score": 80},
                    feature="resume-match",
                    candidate_name="Candidate A",
                    source="Unit Test",
                    client_company="Client A",
                    target_role="Engineer",
                    department="Recruitment",
                    team="JP Team",
                    consent_status="confirmed_internal_use",
                    report_path=report_path,
                )

                self.assertEqual(record["analysis_id"], "IR-000001")
                self.assertEqual(record["entity_code"], "TAKK")
                self.assertEqual(record["candidate_consent_status"], "confirmed_internal_use")
                self.assertTrue(web_module.ANALYSIS_RUNS_FILE.exists())
                self.assertTrue(web_module.REPORT_INDEX_FILE.exists())
        finally:
            web_module.ANALYSIS_RUNS_FILE = original_runs
            web_module.REPORT_INDEX_FILE = original_index

    def test_report_detail_shows_download_for_export_permission(self):
        handler = InterviewReadyHandler.__new__(InterviewReadyHandler)
        original_runs = web_module.ANALYSIS_RUNS_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                web_module.ANALYSIS_RUNS_FILE = tmp_path / "analysis_runs.json"
                web_module.ANALYSIS_RUNS_FILE.write_text(
                    """
                    [
                      {
                        "analysis_id": "IR-000001",
                        "feature_label": "Resume Match",
                        "candidate_name": "Candidate A",
                        "client_company": "Client A",
                        "entity_code": "TAKK",
                        "created_by": "hr@example.com",
                        "status": "completed",
                        "report_path": "/tmp/report.md"
                      }
                    ]
                    """,
                    encoding="utf-8",
                )

                html = handler._report_detail_html(
                    "IR-000001",
                    user={"permissions": ["interview_ready.report.export"]},
                )

                self.assertIn("Download Markdown", html)
                self.assertIn("/report/export?id=IR-000001", html)
        finally:
            web_module.ANALYSIS_RUNS_FILE = original_runs

    def test_report_detail_hides_download_without_export_permission(self):
        handler = InterviewReadyHandler.__new__(InterviewReadyHandler)
        original_runs = web_module.ANALYSIS_RUNS_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                web_module.ANALYSIS_RUNS_FILE = tmp_path / "analysis_runs.json"
                web_module.ANALYSIS_RUNS_FILE.write_text(
                    """
                    [
                      {
                        "analysis_id": "IR-000001",
                        "feature_label": "Resume Match",
                        "candidate_name": "Candidate A",
                        "client_company": "Client A",
                        "entity_code": "TAKK",
                        "created_by": "hr@example.com",
                        "status": "completed",
                        "report_path": "/tmp/report.md"
                      }
                    ]
                    """,
                    encoding="utf-8",
                )

                html = handler._report_detail_html(
                    "IR-000001",
                    user={"permissions": ["interview_ready.report.view"]},
                )

                self.assertNotIn("Download Markdown", html)
                self.assertNotIn("/report/export?id=IR-000001", html)
        finally:
            web_module.ANALYSIS_RUNS_FILE = original_runs

    def test_safe_report_content_blocks_paths_outside_base_dir(self):
        handler = InterviewReadyHandler.__new__(InterviewReadyHandler)
        with tempfile.TemporaryDirectory() as tmp_dir:
            outside_report = Path(tmp_dir) / "outside.md"
            outside_report.write_text("# Outside report", encoding="utf-8")

            report_path, content = handler._safe_report_content({"report_path": str(outside_report)})

            self.assertIsNone(report_path)
            self.assertEqual(content, "Report file is unavailable.")


if __name__ == "__main__":
    unittest.main()
