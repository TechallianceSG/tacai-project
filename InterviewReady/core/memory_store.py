"""Persistent JSON memory for the Interview Readiness Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any


class MemoryStore:
    """Updates lightweight JSON memories after each engine interaction."""

    def __init__(self, memory_dir: Path | None = None) -> None:
        self.memory_dir = memory_dir or Path(__file__).resolve().parents[1] / "memory"
        self.skill_profile_path = self.memory_dir / "skill_profile.json"
        self.interview_patterns_path = self.memory_dir / "interview_patterns.json"
        self.candidate_history_path = self.memory_dir / "candidate_history.json"

    def record_jd_analysis(
        self,
        analysis: dict[str, Any],
        candidate_name: str | None = None,
        source: str = "manual-input",
    ) -> None:
        self.record_analysis(analysis, candidate_name=candidate_name, source=source, interaction_type="jd_analysis")

    def record_analysis(
        self,
        analysis: dict[str, Any],
        candidate_name: str | None = None,
        source: str = "manual-input",
        interaction_type: str = "analysis",
    ) -> None:
        """Record any engine result into all required memory files."""

        now = datetime.now(timezone.utc).isoformat()
        breakdown = analysis.get("jd_breakdown", {})

        self._record_skill_profile(analysis, breakdown, candidate_name, source, interaction_type, now)
        self._record_patterns(breakdown, analysis, now)
        self._record_candidate_history(analysis, candidate_name, source, interaction_type, now)

    def _record_skill_profile(
        self,
        analysis: dict[str, Any],
        breakdown: dict[str, Any],
        candidate_name: str | None,
        source: str,
        interaction_type: str,
        now: str,
    ) -> None:
        skill_profile = self._read_json(self.skill_profile_path, default={})
        skill_profile.setdefault("schema_version", 1)
        skill_profile.setdefault("observed_skills", {})
        skill_profile.setdefault("jd_history", [])
        for skill in breakdown.get("required_skills", []):
            name = skill.get("name")
            if not name:
                continue
            current = skill_profile["observed_skills"].setdefault(
                name,
                {"count": 0, "category": skill.get("category", "unknown"), "last_seen": None},
            )
            current["count"] += 1
            current["category"] = skill.get("category", current.get("category", "unknown"))
            current["last_seen"] = now
        skill_profile["jd_history"].append(
            {
                "source": source,
                "candidate_name": candidate_name,
                "interaction_type": interaction_type,
                "summary": analysis.get("summary"),
                "skill_count": len(breakdown.get("required_skills", [])),
                "risk_count": len(breakdown.get("risk_points", [])),
                "candidate_fit_score": analysis.get("candidate_fit_score"),
                "created_at": now,
            }
        )
        skill_profile["jd_history"] = skill_profile["jd_history"][-200:]
        skill_profile["last_updated"] = now
        self._write_json(self.skill_profile_path, skill_profile)

    def _record_patterns(self, breakdown: dict[str, Any], analysis: dict[str, Any], now: str) -> None:
        patterns = self._read_json(self.interview_patterns_path, default={})
        patterns.setdefault("schema_version", 1)
        patterns.setdefault("focus_area_counts", {})
        patterns.setdefault("hidden_expectation_counts", {})
        patterns.setdefault("risk_pattern_counts", {})
        patterns.setdefault("score_history", [])
        for focus in breakdown.get("interview_focus_areas", []):
            self._increment(patterns["focus_area_counts"], focus.get("area"))
        for expectation in breakdown.get("hidden_expectations", []):
            self._increment(patterns["hidden_expectation_counts"], expectation.get("expectation"))
        for risk in breakdown.get("risk_points", []):
            self._increment(patterns["risk_pattern_counts"], risk.get("risk"))
        if analysis.get("candidate_fit_score") is not None:
            patterns["score_history"].append(
                {"score": analysis.get("candidate_fit_score"), "summary": analysis.get("summary"), "created_at": now}
            )
            patterns["score_history"] = patterns["score_history"][-200:]
        patterns["last_updated"] = now
        self._write_json(self.interview_patterns_path, patterns)

    def _record_candidate_history(
        self,
        analysis: dict[str, Any],
        candidate_name: str | None,
        source: str,
        interaction_type: str,
        now: str,
    ) -> None:
        candidates = self._read_json(self.candidate_history_path, default={})
        candidates.setdefault("schema_version", 1)
        candidates.setdefault("candidates", [])
        candidates["candidates"].append(
            {
                "candidate_name": candidate_name or "unknown",
                "interaction_type": interaction_type,
                "source": source,
                "summary": analysis.get("summary"),
                "candidate_fit_score": analysis.get("candidate_fit_score"),
                "strengths": analysis.get("strengths", [])[:10],
                "weaknesses": analysis.get("weaknesses", [])[:10],
                "created_at": now,
            }
        )
        candidates["candidates"] = candidates["candidates"][-500:]
        candidates["last_updated"] = now
        self._write_json(self.candidate_history_path, candidates)

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return dict(default)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        tmp_path.replace(path)

    def _increment(self, counter: dict[str, int], key: str | None) -> None:
        if not key:
            return
        counter[key] = int(counter.get(key, 0)) + 1
