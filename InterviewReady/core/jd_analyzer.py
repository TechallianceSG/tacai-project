"""Rule-based job description analyzer for the MVP engine.

The analyzer is intentionally deterministic and dependency-free so the first MVP can
run locally without an LLM key. Later phases can replace or augment individual
methods with model calls while preserving the same output contract.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re
from typing import Any


@dataclass(frozen=True)
class SkillHit:
    name: str
    category: str
    importance: str
    evidence: str


class JDAnalyzer:
    """Extracts structured recruitment signals from job descriptions."""

    DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "knowledge_base" / "skill_taxonomy.json"

    def __init__(self, taxonomy_path: Path | None = None) -> None:
        self.taxonomy_path = taxonomy_path or self.DEFAULT_TAXONOMY_PATH
        self.skill_taxonomy = self._load_taxonomy(self.taxonomy_path)

    def analyze(self, jd_text: str, source: str = "manual-input") -> dict[str, Any]:
        clean_text = self._clean(jd_text)
        if not clean_text:
            raise ValueError("JD text is empty. Provide a job description to analyze.")

        sentences = self._sentences(clean_text)
        required_skills = self._extract_required_skills(clean_text, sentences)
        hidden_expectations = self._detect_hidden_expectations(clean_text)
        focus_areas = self._derive_interview_focus_areas(required_skills, hidden_expectations, clean_text)
        risk_points = self._detect_risk_points(clean_text, required_skills, hidden_expectations)
        questions = self._generate_interview_questions(required_skills, focus_areas, risk_points)
        suggested_answers = self._generate_suggested_answers(focus_areas, risk_points)

        return {
            "source": source,
            "summary": self._summary(required_skills, focus_areas, risk_points),
            "jd_breakdown": {
                "required_skills": [asdict(skill) for skill in required_skills],
                "hidden_expectations": hidden_expectations,
                "interview_focus_areas": focus_areas,
                "risk_points": risk_points,
            },
            "candidate_fit_score": None,
            "strengths": [],
            "weaknesses": [],
            "interview_questions": questions,
            "suggested_answers": suggested_answers,
        }

    def _load_taxonomy(self, path: Path) -> dict[str, list[str]]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        return {str(category): [str(skill) for skill in skills] for category, skills in loaded.items()}

    def _clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _sentences(self, text: str) -> list[str]:
        rough_sentences = re.split(r"(?<=[.!?。！？])\s+|\n+|(?<=;)\s+", text)
        return [sentence.strip(" -•\t") for sentence in rough_sentences if sentence.strip()]

    def _extract_required_skills(self, text: str, sentences: list[str]) -> list[SkillHit]:
        hits: list[SkillHit] = []
        seen: set[str] = set()
        lowered = text.lower()

        for category, skills in self.skill_taxonomy.items():
            for skill in skills:
                if not self._contains_skill(lowered, skill):
                    continue
                key = skill.lower()
                if key in seen:
                    continue
                evidence = self._first_evidence_sentence(sentences, skill)
                hits.append(
                    SkillHit(
                        name=skill,
                        category=category,
                        importance=self._importance(evidence),
                        evidence=evidence,
                    )
                )
                seen.add(key)

        return sorted(hits, key=lambda hit: (hit.category, hit.name.lower()))

    def _contains_skill(self, lowered_text: str, skill: str) -> bool:
        lowered_skill = skill.lower()
        if re.search(r"[a-z0-9]", lowered_skill):
            return re.search(rf"(?<![a-z0-9+#.]){re.escape(lowered_skill)}(?![a-z0-9+#.])", lowered_text) is not None
        return lowered_skill in lowered_text

    def _first_evidence_sentence(self, sentences: list[str], skill: str) -> str:
        lowered_skill = skill.lower()
        for sentence in sentences:
            if lowered_skill in sentence.lower():
                return sentence[:260]
        return "Mentioned in JD."

    def _importance(self, evidence: str) -> str:
        lowered = evidence.lower()
        if any(token in lowered for token in ["must", "required", "mandatory", "必須", "need to", "strong experience"]):
            return "required"
        if any(token in lowered for token in ["preferred", "nice to have", "plus", "歓迎", "bonus"]):
            return "preferred"
        return "expected"

    def _detect_hidden_expectations(self, text: str) -> list[dict[str, str]]:
        lowered = text.lower()
        rules = [
            (
                ["client", "customer", "stakeholder", "vendor", "consulting", "顧客", "クライアント"],
                "Stakeholder communication",
                "Candidate should prepare examples of requirement clarification, expectation management, and client-facing communication.",
            ),
            (
                ["legacy", "migration", "modernization", "refactor", "刷新", "移行"],
                "Change management in existing systems",
                "Candidate should explain safe delivery, risk control, and incremental rollout experience.",
            ),
            (
                ["lead", "senior", "mentor", "architect", "ownership", "technical decision"],
                "Technical ownership",
                "Candidate should show decision-making, mentoring, design tradeoffs, and accountability for outcomes.",
            ),
            (
                ["agile", "scrum", "cross-functional", "product", "requirements", "要件定義"],
                "Product and delivery collaboration",
                "Candidate should prepare stories connecting business goals to implementation choices.",
            ),
            (
                ["japanese", "english", "bilingual", "jlpt", "日本語", "英語"],
                "Bilingual workplace readiness",
                "Candidate should be ready to answer in the required language and explain technical topics simply.",
            ),
            (
                ["on-call", "incident", "sre", "production", "運用", "障害"],
                "Production reliability mindset",
                "Candidate should prepare incident response, monitoring, escalation, and postmortem examples.",
            ),
        ]

        expectations: list[dict[str, str]] = []
        for keywords, expectation, preparation_note in rules:
            matched = [keyword for keyword in keywords if keyword in lowered]
            if matched:
                expectations.append(
                    {
                        "expectation": expectation,
                        "signals": matched[:5],
                        "preparation_note": preparation_note,
                    }
                )
        return expectations

    def _derive_interview_focus_areas(
        self,
        required_skills: list[SkillHit],
        hidden_expectations: list[dict[str, str]],
        text: str,
    ) -> list[dict[str, str]]:
        category_counts: dict[str, int] = {}
        for skill in required_skills:
            category_counts[skill.category] = category_counts.get(skill.category, 0) + 1

        focus_areas = [
            {
                "area": self._humanize(category),
                "reason": f"JD references {count} skill(s) in this area.",
            }
            for category, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
        ]

        for expectation in hidden_expectations:
            focus_areas.append(
                {
                    "area": expectation["expectation"],
                    "reason": expectation["preparation_note"],
                }
            )

        lowered = text.lower()
        if "system design" in lowered or "architecture" in lowered or "設計" in text:
            focus_areas.append(
                {
                    "area": "System design depth",
                    "reason": "JD indicates architecture/design responsibility; expect tradeoff and scalability questions.",
                }
            )

        return self._dedupe_dicts(focus_areas, key="area")[:10]

    def _detect_risk_points(
        self,
        text: str,
        required_skills: list[SkillHit],
        hidden_expectations: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        lowered = text.lower()
        risks: list[dict[str, str]] = []

        if len(required_skills) < 3:
            risks.append(
                {
                    "risk": "Underspecified technical requirements",
                    "why_it_matters": "The interview may rely on unstated client expectations rather than explicit JD keywords.",
                    "mitigation": "Prepare broad project examples and ask clarifying questions about stack, scope, and success metrics.",
                }
            )

        categories = {skill.category for skill in required_skills}
        if len(categories) >= 4:
            risks.append(
                {
                    "risk": "Broad full-stack or hybrid scope",
                    "why_it_matters": "Candidate may be tested across multiple domains, not just their strongest area.",
                    "mitigation": "Frame experience by depth, recency, and role in each domain to avoid overclaiming.",
                }
            )

        if any(item["expectation"] == "Bilingual workplace readiness" for item in hidden_expectations):
            risks.append(
                {
                    "risk": "Language-switching pressure",
                    "why_it_matters": "Japan-based interviews may move between English and Japanese to validate practical communication ability.",
                    "mitigation": "Prepare concise self-introduction, project summary, and failure/learning story in both JP and EN.",
                }
            )

        if any(token in lowered for token in ["senior", "lead", "architect", "manager"]):
            risks.append(
                {
                    "risk": "Seniority evidence gap",
                    "why_it_matters": "Interviewers will expect ownership, decision-making, and measurable impact, not only implementation tasks.",
                    "mitigation": "Use STAR stories with project scale, constraints, decisions, outcomes, and stakeholder impact.",
                }
            )

        if any(token in lowered for token in ["contract", "dispatch", "ses", "onsite", "客先常駐"]):
            risks.append(
                {
                    "risk": "Client-site adaptability",
                    "why_it_matters": "Japan IT roles may emphasize reliability, reporting discipline, and smooth client integration.",
                    "mitigation": "Prepare examples of communication cadence, documentation, escalation, and adapting to client processes.",
                }
            )

        return self._dedupe_dicts(risks, key="risk")

    def _generate_interview_questions(
        self,
        required_skills: list[SkillHit],
        focus_areas: list[dict[str, str]],
        risk_points: list[dict[str, str]],
    ) -> dict[str, list[str]]:
        top_skills = required_skills[:6]
        technical = [
            f"How have you used {skill.name} in production, and what tradeoffs did you manage?"
            for skill in top_skills
        ]
        if not technical:
            technical.append("Walk through the most technically complex system you worked on and your concrete contribution.")
        technical.append("Describe a system design decision you made, the alternatives considered, and the outcome.")

        behavioral = [
            "Tell me about a time you had to clarify ambiguous requirements with stakeholders.",
            "Describe a project challenge, what you owned personally, and what changed because of your actions.",
        ]
        for risk in risk_points[:3]:
            behavioral.append(f"How would you address this potential concern in interview: {risk['risk']}?")

        rubric = [
            "Specificity: concrete scope, tools, constraints, and metrics.",
            "Ownership: clear personal contribution versus team contribution.",
            "Tradeoff reasoning: why choices were made and what alternatives were rejected.",
            "Communication: structured, concise, and adapted to technical/non-technical listeners.",
        ]

        return {
            "technical": technical[:8],
            "behavioral": behavioral[:8],
            "scoring_rubric": rubric,
            "focus_area_prompts": [f"Prepare evidence for: {area['area']}" for area in focus_areas[:6]],
        }

    def _generate_suggested_answers(
        self,
        focus_areas: list[dict[str, str]],
        risk_points: list[dict[str, str]],
    ) -> dict[str, list[str]]:
        primary_focus = focus_areas[0]["area"] if focus_areas else "the role requirements"
        primary_risk = risk_points[0]["risk"] if risk_points else "any unclear expectations"
        return {
            "en": [
                f"For {primary_focus}, I would answer with a specific project example: context, my responsibility, technical decision, measurable result, and what I learned.",
                f"To reduce concern around {primary_risk}, I would proactively clarify scope and give evidence of similar situations I handled successfully.",
            ],
            "jp": [
                f"{primary_focus}については、プロジェクトの背景、自分の役割、技術的な判断、成果、学びを順番に説明します。",
                f"{primary_risk}に関する懸念を下げるため、過去の類似経験と具体的な対応方法を簡潔に伝えます。",
            ],
        }

    def _summary(
        self,
        required_skills: list[SkillHit],
        focus_areas: list[dict[str, str]],
        risk_points: list[dict[str, str]],
    ) -> str:
        skill_names = ", ".join(skill.name for skill in required_skills[:5]) or "few explicit technical skills"
        focus = focus_areas[0]["area"] if focus_areas else "general engineering capability"
        risk = risk_points[0]["risk"] if risk_points else "no major JD-level risk detected"
        return f"JD emphasizes {skill_names}. Primary interview focus is {focus}. Main preparation risk: {risk}."

    def _humanize(self, value: str) -> str:
        return value.replace("_", " ").title()

    def _dedupe_dicts(self, items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in items:
            marker = str(item.get(key, "")).lower()
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        return deduped
