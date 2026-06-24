"""Markdown report writer for interview preparation outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


class ReportWriter:
    """Creates human-readable reports under outputs/interview_prep."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or Path(__file__).resolve().parents[1] / "outputs" / "interview_prep"

    def write_interview_prep_report(
        self,
        analysis: dict[str, Any],
        candidate_name: str | None = None,
        source: str = "manual-input",
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = self._slug(candidate_name or source or "analysis")
        path = self.output_dir / f"{timestamp}_{slug}.md"
        path.write_text(self.render(analysis, candidate_name, source), encoding="utf-8")
        return path

    def render(self, analysis: dict[str, Any], candidate_name: str | None, source: str) -> str:
        breakdown = analysis.get("jd_breakdown", {})
        questions = analysis.get("interview_questions", {})
        answers = analysis.get("suggested_answers", {})

        lines = [
            "# Interview Preparation Report",
            "",
            f"- Source: {source}",
            f"- Candidate: {candidate_name or 'Not provided'}",
            f"- Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Summary",
            "",
            analysis.get("summary", "No summary generated."),
            "",
            "## Candidate fit score / 候補者適合スコア",
            "",
            self._fit_score(analysis.get("candidate_fit_score")),
        ]
        self._append_resume_match(lines, analysis.get("resume_match"))

        lines.extend([
            "",
            "## JD breakdown",
            "",
            "### Required skills",
            "",
        ])
        lines.extend(self._skill_lines(breakdown.get("required_skills", [])))
        lines.extend(["", "### Hidden expectations", ""])
        lines.extend(self._object_lines(breakdown.get("hidden_expectations", []), "expectation", "preparation_note"))
        lines.extend(["", "### Interview focus areas", ""])
        lines.extend(self._object_lines(breakdown.get("interview_focus_areas", []), "area", "reason"))
        lines.extend(["", "### Risk points", ""])
        lines.extend(self._risk_lines(breakdown.get("risk_points", [])))
        self._append_jd_insight(lines, analysis.get("jd_insight"))
        lines.extend(["", "## Strengths", ""])
        lines.extend(self._plain_lines(analysis.get("strengths", []), fallback="Not evaluated yet."))
        lines.extend(["", "## Weaknesses", ""])
        lines.extend(self._plain_lines(analysis.get("weaknesses", []), fallback="Not evaluated yet."))

        self._append_japan_risk(lines, analysis.get("japan_risk"))
        self._append_mock_interview(lines, analysis.get("mock_interview"))

        lines.extend(["", "## Interview questions", "", "### Technical", ""])
        lines.extend(self._plain_lines(questions.get("technical", [])))
        lines.extend(["", "### Behavioral", ""])
        lines.extend(self._plain_lines(questions.get("behavioral", [])))
        lines.extend(["", "### Scoring rubric", ""])
        lines.extend(self._plain_lines(questions.get("scoring_rubric", [])))
        lines.extend(["", "## Suggested answers (EN)", ""])
        lines.extend(self._plain_lines(answers.get("en", [])))
        lines.extend(["", "## Suggested answers (JP)", ""])
        lines.extend(self._plain_lines(answers.get("jp", [])))
        lines.append("")
        return "\n".join(lines)

    def _append_resume_match(self, lines: list[str], resume_match: dict[str, Any] | None) -> None:
        if not resume_match:
            return
        score = resume_match.get("overall_score")
        label = resume_match.get("score_label")
        if score is not None:
            lines.extend(["", f"**Overall resume/JD match: {score}/100**" + (f" — {label}" if label else "")])

        lines.extend(["", "## Matching points / マッチポイント（最大10項目）", ""])
        lines.extend(self._numbered_point_lines(resume_match.get("matching_points", []), positive=True))

        lines.extend(["", "## Gap points / ギャップポイント（最大10項目）", ""])
        lines.extend(self._numbered_point_lines(resume_match.get("gap_points", []), positive=False))

        lines.extend(["", "## Score components / スコア構成", ""])
        score_components = resume_match.get("score_components", {})
        component_caps = {
            "skill_match": 55,
            "category_coverage": 15,
            "seniority_evidence": 10,
            "communication_alignment": 10,
            "japan_readiness": 10,
        }
        for key, value in score_components.items():
            cap = component_caps.get(key)
            suffix = f"/{cap}" if cap else ""
            lines.append(f"- {key.replace('_', ' ').title()}: {value}{suffix}")

        lines.extend(["", "### Matched skills", ""])
        lines.extend(self._skill_lines(resume_match.get("matched_skills", [])))
        lines.extend(["", "### Missing skills", ""])
        lines.extend(self._skill_lines(resume_match.get("missing_skills", [])))
        lines.extend(["", "### Improvement suggestions", ""])
        lines.extend(self._plain_lines(resume_match.get("improvement_suggestions", [])))

    def _numbered_point_lines(self, points: list[dict[str, Any]], positive: bool) -> list[str]:
        if not points:
            return ["No explicit matching points detected." if positive else "No major gaps detected."]
        lines: list[str] = []
        for index, point in enumerate(points[:10], start=1):
            title = point.get("point", "N/A")
            evidence = point.get("evidence")
            detail_key = "impact" if positive else "action"
            detail = point.get(detail_key)
            line = f"{index}. {title}"
            if evidence:
                line += f" Evidence: {evidence}"
            if detail:
                line += f" {'Impact' if positive else 'Action'}: {detail}"
            lines.append(line)
        return lines

    def _append_jd_insight(self, lines: list[str], jd_insight: dict[str, Any] | None) -> None:
        if not jd_insight:
            return
        lines.extend(["", "## JD Insight benchmark analysis", ""])
        lines.append(f"- Target company: {jd_insight.get('target_company', 'Not provided')}")
        lines.append(f"- Benchmark input provided: {jd_insight.get('benchmark_input_provided', False)}")
        lines.extend(["", "### Benchmark company signals", ""])
        benchmark_signals = jd_insight.get("benchmark_signals", [])
        if benchmark_signals:
            for index, signal in enumerate(benchmark_signals[:10], start=1):
                lines.append(f"{index}. {signal.get('signal', 'N/A')} Evidence: {signal.get('evidence', '')}")
        else:
            lines.append("No benchmark company signals detected.")
        lines.extend(["", "### Consultant notes", ""])
        lines.extend(self._plain_lines(jd_insight.get("consultant_notes", [])))

    def _append_japan_risk(self, lines: list[str], japan_risk: dict[str, Any] | None) -> None:
        if not japan_risk:
            return
        lines.extend(["", "## Japan interview risk analysis", ""])
        lines.append(f"- Communication risk score: {japan_risk.get('communication_risk_score')}/100")
        lines.append(f"- Cultural mismatch analysis: {japan_risk.get('cultural_mismatch_analysis')}")
        lines.extend(["", "### Improvement suggestions", ""])
        lines.extend(self._plain_lines(japan_risk.get("improvement_suggestions", [])))

    def _append_mock_interview(self, lines: list[str], mock_interview: dict[str, Any] | None) -> None:
        if not mock_interview:
            return
        lines.extend(["", "## Mock interview structure", ""])
        lines.extend(self._plain_lines(mock_interview.get("recommended_sequence", [])))
        lines.extend(["", "### Detailed technical prompts", ""])
        for item in mock_interview.get("technical_questions", []):
            lines.append(f"- {item.get('question')} Follow-up: {item.get('follow_up')}")
        lines.extend(["", "### Detailed behavioral prompts", ""])
        for item in mock_interview.get("behavioral_questions", []):
            lines.append(f"- {item.get('question')} Follow-up: {item.get('follow_up')}")

    def _skill_lines(self, skills: list[dict[str, Any]]) -> list[str]:
        if not skills:
            return ["- None detected."]
        return [
            f"- {skill.get('name')} ({skill.get('category', 'unknown')}, {skill.get('importance', 'matched')}): {skill.get('evidence', 'Detected in profile/resume.')}"
            for skill in skills
        ]

    def _object_lines(self, items: list[dict[str, Any]], title_key: str, note_key: str) -> list[str]:
        if not items:
            return ["- None detected."]
        return [f"- {item.get(title_key)}: {item.get(note_key)}" for item in items]

    def _risk_lines(self, risks: list[dict[str, Any]]) -> list[str]:
        if not risks:
            return ["- No major JD-level risks detected."]
        return [
            f"- {risk.get('risk')}: {risk.get('why_it_matters')} Mitigation: {risk.get('mitigation')}"
            for risk in risks
        ]

    def _plain_lines(self, items: list[str], fallback: str = "- None generated.") -> list[str]:
        if not items:
            return [fallback if fallback.startswith("-") else f"- {fallback}"]
        return [f"- {item}" for item in items]

    def _fit_score(self, score: int | None) -> str:
        if score is None:
            return "Not evaluated yet."
        return f"{score}/100"

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return slug[:60] or "analysis"
