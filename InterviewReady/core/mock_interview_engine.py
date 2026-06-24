"""Text-based mock interview generation engine."""

from __future__ import annotations

from typing import Any

from .jd_analyzer import JDAnalyzer
from .resume_matcher import ResumeMatcher


class MockInterviewEngine:
    """Creates structured technical and behavioral mock interviews."""

    def __init__(self, analyzer: JDAnalyzer | None = None) -> None:
        self.analyzer = analyzer or JDAnalyzer()
        self.matcher = ResumeMatcher(self.analyzer)

    def generate(
        self,
        jd_text: str,
        candidate_profile: str = "",
        candidate_name: str | None = None,
        source: str = "manual-input",
    ) -> dict[str, Any]:
        if candidate_profile.strip():
            base = self.matcher.match(candidate_profile, jd_text, candidate_name=candidate_name, source=source)
        else:
            base = self.analyzer.analyze(jd_text, source=source)

        breakdown = base["jd_breakdown"]
        required_skills = breakdown.get("required_skills", [])
        risk_points = breakdown.get("risk_points", [])
        focus_areas = breakdown.get("interview_focus_areas", [])

        technical = [
            {
                "question": f"Please explain your most relevant experience with {skill['name']} and one difficult technical decision you made.",
                "evaluation_points": ["production relevance", "personal ownership", "tradeoff reasoning", "measurable result"],
                "follow_up": f"What would you improve if you used {skill['name']} again in this role?",
            }
            for skill in required_skills[:6]
        ]
        if not technical:
            technical.append(
                {
                    "question": "Walk through a technically complex project from requirements to delivery.",
                    "evaluation_points": ["structure", "technical depth", "ownership", "business impact"],
                    "follow_up": "Which part was most risky and how did you reduce the risk?",
                }
            )

        behavioral = [
            {
                "question": "Tell me about a time you had to align with a difficult stakeholder or client.",
                "evaluation_points": ["communication", "conflict handling", "documentation", "outcome"],
                "follow_up": "How did you confirm that expectations were understood correctly?",
            },
            {
                "question": "Describe a failure or production issue and what you changed afterward.",
                "evaluation_points": ["accountability", "root cause thinking", "learning", "prevention"],
                "follow_up": "What signal would help you detect the same issue earlier next time?",
            },
        ]
        behavioral.extend(
            {
                "question": f"How would you proactively address this interview concern: {risk['risk']}?",
                "evaluation_points": ["self-awareness", "specific evidence", "risk mitigation"],
                "follow_up": risk.get("mitigation", "Give one concrete example."),
            }
            for risk in risk_points[:3]
        )

        base["summary"] = f"Mock interview generated for {candidate_name or 'candidate'} with {len(technical)} technical and {len(behavioral)} behavioral questions."
        base["interview_questions"] = {
            "technical": [item["question"] for item in technical],
            "behavioral": [item["question"] for item in behavioral],
            "scoring_rubric": self._rubric(),
            "focus_area_prompts": [f"Prepare evidence for: {area['area']}" for area in focus_areas[:6]],
        }
        base["mock_interview"] = {
            "technical_questions": technical,
            "behavioral_questions": behavioral,
            "scoring_rubric": self._rubric(),
            "recommended_sequence": ["self_introduction", "technical_depth", "project_ownership", "risk_handling", "closing_questions"],
        }
        base["suggested_answers"] = self._answer_templates(required_skills, risk_points)
        return base

    def _rubric(self) -> list[str]:
        return [
            "5: Clear conclusion-first answer with concrete facts, personal ownership, tradeoffs, and measurable impact.",
            "4: Relevant and structured answer with minor missing detail.",
            "3: Understandable answer but limited metrics, ownership clarity, or tradeoff explanation.",
            "2: Vague answer with weak relevance to the JD or unclear personal contribution.",
            "1: Cannot answer directly or creates new evaluation risk.",
        ]

    def _answer_templates(self, required_skills: list[dict[str, Any]], risk_points: list[dict[str, Any]]) -> dict[str, list[str]]:
        skill = required_skills[0]["name"] if required_skills else "the required technology"
        risk = risk_points[0]["risk"] if risk_points else "the interview concern"
        return {
            "en": [
                f"For {skill}: start with the project goal, describe your role, explain the technical choice, then give the result.",
                f"For {risk}: acknowledge the concern briefly, then provide one concrete example that lowers the risk.",
            ],
            "jp": [
                f"{skill}については、目的、自分の役割、技術選定の理由、結果の順番で説明します。",
                f"{risk}については、懸念点を簡潔に認識した上で、それを下げる具体例を一つ提示します。",
            ],
        }
