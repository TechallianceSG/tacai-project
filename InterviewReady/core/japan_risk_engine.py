"""Japan-specific interview risk analysis engine."""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any


class JapanInterviewRiskEngine:
    """Detects Japan-market communication and culture-fit interview risks."""

    DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "knowledge_base" / "japan_risk_taxonomy.json"

    def __init__(self, taxonomy_path: Path | None = None) -> None:
        self.taxonomy_path = taxonomy_path or self.DEFAULT_TAXONOMY_PATH
        self.taxonomy = self._load_taxonomy(self.taxonomy_path)

    def analyze(
        self,
        candidate_text: str,
        jd_text: str = "",
        candidate_name: str | None = None,
        source: str = "manual-input",
    ) -> dict[str, Any]:
        combined = f"{candidate_text}\n{jd_text}".strip()
        if not combined:
            raise ValueError("Candidate answers/profile text is empty.")

        risks = self._detect_risks(candidate_text, jd_text)
        positive = self._detect_positive_signals(combined)
        risk_score = min(100, 20 + len(risks) * 12 - len(positive) * 4)
        risk_score = max(0, risk_score)
        cultural_analysis = self._cultural_analysis(risks, positive, combined)
        suggestions = self._suggestions(risks, positive)

        return {
            "source": source,
            "summary": f"Japan interview risk score for {candidate_name or 'candidate'}: {risk_score}/100. Main risks: {', '.join(r['risk'] for r in risks[:3]) or 'none detected'}.",
            "jd_breakdown": {
                "required_skills": [],
                "hidden_expectations": [],
                "interview_focus_areas": [
                    {"area": "Japan interview communication", "reason": "Assess structure, humility/confidence balance, ownership, and cultural fit."}
                ],
                "risk_points": [
                    {"risk": risk["risk"], "why_it_matters": risk["why_it_matters"], "mitigation": risk["suggestion"]}
                    for risk in risks
                ],
            },
            "candidate_fit_score": max(0, 100 - risk_score),
            "strengths": positive or ["No strong positive Japan-interview signal detected yet."],
            "weaknesses": [risk["risk"] for risk in risks] or ["No major Japan-specific communication weakness detected."],
            "interview_questions": {
                "technical": [],
                "behavioral": self._risk_questions(risks),
                "scoring_rubric": [
                    "Low risk: answers are concise, factual, ownership-aware, and culturally balanced.",
                    "Medium risk: answers need better structure, evidence, or stakeholder framing.",
                    "High risk: answers may create concern about communication, maturity, or fit for Japan-market interviews.",
                ],
            },
            "suggested_answers": {
                "en": ["Use: conclusion -> reason -> concrete example -> result -> learning/next action."],
                "jp": ["結論 → 理由 → 具体例 → 結果 → 学び・次の行動、の順番で簡潔に回答してください。"],
            },
            "japan_risk": {
                "communication_risk_score": risk_score,
                "cultural_mismatch_analysis": cultural_analysis,
                "detected_risks": risks,
                "positive_signals": positive,
                "improvement_suggestions": suggestions,
            },
        }

    def _load_taxonomy(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"communication_risks": [], "positive_signals": []}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _detect_risks(self, candidate_text: str, jd_text: str) -> list[dict[str, str]]:
        candidate_lower = candidate_text.lower()
        jd_lower = jd_text.lower()
        risks: list[dict[str, str]] = []
        for item in self.taxonomy.get("communication_risks", []):
            signals = [signal for signal in item.get("signals", []) if signal.lower() in candidate_lower]
            if signals:
                risks.append(
                    {
                        "risk": item["risk"],
                        "signals": ", ".join(signals[:5]),
                        "why_it_matters": self._why_it_matters(item["risk"]),
                        "suggestion": item["suggestion"],
                    }
                )

        if any(token in jd_lower for token in ["client", "stakeholder", "顧客", "クライアント"]) and not any(
            token in candidate_lower for token in ["stakeholder", "client", "customer", "顧客", "調整", "合意"]
        ):
            risks.append(
                {
                    "risk": "Insufficient client-facing evidence",
                    "signals": "JD expects stakeholder/client communication, but candidate answer lacks matching evidence.",
                    "why_it_matters": "Japan IT interviews often evaluate reliability in client and cross-functional settings.",
                    "suggestion": "Add one example of requirement clarification, reporting, escalation, or stakeholder alignment.",
                }
            )

        if not re.search(r"\d+%|\d+\s*(people|members|users|projects|years|年|名|件)", candidate_text, re.I):
            risks.append(
                {
                    "risk": "Low measurable impact evidence",
                    "signals": "No clear numeric scale or outcome found.",
                    "why_it_matters": "Interviewers may struggle to judge scope, seniority, and business contribution.",
                    "suggestion": "Add numbers: team size, users, latency/cost improvement, project duration, revenue, or defect reduction.",
                }
            )
        return self._dedupe(risks)

    def _detect_positive_signals(self, text: str) -> list[str]:
        lowered = text.lower()
        positives = []
        checks = {
            "Measurable outcome evidence": [r"\d+%", r"\d+\s*(users|members|projects|years|年|名|件)"],
            "Stakeholder/client alignment evidence": ["stakeholder", "client", "customer", "顧客", "調整", "合意"],
            "Documentation or reporting discipline": ["documentation", "report", "minutes", "ドキュメント", "報告"],
            "Incident or production ownership": ["incident", "production", "障害", "運用"],
            "Bilingual communication evidence": ["japanese", "english", "bilingual", "jlpt", "日本語", "英語"],
        }
        for label, patterns in checks.items():
            if any(re.search(pattern, lowered, re.I) for pattern in patterns):
                positives.append(label)
        return positives

    def _cultural_analysis(self, risks: list[dict[str, str]], positive: list[str], text: str) -> str:
        if not risks and positive:
            return "Candidate currently shows low Japan-specific interview risk with usable evidence of structured communication or workplace readiness."
        if any(risk["risk"] in {"Over-assertion", "Negative resignation reason"} for risk in risks):
            return "Candidate should soften potentially negative or absolute statements and reframe answers around constructive contribution."
        if any(risk["risk"] == "Excessive humility" for risk in risks):
            return "Candidate should avoid under-selling and clearly separate personal contribution from team contribution."
        return "Candidate needs more structured, evidence-based answers to reduce uncertainty for Japan-market interviewers."

    def _suggestions(self, risks: list[dict[str, str]], positive: list[str]) -> list[str]:
        suggestions = [risk["suggestion"] for risk in risks]
        suggestions.append("Prepare 60-second self-introduction in Japanese and English if the role is bilingual or Japan-facing.")
        suggestions.append("For each major project, prepare: context, task, action, result, stakeholder impact, and learning.")
        return self._dedupe_strings(suggestions)

    def _risk_questions(self, risks: list[dict[str, str]]) -> list[str]:
        if not risks:
            return ["Please introduce yourself and explain why this role fits your next career step."]
        return [f"Please answer again in a way that reduces this concern: {risk['risk']}." for risk in risks[:6]]

    def _why_it_matters(self, risk: str) -> str:
        mapping = {
            "Unclear logic structure": "Japanese interviewers often expect concise, conclusion-first answers with clear reasoning.",
            "Excessive humility": "Understating contribution can make seniority and ownership difficult to evaluate.",
            "Over-assertion": "Overconfident statements without evidence can reduce trust and perceived maturity.",
            "Negative resignation reason": "Negative framing can create concerns about teamwork and long-term fit.",
            "Missing individual ownership": "Hiring managers need to understand the candidate's direct contribution, not only team results.",
        }
        return mapping.get(risk, "This may create evaluation uncertainty in Japan-market interviews.")

    def _dedupe(self, risks: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[str] = set()
        output: list[dict[str, str]] = []
        for risk in risks:
            if risk["risk"] in seen:
                continue
            seen.add(risk["risk"])
            output.append(risk)
        return output

    def _dedupe_strings(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            output.append(item)
        return output
