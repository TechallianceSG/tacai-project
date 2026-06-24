"""Resume-to-JD matching engine for recruitment consultants."""

from __future__ import annotations

import re
from typing import Any

from .jd_analyzer import JDAnalyzer


class ResumeMatcher:
    """Scores candidate resume fit against a job description using transparent rules."""

    def __init__(self, analyzer: JDAnalyzer | None = None) -> None:
        self.analyzer = analyzer or JDAnalyzer()
        self.skill_taxonomy = self.analyzer.skill_taxonomy

    def match(
        self,
        resume_text: str,
        jd_text: str,
        candidate_name: str | None = None,
        source: str = "manual-input",
    ) -> dict[str, Any]:
        jd_analysis = self.analyzer.analyze(jd_text, source=source)
        jd_skills = jd_analysis["jd_breakdown"].get("required_skills", [])
        resume_skills = self._extract_resume_skills(resume_text)
        resume_skill_names = {skill["name"].lower() for skill in resume_skills}

        matched = [skill for skill in jd_skills if skill["name"].lower() in resume_skill_names]
        missing = [skill for skill in jd_skills if skill["name"].lower() not in resume_skill_names]
        category_score = self._category_coverage_score(jd_skills, matched)
        skill_score = round((len(matched) / max(len(jd_skills), 1)) * 55)
        seniority_score = self._seniority_score(resume_text, jd_text)
        communication_score = self._communication_score(resume_text, jd_analysis)
        japan_readiness_score = self._japan_readiness_score(resume_text, jd_text)
        score = min(100, skill_score + category_score + seniority_score + communication_score + japan_readiness_score)

        score_components = {
            "skill_match": skill_score,
            "category_coverage": category_score,
            "seniority_evidence": seniority_score,
            "communication_alignment": communication_score,
            "japan_readiness": japan_readiness_score,
        }
        matching_points = self._matching_points(matched, resume_text, jd_analysis, score_components)
        gap_points = self._gap_points(missing, jd_analysis, resume_text, score_components)
        suggestions = self._suggestions(missing, jd_analysis, resume_text)

        jd_analysis.update(
            {
                "summary": self._summary(candidate_name, score, matched, missing),
                "candidate_fit_score": score,
                "strengths": [point["point"] for point in matching_points] or ["No strong matching point detected yet."],
                "weaknesses": [point["point"] for point in gap_points] or ["No major gap detected yet."],
                "resume_match": {
                    "candidate_name": candidate_name,
                    "overall_score": score,
                    "score_label": self._score_label(score),
                    "matching_points": matching_points,
                    "gap_points": gap_points,
                    "matched_skills": matched,
                    "missing_skills": missing,
                    "resume_detected_skills": resume_skills,
                    "score_components": score_components,
                    "improvement_suggestions": suggestions,
                },
            }
        )
        jd_analysis["suggested_answers"] = self._candidate_answer_guidance(jd_analysis, matched, missing)
        return jd_analysis

    def _extract_resume_skills(self, resume_text: str) -> list[dict[str, str]]:
        lowered = resume_text.lower()
        hits: list[dict[str, str]] = []
        seen: set[str] = set()
        for category, skills in self.skill_taxonomy.items():
            for skill in skills:
                if skill.lower() in seen:
                    continue
                if self.analyzer._contains_skill(lowered, skill):
                    hits.append({"name": skill, "category": category})
                    seen.add(skill.lower())
        return hits

    def _category_coverage_score(self, jd_skills: list[dict[str, Any]], matched: list[dict[str, Any]]) -> int:
        required_categories = {skill.get("category") for skill in jd_skills if skill.get("category")}
        matched_categories = {skill.get("category") for skill in matched if skill.get("category")}
        if not required_categories:
            return 10
        return round((len(matched_categories) / len(required_categories)) * 15)

    def _seniority_score(self, resume_text: str, jd_text: str) -> int:
        jd_lower = jd_text.lower()
        resume_lower = resume_text.lower()
        senior_jd = any(token in jd_lower for token in ["senior", "lead", "architect", "manager", "principal"])
        evidence = ["led", "designed", "owned", "architected", "mentored", "managed", "改善", "設計", "リード"]
        if not senior_jd:
            return 8
        return 10 if any(token in resume_lower for token in evidence) else 3

    def _communication_score(self, resume_text: str, jd_analysis: dict[str, Any]) -> int:
        resume_lower = resume_text.lower()
        expectations = jd_analysis["jd_breakdown"].get("hidden_expectations", [])
        stakeholder_expected = any(item["expectation"] == "Stakeholder communication" for item in expectations)
        evidence = ["stakeholder", "client", "customer", "vendor", "requirement", "documentation", "顧客", "要件", "調整"]
        if not stakeholder_expected:
            return 7
        return 10 if any(token in resume_lower for token in evidence) else 4

    def _japan_readiness_score(self, resume_text: str, jd_text: str) -> int:
        combined = f"{resume_text}\n{jd_text}".lower()
        if any(token in combined for token in ["japanese", "jlpt", "bilingual", "日本語", "英語", "japan"]):
            return 10
        return 5

    def _matching_points(
        self,
        matched: list[dict[str, Any]],
        resume_text: str,
        jd_analysis: dict[str, Any],
        score_components: dict[str, int],
    ) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for skill in matched[:6]:
            points.append(
                {
                    "point": f"Required skill matched: {skill['name']} ({skill['category']}).",
                    "evidence": skill.get("evidence", "JD requires this skill and it appears in the resume."),
                    "impact": "Reduces technical screening risk.",
                }
            )

        if score_components["category_coverage"] >= 10:
            points.append(
                {
                    "point": "Resume covers multiple JD skill categories.",
                    "evidence": f"Category coverage score: {score_components['category_coverage']}/15.",
                    "impact": "Useful for broad or hybrid roles.",
                }
            )
        if score_components["seniority_evidence"] >= 8:
            points.append(
                {
                    "point": "Seniority/ownership evidence is visible.",
                    "evidence": "Resume contains leadership, design, ownership, or delivery decision signals.",
                    "impact": "Supports senior-role interview positioning.",
                }
            )
        if score_components["communication_alignment"] >= 8:
            points.append(
                {
                    "point": "Stakeholder/client communication alignment is visible.",
                    "evidence": "Resume includes client, stakeholder, documentation, requirements, or coordination signals.",
                    "impact": "Important for Japan client-facing recruitment roles.",
                }
            )
        if score_components["japan_readiness"] >= 10:
            points.append(
                {
                    "point": "Japan/bilingual readiness signal detected.",
                    "evidence": "Resume/JD mentions Japanese, English, bilingual work, JLPT, or Japan context.",
                    "impact": "Reduces communication-risk concern for Japan-market interviews.",
                }
            )
        if re.search(r"\d+%|\d+\s*(users|members|engineers|projects|years|年|名|件)", resume_text, re.I):
            points.append(
                {
                    "point": "Measurable impact evidence is present.",
                    "evidence": "Resume includes numeric scale, improvement percentage, team size, duration, or delivery count.",
                    "impact": "Makes interview answers more credible and easier to evaluate.",
                }
            )
        return points[:10]

    def _gap_points(
        self,
        missing: list[dict[str, Any]],
        jd_analysis: dict[str, Any],
        resume_text: str,
        score_components: dict[str, int],
    ) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        for skill in missing[:6]:
            gaps.append(
                {
                    "point": f"Missing or unclear required skill: {skill['name']} ({skill['category']}).",
                    "evidence": skill.get("evidence", "JD expects this skill, but resume evidence was not detected."),
                    "action": f"Add a concrete project bullet for {skill['name']} or prepare an adjacent-experience explanation.",
                }
            )

        if score_components["seniority_evidence"] < 8:
            gaps.append(
                {
                    "point": "Seniority/ownership evidence is not strong enough.",
                    "evidence": "Senior JD expectations require clear ownership, design decisions, mentoring, or accountability examples.",
                    "action": "Add STAR stories showing personal role, decision, tradeoff, and outcome.",
                }
            )
        if score_components["communication_alignment"] < 8:
            gaps.append(
                {
                    "point": "Stakeholder/client communication evidence is weak.",
                    "evidence": "JD implies communication with clients, stakeholders, or cross-functional teams.",
                    "action": "Add examples of requirement clarification, reporting, escalation, or documentation.",
                }
            )
        if score_components["japan_readiness"] < 10:
            gaps.append(
                {
                    "point": "Japan/bilingual readiness is not explicit.",
                    "evidence": "No clear Japanese/English/Japan-market communication signal was detected.",
                    "action": "Prepare or add Japanese/English self-introduction, project summary, and stakeholder examples if relevant.",
                }
            )
        if not re.search(r"\d+%|\d+\s*(users|members|engineers|projects|years|年|名|件)", resume_text, re.I):
            gaps.append(
                {
                    "point": "Resume lacks measurable business or delivery outcomes.",
                    "evidence": "No clear numeric impact, scale, team size, duration, or improvement percentage detected.",
                    "action": "Quantify project impact with numbers before interview preparation.",
                }
            )
        for risk in jd_analysis["jd_breakdown"].get("risk_points", [])[:3]:
            gaps.append(
                {
                    "point": f"Interview risk to prepare: {risk['risk']}.",
                    "evidence": risk.get("why_it_matters", "Detected from JD context."),
                    "action": risk.get("mitigation", "Prepare a concise example that reduces this concern."),
                }
            )
        return gaps[:10]

    def _suggestions(self, missing: list[dict[str, Any]], jd_analysis: dict[str, Any], resume_text: str) -> list[str]:
        suggestions = [
            f"Add a project bullet showing hands-on experience with {skill['name']} or explain adjacent experience."
            for skill in missing[:6]
        ]
        suggestions.extend(
            f"Prepare story for {focus['area']}: {focus['reason']}"
            for focus in jd_analysis["jd_breakdown"].get("interview_focus_areas", [])[:4]
        )
        if "japanese" in jd_analysis.get("summary", "").lower() or "日本" in resume_text:
            suggestions.append("Prepare concise Japanese and English versions of self-introduction and project summary.")
        return suggestions

    def _candidate_answer_guidance(
        self,
        jd_analysis: dict[str, Any],
        matched: list[dict[str, Any]],
        missing: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        top_match = matched[0]["name"] if matched else "your strongest relevant project"
        top_gap = missing[0]["name"] if missing else "remaining role expectations"
        return {
            "en": [
                f"For {top_match}, explain one production example with context, your role, tradeoffs, and measurable result.",
                f"For {top_gap}, be transparent: explain adjacent experience, learning plan, and how you would ramp up quickly.",
            ],
            "jp": [
                f"{top_match}については、本番環境での具体例、担当範囲、判断理由、成果を簡潔に説明してください。",
                f"{top_gap}に不足がある場合は、関連経験、キャッチアップ計画、早期に貢献する方法を正直に伝えてください。",
            ],
        }

    def _summary(
        self,
        candidate_name: str | None,
        score: int,
        matched: list[dict[str, Any]],
        missing: list[dict[str, Any]],
    ) -> str:
        name = candidate_name or "Candidate"
        matched_names = ", ".join(skill["name"] for skill in matched[:5]) or "limited explicit JD skills"
        missing_names = ", ".join(skill["name"] for skill in missing[:5]) or "no major required skills"
        return f"{name} scores {score}/100 ({self._score_label(score)}). Matched: {matched_names}. Gaps to address: {missing_names}."

    def _score_label(self, score: int) -> str:
        if score >= 85:
            return "Strong fit"
        if score >= 70:
            return "Good fit with preparation needed"
        if score >= 50:
            return "Partial fit"
        return "High gap"
