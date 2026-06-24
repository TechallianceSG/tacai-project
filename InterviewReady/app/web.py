"""Local Web UI for the Interview Readiness Engine.

This intentionally uses Python's standard library to keep the MVP locally runnable
without requiring a web framework. Future versions can wrap the same core engines
with FastAPI or another production web stack.
"""

from __future__ import annotations

import argparse
import cgi
from datetime import datetime, timezone
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

from core import (
    DocumentLoader,
    JDAnalyzer,
    JapanInterviewRiskEngine,
    MemoryStore,
    MockInterviewEngine,
    ReportWriter,
    ResumeMatcher,
)


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"
ANALYSIS_RUNS_FILE = DATABASE_DIR / "analysis_runs.json"
AUDIT_LOG_FILE = DATABASE_DIR / "interview_ready_audit_logs.json"
REPORT_INDEX_FILE = DATABASE_DIR / "report_index.json"

TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
APP_BASE_URL = f"http://{TACAI_PUBLIC_HOST}:8000"
PORTAL_BASE_URL = (os.environ.get("PORTAL_PUBLIC_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8005").strip() or f"http://{TACAI_PUBLIC_HOST}:8005").rstrip("/")
USER_ADMIN_BASE_URL = f"http://{TACAI_PUBLIC_HOST}:8006"
USER_ADMIN_INTERNAL_BASE_URL = f"http://{TACAI_INTERNAL_HOST}:8006"
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
MODULE_KEY = "interview_ready"
REQUIRED_MODULE_PERMISSION = "interview_ready.access"
FEATURE_PERMISSIONS = {
    "jd-insight": "interview_ready.jd_insight",
    "resume-match": "interview_ready.resume_match",
    "mock-interview": "interview_ready.mock_interview",
    "japan-risk": "interview_ready.japan_risk",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def write_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def next_id(records: list[dict[str, Any]], key: str, prefix: str) -> str:
    max_number = 0
    for record in records:
        value = str(record.get(key, ""))
        if value.startswith(prefix):
            raw = value.removeprefix(prefix)
            if raw.isdigit():
                max_number = max(max_number, int(raw))
    return f"{prefix}{max_number + 1:06d}"


def validate_user_admin_session(session_id: str) -> dict | None:
    if not session_id:
        return None
    payload = json.dumps({"session_id": session_id}).encode("utf-8")
    request = Request(
        f"{USER_ADMIN_INTERNAL_BASE_URL}/api/validate-session",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None
    if data.get("valid") and isinstance(data.get("user"), dict):
        user = data["user"]
        if isinstance(data.get("session"), dict):
            user["_session"] = data["session"]
        return user
    return None


def has_permission(user: dict, permission_key: str) -> bool:
    roles = set(user.get("roles", []))
    permissions = set(user.get("permissions", []))
    return "system_admin" in roles or permission_key in permissions


def entity_context(user: dict) -> dict[str, str]:
    entity = user.get("entity") if isinstance(user.get("entity"), dict) else {}
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    session_entity = session.get("entity") if isinstance(session.get("entity"), dict) else {}
    return {
        "entity_id": str(entity.get("entity_id") or user.get("entity_id") or session_entity.get("entity_id") or "").strip(),
        "entity_code": str(entity.get("entity_code") or user.get("entity_code") or session_entity.get("entity_code") or "").strip(),
        "entity_name_en": str(entity.get("entity_name_en") or user.get("entity_name") or session_entity.get("entity_name_en") or "").strip(),
        "entity_name_ja": str(entity.get("entity_name_ja") or session_entity.get("entity_name_ja") or "").strip(),
        "entity_name_zh": str(entity.get("entity_name_zh") or session_entity.get("entity_name_zh") or "").strip(),
    }


def has_entity_context(user: dict) -> bool:
    context = entity_context(user)
    return bool(context.get("entity_id") and context.get("entity_code"))


def audit_actor_from_user(user: dict | None) -> str:
    if not user:
        return "unknown"
    for key in ["email", "username", "display_name", "user_id"]:
        value = str(user.get(key, "")).strip()
        if value:
            return value
    return "unknown"


def safe_relative_report_path(path: str) -> str:
    try:
        report_path = Path(path).resolve()
        return str(report_path.relative_to(BASE_DIR))
    except (ValueError, OSError):
        return str(path)


class InterviewReadyHandler(BaseHTTPRequestHandler):
    server_version = "InterviewReadyWeb/0.4"

    def current_user(self) -> dict | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(USER_ADMIN_SESSION_COOKIE)
        if not session_cookie:
            return None
        return validate_user_admin_session(session_cookie.value)

    def require_user(self) -> dict | None:
        user = self.current_user()
        if not user:
            next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
            self.send_response(303)
            self.send_header("Location", f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
            self.end_headers()
            return None
        if not has_entity_context(user):
            self.send_error(403, "InterviewReady requires a User_admin session with Entity context.")
            return None
        if not has_permission(user, REQUIRED_MODULE_PERMISSION):
            self.send_error(403, "This User_admin account does not have permission to access InterviewReady.")
            return None
        return user

    def require_permission(self, user: dict, permission_key: str, label: str) -> bool:
        if has_permission(user, permission_key):
            return True
        self.send_error(403, f"This User_admin account does not have permission to {label}.")
        return False

    def require_feature_permission(self, user: dict, feature: str) -> bool:
        permission_key = FEATURE_PERMISSIONS.get(feature)
        if permission_key and has_permission(user, permission_key):
            return True
        self.send_error(403, f"This User_admin account does not have permission to run {self._feature_title(feature)}.")
        return False

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_text("OK")
            return
        user = self.require_user()
        if not user:
            return
        if parsed.path in {"/", "/dashboard"}:
            self._send_html(self._page(user=user))
            return
        if parsed.path == "/reports":
            if not self.require_permission(user, "interview_ready.report.view", "view InterviewReady reports"):
                return
            self._send_html(self._page(user=user, result_html=self._reports_html(), active_feature="reports"))
            return
        if parsed.path == "/report":
            if not self.require_permission(user, "interview_ready.report.view", "view InterviewReady reports"):
                return
            query = parse_qs(parsed.query)
            self._send_html(self._page(user=user, result_html=self._report_detail_html(query.get("id", [""])[0], user=user), active_feature="reports"))
            return
        if parsed.path == "/report/export":
            if not self.require_permission(user, "interview_ready.report.export", "export InterviewReady reports"):
                return
            query = parse_qs(parsed.query)
            self._export_report(query.get("id", [""])[0], user)
            return
        if parsed.path == "/audit":
            if not self.require_permission(user, "interview_ready.audit.view", "view InterviewReady audit logs"):
                return
            self._send_html(self._page(user=user, result_html=self._audit_html(), active_feature="audit"))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        user = self.require_user()
        if not user:
            return
        parsed = urlparse(self.path)
        if parsed.path != "/analyze":
            self.send_error(404, "Not found")
            return

        try:
            form = self._parse_form()
            feature = form.get("feature", "jd-insight")
            if not self.require_feature_permission(user, feature):
                return
            candidate_name = form.get("candidate_name") or None
            source = form.get("source") or feature
            target_company = form.get("target_company", "")
            client_company = form.get("client_company", "") or target_company
            target_role = form.get("target_role", "")
            department = form.get("department", "")
            team = form.get("team", "")
            consent_status = form.get("candidate_consent", "")
            if feature != "jd-insight" and consent_status != "confirmed_internal_use":
                raise ValueError("Candidate-specific analysis requires confirmation that candidate data is used for internal recruitment support only.")

            jd_text = self._collect_input(form, "jd_file", "jd_text")
            resume_text = self._collect_input(form, "resume_file", "resume_text")
            candidate_text = self._collect_input(form, "candidate_file", "candidate_text") or resume_text
            benchmark_text = self._collect_input(form, "benchmark_file", "benchmark_text")

            analysis = self._run_feature(
                feature=feature,
                jd_text=jd_text,
                resume_text=resume_text,
                candidate_text=candidate_text,
                benchmark_text=benchmark_text,
                candidate_name=candidate_name,
                source=source,
                target_company=target_company,
            )
            MemoryStore().record_analysis(analysis, candidate_name=candidate_name, source=source, interaction_type=feature)
            report_path = ReportWriter().write_interview_prep_report(analysis, candidate_name=candidate_name, source=source)
            rendered = ReportWriter().render(analysis, candidate_name, source)
            run_record = self._record_analysis_run(
                user=user,
                form=form,
                analysis=analysis,
                feature=feature,
                candidate_name=candidate_name,
                source=source,
                client_company=client_company,
                target_role=target_role,
                department=department,
                team=team,
                consent_status=consent_status,
                report_path=report_path,
            )
            self._append_audit_log(
                record_id=run_record["analysis_id"],
                action=f"run_{feature.replace('-', '_')}",
                user=user,
                before_value=None,
                after_value={
                    "feature": feature,
                    "candidate_name": candidate_name or "",
                    "client_company": client_company,
                    "target_role": target_role,
                    "entity_id": run_record.get("entity_id", ""),
                    "report_path": safe_relative_report_path(str(report_path)),
                },
            )
            result_html = f"""
            <section class='result sap-section'>
              <div class='message-strip success-strip'>Analysis record {escape(run_record['analysis_id'])} for {escape(candidate_name or source or feature)} saved successfully at {escape(run_record['created_at'])}.</div>
              <div class='sap-object-meta'>
                <span><strong>Feature</strong>{escape(self._feature_title(feature))}</span>
                <span><strong>Entity</strong>{escape(run_record.get('entity_code', ''))}</span>
                <span><strong>Client</strong>{escape(client_company or '-')}</span>
                <span><strong>Role</strong>{escape(target_role or '-')}</span>
              </div>
              <p><strong>Report:</strong> {escape(safe_relative_report_path(str(report_path)))}</p>
              <p><a class='secondary-link' href='/report?id={escape(run_record['analysis_id'])}'>View saved report</a> <a class='secondary-link' href='/reports'>Report history</a></p>
              {self._result_summary_html(analysis, feature)}
              <details>
                <summary>Full Markdown report</summary>
                <pre>{escape(rendered)}</pre>
              </details>
            </section>
            """
            self._send_html(self._page(result_html=result_html, active_feature=feature, user=user))
        except Exception as exc:  # noqa: BLE001 - web UI should show operational errors.
            error_html = f"<section class='error sap-section'><h2>Error</h2><div class='message-strip error-strip'>{escape(str(exc))}</div></section>"
            self._send_html(self._page(result_html=error_html, user=user), status=400)

    def _parse_form(self) -> dict[str, str]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return self._parse_multipart_form()

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        return {key: values[0] for key, values in parse_qs(body).items()}

    def _parse_multipart_form(self) -> dict[str, str]:
        fields = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        form: dict[str, str] = {}
        for key in fields.keys():
            item = fields[key]
            values = item if isinstance(item, list) else [item]
            for index, value in enumerate(values):
                field_key = key if index == 0 else f"{key}_{index + 1}"
                if value.filename:
                    loaded_text = self._load_uploaded_file(value.filename, value.file.read())
                    form[f"{field_key}_text"] = loaded_text
                    form[f"{field_key}_name"] = value.filename
                else:
                    raw_value = value.value
                    form[field_key] = raw_value if isinstance(raw_value, str) else raw_value.decode("utf-8", errors="replace")
        return form

    def _load_uploaded_file(self, filename: str, content: bytes) -> str:
        if not content:
            return ""
        suffix = Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            return DocumentLoader().load(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _collect_input(self, form: dict[str, str], file_prefix: str, text_key: str) -> str:
        parts: list[str] = []
        for index in range(1, 5):
            uploaded = form.get(f"{file_prefix}_{index}_text", "").strip()
            filename = form.get(f"{file_prefix}_{index}_name", "")
            if uploaded:
                header = f"\n\n--- Uploaded file {index}: {filename or file_prefix} ---\n"
                parts.append(header + uploaded)
        pasted = form.get(text_key, "").strip()
        if pasted:
            parts.append(f"\n\n--- Text input: {text_key} ---\n{pasted}")
        return "\n".join(parts).strip()

    def _input_summary(self, form: dict[str, str]) -> dict[str, Any]:
        file_counts: dict[str, int] = {}
        for prefix in ["jd_file", "resume_file", "candidate_file", "benchmark_file"]:
            file_counts[prefix] = sum(1 for index in range(1, 5) if form.get(f"{prefix}_{index}_text", "").strip())
        text_inputs = [key for key in ["jd_text", "resume_text", "candidate_text", "benchmark_text"] if form.get(key, "").strip()]
        return {"file_counts": file_counts, "text_inputs": text_inputs}

    def _result_summary(self, analysis: dict, feature: str) -> dict[str, Any]:
        summary = {"summary": str(analysis.get("summary", ""))[:300]}
        if analysis.get("candidate_fit_score") is not None:
            summary["fit_score"] = analysis.get("candidate_fit_score")
        if isinstance(analysis.get("japan_risk"), dict):
            summary["risk_score"] = analysis["japan_risk"].get("communication_risk_score")
        if isinstance(analysis.get("resume_match"), dict):
            summary["match_score"] = analysis["resume_match"].get("overall_score")
        summary["feature"] = feature
        return summary

    def _record_analysis_run(
        self,
        *,
        user: dict,
        form: dict[str, str],
        analysis: dict,
        feature: str,
        candidate_name: str | None,
        source: str,
        client_company: str,
        target_role: str,
        department: str,
        team: str,
        consent_status: str,
        report_path: Path,
    ) -> dict[str, Any]:
        records = read_json_array(ANALYSIS_RUNS_FILE)
        analysis_id = next_id(records, "analysis_id", "IR-")
        entity = entity_context(user)
        timestamp = utc_now_iso()
        record = {
            "analysis_id": analysis_id,
            "entity_id": entity.get("entity_id", ""),
            "entity_code": entity.get("entity_code", ""),
            "entity_name_en": entity.get("entity_name_en", ""),
            "department": department,
            "team": team,
            "user_id": str(user.get("user_id", "")),
            "user_display_name": str(user.get("display_name") or user.get("username") or ""),
            "created_by": audit_actor_from_user(user),
            "feature": feature,
            "feature_label": self._feature_title(feature),
            "candidate_name": candidate_name or "",
            "client_company": client_company,
            "target_role": target_role,
            "source": source,
            "candidate_consent_status": consent_status or "not_required",
            "input_summary": self._input_summary(form),
            "result_summary": self._result_summary(analysis, feature),
            "report_path": str(report_path),
            "report_relative_path": safe_relative_report_path(str(report_path)),
            "created_at": timestamp,
            "status": "completed",
        }
        records.append(record)
        write_json_array(ANALYSIS_RUNS_FILE, records)

        report_index = read_json_array(REPORT_INDEX_FILE)
        report_index.append(
            {
                "report_id": analysis_id,
                "analysis_id": analysis_id,
                "feature": feature,
                "candidate_name": candidate_name or "",
                "client_company": client_company,
                "target_role": target_role,
                "created_at": timestamp,
                "created_by": audit_actor_from_user(user),
                "entity_code": entity.get("entity_code", ""),
                "report_path": str(report_path),
                "report_relative_path": safe_relative_report_path(str(report_path)),
                "status": "available",
            }
        )
        write_json_array(REPORT_INDEX_FILE, report_index)
        return record

    def _append_audit_log(self, *, record_id: str, action: str, user: dict, before_value: Any, after_value: Any) -> None:
        logs = read_json_array(AUDIT_LOG_FILE)
        logs.append(
            {
                "audit_id": next_id(logs, "audit_id", "AUD-"),
                "module": MODULE_KEY,
                "record_id": record_id,
                "action": action,
                "user": audit_actor_from_user(user),
                "timestamp": utc_now_iso(),
                "before_value": before_value,
                "after_value": after_value,
            }
        )
        write_json_array(AUDIT_LOG_FILE, logs)

    def _run_feature(
        self,
        feature: str,
        jd_text: str,
        resume_text: str,
        candidate_text: str,
        benchmark_text: str,
        candidate_name: str | None,
        source: str,
        target_company: str,
    ) -> dict:
        if feature == "jd-insight":
            if not jd_text:
                raise ValueError("JD Insight requires at least one JD file or JD text input.")
            analysis = JDAnalyzer().analyze(jd_text, source=source)
            self._attach_jd_insight(analysis, target_company=target_company, benchmark_text=benchmark_text)
            return analysis
        if feature == "resume-match":
            if not jd_text or not resume_text:
                raise ValueError("Resume Match requires JD input and resume/profile input.")
            return ResumeMatcher().match(resume_text, jd_text, candidate_name=candidate_name, source=source)
        if feature == "mock-interview":
            if not jd_text:
                raise ValueError("AI Mock Interview requires JD input.")
            return MockInterviewEngine().generate(jd_text, candidate_text, candidate_name=candidate_name, source=source)
        if feature == "japan-risk":
            if not candidate_text:
                raise ValueError("Japanese Interview Risk Analysis requires candidate answer/profile input.")
            return JapanInterviewRiskEngine().analyze(candidate_text, jd_text, candidate_name=candidate_name, source=source)
        raise ValueError(f"Unknown feature: {feature}")

    def _attach_jd_insight(self, analysis: dict, target_company: str, benchmark_text: str) -> None:
        benchmark_signals = []
        lowered = benchmark_text.lower()
        signal_rules = [
            ("MNC/global company style", ["global", "mnc", "multinational", "english", "regional"]),
            ("Japanese enterprise style", ["japanese", "日本", "顧客", "稟議", "調整", "documentation"]),
            ("Startup/product style", ["startup", "product", "0-1", "scale", "growth"]),
            ("SIer/client delivery style", ["client", "vendor", "sier", "onsite", "ses", "客先"]),
            ("Technical-depth interview style", ["architecture", "system design", "coding", "technical assessment"]),
        ]
        for signal, keywords in signal_rules:
            matched = [keyword for keyword in keywords if keyword in lowered]
            if matched:
                benchmark_signals.append({"signal": signal, "evidence": ", ".join(matched[:5])})
        if target_company or benchmark_text:
            analysis["jd_insight"] = {
                "target_company": target_company or "Not provided",
                "benchmark_input_provided": bool(benchmark_text),
                "benchmark_signals": benchmark_signals or [
                    {
                        "signal": "No strong benchmark signal detected",
                        "evidence": "Provide company profile, peer company notes, or hiring-manager feedback to improve benchmark analysis.",
                    }
                ],
                "consultant_notes": [
                    "Compare JD requirements against known company interview style before candidate coaching.",
                    "Use benchmark signals to adjust question difficulty, communication style, and seniority expectations.",
                ],
            }

    def _feature_title(self, feature: str) -> str:
        return {
            "jd-insight": "JD Insight",
            "resume-match": "Resume Match",
            "mock-interview": "AI Mock Interview",
            "japan-risk": "Japanese Interview Risk Analysis",
            "reports": "Report History",
            "audit": "Audit Trail",
        }.get(feature, feature)

    def _result_summary_html(self, analysis: dict, feature: str) -> str:
        if feature == "jd-insight":
            return self._jd_insight_result_html(analysis)
        if feature == "resume-match":
            return self._resume_result_html(analysis, analysis.get("resume_match") or {})
        if feature == "mock-interview":
            return self._mock_result_html(analysis)
        if feature == "japan-risk":
            return self._risk_result_html(analysis)
        return self._generic_result_html(analysis)

    def _resume_result_html(self, analysis: dict, resume_match: dict) -> str:
        score = analysis.get("candidate_fit_score")
        score_text = "Not evaluated" if score is None else f"{score}/100"
        score_label = resume_match.get("score_label", "")
        matching_points = resume_match.get("matching_points", [])[:10]
        gap_points = resume_match.get("gap_points", [])[:10]
        return f"""
        <div class='score-card'>
          <div class='score-number'>{escape(score_text)}</div>
          <div>
            <div class='score-label'>{escape(score_label)}</div>
            <div class='muted'>Candidate fit score / 候補者適合スコア（100点満点）</div>
          </div>
        </div>
        <div class='grid'>
          <section class='panel good'>
            <h3>Matching points / マッチポイント（最大10項目）</h3>
            {self._point_list_html(matching_points, "No explicit matching points detected.", "impact")}
          </section>
          <section class='panel warn'>
            <h3>Gap points / ギャップポイント（最大10項目）</h3>
            {self._point_list_html(gap_points, "No major gaps detected.", "action")}
          </section>
        </div>
        """

    def _jd_insight_result_html(self, analysis: dict) -> str:
        breakdown = analysis.get("jd_breakdown", {})
        insight = analysis.get("jd_insight", {})
        required = breakdown.get("required_skills", [])[:10]
        hidden = breakdown.get("hidden_expectations", [])[:10]
        risks = breakdown.get("risk_points", [])[:10]
        benchmark = insight.get("benchmark_signals", [])[:10]
        return f"""
        <div class='grid'>
          <section class='panel good'>
            <h3>Required skills / 必須スキル（最大10項目）</h3>
            {self._skill_list_html(required)}
          </section>
          <section class='panel info'>
            <h3>Hidden expectations / 隠れた期待事項（最大10項目）</h3>
            {self._simple_object_list_html(hidden, "expectation", "preparation_note")}
          </section>
          <section class='panel warn'>
            <h3>Risk points / リスクポイント（最大10項目）</h3>
            {self._simple_object_list_html(risks, "risk", "mitigation")}
          </section>
          <section class='panel info'>
            <h3>Benchmark company signals / ベンチマーク企業シグナル</h3>
            <p class='muted'>Target company: {escape(str(insight.get('target_company', 'Not provided')))}</p>
            {self._simple_object_list_html(benchmark, "signal", "evidence")}
          </section>
        </div>
        """

    def _mock_result_html(self, analysis: dict) -> str:
        mock = analysis.get("mock_interview", {})
        technical = mock.get("technical_questions", [])[:10]
        behavioral = mock.get("behavioral_questions", [])[:10]
        return f"""
        <div class='grid'>
          <section class='panel info'>
            <h3>Technical questions</h3>
            {self._question_list_html(technical)}
          </section>
          <section class='panel info'>
            <h3>Behavioral questions</h3>
            {self._question_list_html(behavioral)}
          </section>
        </div>
        """

    def _risk_result_html(self, analysis: dict) -> str:
        risk = analysis.get("japan_risk", {})
        score = risk.get("communication_risk_score", "N/A")
        detected = risk.get("detected_risks", [])[:10]
        suggestions = risk.get("improvement_suggestions", [])[:10]
        return f"""
        <div class='score-card warn-card'>
          <div class='score-number'>{escape(str(score))}/100</div>
          <div>
            <div class='score-label'>Communication risk score</div>
            <div class='muted'>Lower is better / スコアが低いほどリスクは小さい</div>
          </div>
        </div>
        <div class='grid'>
          <section class='panel warn'>
            <h3>Detected risks / 検出リスク（最大10項目）</h3>
            {self._simple_object_list_html(detected, "risk", "suggestion")}
          </section>
          <section class='panel good'>
            <h3>Improvement suggestions / 改善提案</h3>
            {self._string_list_html(suggestions)}
          </section>
        </div>
        """

    def _generic_result_html(self, analysis: dict) -> str:
        return f"<p>{escape(analysis.get('summary', 'Analysis complete.'))}</p>"

    def _point_list_html(self, points: list[dict], empty: str, detail_key: str) -> str:
        if not points:
            return f"<p class='muted'>{escape(empty)}</p>"
        items = []
        for point in points[:10]:
            title = escape(str(point.get("point", "N/A")))
            evidence = escape(str(point.get("evidence", "")))
            detail = escape(str(point.get(detail_key, "")))
            parts = [f"<strong>{title}</strong>"]
            if evidence:
                parts.append(f"<span>Evidence: {evidence}</span>")
            if detail:
                label = "Impact" if detail_key == "impact" else "Action"
                parts.append(f"<span>{label}: {detail}</span>")
            items.append("<li>" + "<br>".join(parts) + "</li>")
        return "<ol>" + "".join(items) + "</ol>"

    def _skill_list_html(self, skills: list[dict]) -> str:
        if not skills:
            return "<p class='muted'>None detected.</p>"
        items = []
        for skill in skills[:10]:
            items.append(
                "<li>"
                f"<strong>{escape(str(skill.get('name', 'N/A')))}</strong> "
                f"({escape(str(skill.get('category', 'unknown')))}, {escape(str(skill.get('importance', 'expected')))})<br>"
                f"<span>Evidence: {escape(str(skill.get('evidence', 'Detected.')))}</span>"
                "</li>"
            )
        return "<ol>" + "".join(items) + "</ol>"

    def _simple_object_list_html(self, items: list[dict], title_key: str, detail_key: str) -> str:
        if not items:
            return "<p class='muted'>None detected.</p>"
        rendered = []
        for item in items[:10]:
            rendered.append(
                "<li>"
                f"<strong>{escape(str(item.get(title_key, 'N/A')))}</strong><br>"
                f"<span>{escape(str(item.get(detail_key, '')))}</span>"
                "</li>"
            )
        return "<ol>" + "".join(rendered) + "</ol>"

    def _question_list_html(self, questions: list[dict]) -> str:
        if not questions:
            return "<p class='muted'>None generated.</p>"
        rendered = []
        for question in questions[:10]:
            rendered.append(
                "<li>"
                f"<strong>{escape(str(question.get('question', 'N/A')))}</strong><br>"
                f"<span>Follow-up: {escape(str(question.get('follow_up', '')))}</span>"
                "</li>"
            )
        return "<ol>" + "".join(rendered) + "</ol>"

    def _string_list_html(self, items: list[str]) -> str:
        if not items:
            return "<p class='muted'>None generated.</p>"
        return "<ol>" + "".join(f"<li>{escape(str(item))}</li>" for item in items[:10]) + "</ol>"

    def _reports_html(self) -> str:
        records = sorted(read_json_array(ANALYSIS_RUNS_FILE), key=lambda item: str(item.get("created_at", "")), reverse=True)[:100]
        if not records:
            return """
            <section class='sap-section'>
              <h2>Report History</h2>
              <div class='empty-state'>No InterviewReady analysis records yet.</div>
            </section>
            """
        rows = []
        for record in records:
            result = record.get("result_summary") if isinstance(record.get("result_summary"), dict) else {}
            score = result.get("fit_score") or result.get("match_score") or result.get("risk_score") or "-"
            rows.append(
                "<tr>"
                f"<td>{escape(str(record.get('created_at', '')))}</td>"
                f"<td><a href='/report?id={escape(str(record.get('analysis_id', '')))}'>{escape(str(record.get('analysis_id', '')))}</a></td>"
                f"<td>{escape(str(record.get('feature_label') or self._feature_title(str(record.get('feature', '')))))}</td>"
                f"<td>{escape(str(record.get('candidate_name') or '-'))}</td>"
                f"<td>{escape(str(record.get('client_company') or '-'))}</td>"
                f"<td>{escape(str(record.get('target_role') or '-'))}</td>"
                f"<td>{escape(str(score))}</td>"
                f"<td>{escape(str(record.get('created_by') or '-'))}</td>"
                f"<td>{escape(str(record.get('entity_code') or '-'))}</td>"
                "</tr>"
            )
        return f"""
        <section class='sap-section'>
          <div class='section-heading'><h2>Report History</h2><span class='status-badge'>Latest 100</span></div>
          <div class='wide-table-wrap'>
            <table class='wide-table'>
              <thead><tr><th>Created</th><th>ID</th><th>Feature</th><th>Candidate</th><th>Client</th><th>Role</th><th>Score/Risk</th><th>User</th><th>Entity</th></tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>
          </div>
        </section>
        """

    def _find_report_record(self, analysis_id: str) -> dict[str, Any] | None:
        analysis_id = analysis_id.strip()
        if not analysis_id:
            return None
        return next((item for item in read_json_array(ANALYSIS_RUNS_FILE) if item.get("analysis_id") == analysis_id), None)

    def _safe_report_content(self, record: dict[str, Any]) -> tuple[Path | None, str]:
        raw_path = str(record.get("report_path", "")).strip()
        if not raw_path:
            return None, "Report file is unavailable."
        report_path = Path(raw_path).resolve()
        try:
            report_path.relative_to(BASE_DIR)
            return report_path, report_path.read_text(encoding="utf-8")
        except (ValueError, OSError):
            return None, "Report file is unavailable."

    def _safe_report_filename(self, analysis_id: str) -> str:
        safe_id = "".join(char for char in analysis_id if char.isalnum() or char in "-_") or "report"
        return f"InterviewReady_{safe_id}.md"

    def _export_report(self, analysis_id: str, user: dict) -> None:
        analysis_id = analysis_id.strip()
        record = self._find_report_record(analysis_id)
        if not record:
            self.send_error(404, "The requested InterviewReady report was not found.")
            return
        report_path, content = self._safe_report_content(record)
        if not report_path:
            self.send_error(404, "Report file is unavailable.")
            return
        self._append_audit_log(
            record_id=analysis_id,
            action="export_report",
            user=user,
            before_value=None,
            after_value={
                "analysis_id": analysis_id,
                "report_relative_path": safe_relative_report_path(str(report_path)),
                "feature": record.get("feature", ""),
                "candidate_name": record.get("candidate_name", ""),
                "client_company": record.get("client_company", ""),
                "entity_code": record.get("entity_code", ""),
            },
        )
        self._send_download(content, self._safe_report_filename(analysis_id))

    def _report_detail_html(self, analysis_id: str, user: dict | None = None) -> str:
        analysis_id = analysis_id.strip()
        record = self._find_report_record(analysis_id)
        if not record:
            return "<section class='error sap-section'><h2>Report not found</h2><p>The requested InterviewReady report was not found.</p></section>"
        _, content = self._safe_report_content(record)
        download_link = ""
        if user and has_permission(user, "interview_ready.report.export"):
            download_link = f"<a class='secondary-link' href='/report/export?id={escape(analysis_id)}'>Download Markdown</a>"
        return f"""
        <section class='sap-section'>
          <div class='section-heading'><h2>Report {escape(analysis_id)}</h2><span class='status-badge'>{escape(str(record.get('status', 'completed')))}</span></div>
          <div class='sap-object-meta'>
            <span><strong>Feature</strong>{escape(str(record.get('feature_label', '')))}</span>
            <span><strong>Candidate</strong>{escape(str(record.get('candidate_name') or '-'))}</span>
            <span><strong>Client</strong>{escape(str(record.get('client_company') or '-'))}</span>
            <span><strong>Entity</strong>{escape(str(record.get('entity_code') or '-'))}</span>
            <span><strong>Created by</strong>{escape(str(record.get('created_by') or '-'))}</span>
          </div>
          <div class='action-bar'><a class='secondary-link' href='/reports'>Back to report history</a>{download_link}</div>
          <pre>{escape(content)}</pre>
        </section>
        """

    def _audit_html(self) -> str:
        logs = sorted(read_json_array(AUDIT_LOG_FILE), key=lambda item: str(item.get("timestamp", "")), reverse=True)[:100]
        if not logs:
            return "<section class='sap-section'><h2>Audit Trail</h2><div class='empty-state'>No InterviewReady audit records yet.</div></section>"
        rows = []
        for log in logs:
            rows.append(
                "<tr>"
                f"<td>{escape(str(log.get('timestamp', '')))}</td>"
                f"<td>{escape(str(log.get('record_id', '')))}</td>"
                f"<td>{escape(str(log.get('action', '')))}</td>"
                f"<td>{escape(str(log.get('user', '')))}</td>"
                f"<td><pre class='table-pre'>{escape(json.dumps(log.get('after_value'), ensure_ascii=False, indent=2))}</pre></td>"
                "</tr>"
            )
        return f"""
        <section class='sap-section'>
          <div class='section-heading'><h2>Audit Trail</h2><span class='status-badge'>Append-only</span></div>
          <div class='wide-table-wrap'>
            <table class='wide-table'>
              <thead><tr><th>Timestamp</th><th>Record</th><th>Action</th><th>User</th><th>After value</th></tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>
          </div>
        </section>
        """

    def _dashboard_cards_html(self) -> str:
        records = read_json_array(ANALYSIS_RUNS_FILE)
        today = datetime.now(timezone.utc).date().isoformat()
        today_count = sum(1 for record in records if str(record.get("created_at", "")).startswith(today))
        feature_counts = {feature: 0 for feature in FEATURE_PERMISSIONS}
        high_risk = 0
        for record in records:
            feature = str(record.get("feature", ""))
            if feature in feature_counts:
                feature_counts[feature] += 1
            result = record.get("result_summary") if isinstance(record.get("result_summary"), dict) else {}
            risk = result.get("risk_score")
            if isinstance(risk, (int, float)) and risk >= 60:
                high_risk += 1
        return f"""
        <section class='kpi-grid'>
          <div class='kpi-card'><span>Today</span><strong>{today_count}</strong><small>analysis runs</small></div>
          <div class='kpi-card'><span>JD Insight</span><strong>{feature_counts['jd-insight']}</strong><small>records</small></div>
          <div class='kpi-card'><span>Resume Match</span><strong>{feature_counts['resume-match']}</strong><small>records</small></div>
          <div class='kpi-card'><span>Japan Risk</span><strong>{high_risk}</strong><small>high risk signals</small></div>
        </section>
        """

    def _current_user_html(self, user: dict | None = None) -> str:
        if not user:
            return ""
        session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
        account = str(user.get("username") or user.get("email") or user.get("display_name") or "User")
        display_name = str(user.get("display_name") or account)
        entity = entity_context(user)
        entity_code = entity.get("entity_code", "")
        login_time = str(session.get("login_time_jst") or session.get("login_time") or "-")
        logout_url = f"{USER_ADMIN_BASE_URL}/logout?next={quote(APP_BASE_URL, safe='')}"
        return f"<div class='current-user-chip' title='Login: {escape(login_time)}'><strong>👤 {escape(account)}</strong><span>{escape(display_name)}{(' · ' + escape(entity_code)) if entity_code else ''}</span><small>Login: {escape(login_time)}</small><a href='{escape(logout_url)}'>Logout</a></div>"

    def _entity_panel_html(self, user: dict | None) -> str:
        entity = entity_context(user or {})
        return f"""
        <div class='sap-object-meta'>
          <span><strong>Entity</strong>{escape(entity.get('entity_code') or '-')}</span>
          <span><strong>Entity name</strong>{escape(entity.get('entity_name_en') or '-')}</span>
          <span><strong>Auth</strong>User_admin RBAC</span>
          <span><strong>Engine</strong>Local deterministic rules</span>
        </div>
        """

    def _page(self, result_html: str = "", active_feature: str = "jd-insight", user: dict | None = None) -> str:
        user_html = self._current_user_html(user)
        dashboard_cards = self._dashboard_cards_html()
        audit_link = "<a href='/audit'>Audit Trail</a>" if user and has_permission(user, "interview_ready.audit.view") else ""
        return f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>InterviewReady | TACAI Portal</title>
  <style>{self._style_css()}</style>
</head>
<body>
<div class='app-shell'>
  <aside class='sidebar'>
    <div class='sidebar-title'>TACAI</div>
    <p class='sidebar-subtitle'>InterviewReady / 面接準備 AI<br>Recruitment intelligence module</p>
    <nav>
      <a href='/dashboard'>Dashboard</a>
      <a href='#form-jd-insight' onclick="showFeature('jd-insight')">JD Insight</a>
      <a href='#form-resume-match' onclick="showFeature('resume-match')">Resume Match</a>
      <a href='#form-mock-interview' onclick="showFeature('mock-interview')">Mock Interview</a>
      <a href='#form-japan-risk' onclick="showFeature('japan-risk')">Japan Risk</a>
      <a href='/reports'>Report History</a>
      {audit_link}
      <a class='portal-link' href='{escape(PORTAL_BASE_URL)}' title='Return to TACAI Portal' aria-label='Return to TACAI Portal'><span aria-hidden='true'>⌂</span> Back to Portal</a>
    </nav>
  </aside>
  <main class='content'>
    <div class='topbar'>
      <div>
        <p class='eyebrow'>Recruitment Intelligence</p>
        <h1>InterviewReady</h1>
      </div>
      {user_html}
    </div>

    <section class='sap-page-header'>
      <div>
        <p class='eyebrow'>AI Recruitment Platform</p>
        <h2>Candidate interview readiness control</h2>
        <p class='subtitle'>JD analysis, resume matching, mock interview generation, and Japan-specific interview risk coaching under TACAI Portal governance.</p>
      </div>
      {self._entity_panel_html(user)}
    </section>

    {dashboard_cards}

    <nav class='feature-nav'>
      {self._nav_button('jd-insight', 'JD Insight', 'Analyze JD requirements, hidden expectations, benchmark company signals.', active_feature)}
      {self._nav_button('resume-match', 'Resume Match', 'Score resume/JD fit and show matching/gap points.', active_feature)}
      {self._nav_button('mock-interview', 'AI Mock Interview', 'Generate text-based technical and behavioral interview questions.', active_feature)}
      {self._nav_button('japan-risk', 'Japanese Interview Risks', 'Detect Japan-specific communication and cultural interview risks.', active_feature)}
    </nav>

    {self._jd_insight_form(active_feature)}
    {self._resume_match_form(active_feature)}
    {self._mock_interview_form(active_feature)}
    {self._japan_risk_form(active_feature)}

    {result_html}
  </main>
</div>
<script>
  function showFeature(feature) {{
    document.querySelectorAll('.feature-form').forEach(function(el) {{ el.classList.remove('active'); }});
    document.querySelectorAll('.feature-nav button').forEach(function(el) {{ el.classList.remove('active'); }});
    var form = document.getElementById('form-' + feature);
    var nav = document.getElementById('nav-' + feature);
    if (form) {{ form.classList.add('active'); }}
    if (nav) {{ nav.classList.add('active'); }}
  }}
</script>
</body>
</html>"""

    def _style_css(self) -> str:
        return """
:root { --bg:#f5f7fb; --panel:#fff; --text:#1f2937; --muted:#6b7280; --primary:#1d4ed8; --primary-dark:#1e40af; --border:#dbe3ef; --sidebar:#0f172a; --sidebar-muted:#cbd5e1; --success:#166534; --success-bg:#f0fdf4; --warn:#92400e; --warn-bg:#fffbeb; --danger:#991b1b; --danger-bg:#fef2f2; --shadow:0 18px 45px rgba(15,23,42,.10); }
* { box-sizing:border-box; }
body { margin:0; min-height:100vh; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
a { color:inherit; text-decoration:none; }
button,input,textarea { font:inherit; }
.app-shell { display:grid; min-height:100vh; grid-template-columns:280px 1fr; }
.sidebar { padding:28px; background:var(--sidebar); color:#fff; }
.sidebar-title { margin-bottom:8px; font-size:22px; font-weight:800; }
.sidebar-subtitle { margin:0 0 32px; color:var(--sidebar-muted); font-size:13px; line-height:1.6; }
.sidebar nav { display:grid; gap:8px; }
.sidebar a { padding:12px 14px; border-radius:12px; color:var(--sidebar-muted); }
.sidebar a:hover { background:rgba(255,255,255,.09); color:#fff; }
.sidebar a.portal-link { display:flex; align-items:center; gap:8px; margin-bottom:8px; color:#dbeafe; background:linear-gradient(180deg,rgba(248,251,255,.16) 0%,rgba(234,244,255,.10) 100%); border:1px solid rgba(156,199,242,.45); box-shadow:inset 0 1px 0 rgba(255,255,255,.12),0 1px 2px rgba(15,23,42,.16); }
.sidebar a.portal-link:hover { color:#fff; border-color:#93c5fd; background:rgba(255,255,255,.14); }
.content { padding:32px; }
.topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-bottom:24px; }
h1,h2,h3 { margin-top:0; }
.eyebrow,.status { margin:0 0 6px; color:var(--primary); font-size:12px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }
.subtitle,.muted,.hint { color:var(--muted); line-height:1.6; }
.current-user-chip { display:grid; gap:2px; min-width:210px; padding:10px 12px; border:1px solid var(--border); border-radius:14px; background:var(--panel); box-shadow:0 1px 2px rgba(15,23,42,.04); }
.current-user-chip strong { color:var(--text); font-size:14px; }
.current-user-chip span,.current-user-chip small,.current-user-chip a { color:var(--muted); font-size:12px; }
.sap-page-header,.sap-section,form,.result,.error { background:var(--panel); border:1px solid var(--border); border-radius:24px; padding:24px; margin:20px 0; box-shadow:0 8px 30px rgba(15,23,42,.05); }
.sap-object-meta { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
.sap-object-meta span { display:grid; gap:2px; min-width:145px; padding:10px 12px; border:1px solid var(--border); border-radius:14px; background:#f8fafc; color:var(--text); }
.sap-object-meta strong { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
.kpi-grid,.feature-nav,.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; margin:18px 0; }
.kpi-card,.feature-nav button,.panel { border:1px solid var(--border); border-radius:18px; background:var(--panel); padding:18px; box-shadow:0 8px 25px rgba(15,23,42,.04); }
.kpi-card span { color:var(--muted); font-size:13px; }
.kpi-card strong { display:block; margin:6px 0; font-size:32px; }
.kpi-card small { color:var(--muted); }
.feature-nav button { cursor:pointer; color:var(--text); text-align:left; }
.feature-nav button.active { border-color:rgba(29,78,216,.45); box-shadow:0 0 0 3px #dbeafe; }
.feature-nav strong { display:block; margin-bottom:6px; }
.feature-form { display:none; }
.feature-form.active { display:block; }
.form-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; }
.form-card { margin-top:18px; padding:18px; border:1px solid var(--border); border-radius:18px; background:#f8fafc; }
label { display:block; font-weight:700; margin-top:14px; }
input,textarea { width:100%; margin-top:6px; padding:11px 12px; border:1px solid #c8d1dc; border-radius:12px; background:#fff; color:var(--text); }
input[type=file] { padding:9px; }
input[type=checkbox] { width:auto; margin-right:8px; }
textarea { min-height:120px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; }
.file-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
.action-bar { display:flex; flex-wrap:wrap; gap:10px; margin-top:18px; }
.submit,.secondary-link { display:inline-block; border:0; border-radius:12px; padding:12px 18px; font-weight:800; cursor:pointer; }
.submit { background:var(--primary); color:#fff; }
.submit:hover { background:var(--primary-dark); }
.secondary-link { border:1px solid var(--border); background:#fff; color:var(--text); }
.message-strip { margin:12px 0; padding:12px 14px; border-radius:14px; font-weight:700; }
.success-strip { border:1px solid #bbf7d0; background:var(--success-bg); color:var(--success); }
.error-strip { border:1px solid #fecaca; background:var(--danger-bg); color:var(--danger); }
.status-badge { display:inline-flex; align-items:center; border:1px solid #bfdbfe; border-radius:999px; padding:5px 10px; background:#eff6ff; color:var(--primary-dark); font-size:12px; font-weight:800; }
.section-heading { display:flex; align-items:center; justify-content:space-between; gap:14px; }
pre { white-space:pre-wrap; background:#0b1220; color:#e5edf5; padding:16px; border-radius:12px; overflow:auto; }
.table-pre { max-width:360px; max-height:180px; margin:0; padding:10px; font-size:12px; }
details { margin-top:18px; }
summary { cursor:pointer; font-weight:800; color:var(--primary); }
.score-card { display:flex; gap:18px; align-items:center; background:#eef6ff; border:1px solid #b9d9f5; border-radius:18px; padding:18px; margin:16px 0; }
.score-number { font-size:2.4rem; font-weight:800; color:#154360; min-width:130px; }
.score-label { font-size:1.15rem; font-weight:800; }
.panel h3 { margin-top:0; }
.panel ol { padding-left:22px; }
.panel li { margin-bottom:12px; line-height:1.45; }
.good { background:#f1fbf5; border-color:#badbcc; }
.warn,.warn-card { background:#fff8ed; border-color:#f1d2a8; }
.info { background:#f4f8fb; border-color:#c9d9e8; }
.error { border-color:#fecaca; color:var(--danger); }
.empty-state { padding:22px; border:1px dashed var(--border); border-radius:18px; background:#f8fafc; color:var(--muted); }
.wide-table-wrap { overflow-x:auto; }
.wide-table { width:100%; min-width:900px; border-collapse:collapse; }
.wide-table th,.wide-table td { padding:10px 12px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }
.wide-table th { background:#f8fafc; color:#374151; font-size:12px; letter-spacing:.08em; text-transform:uppercase; }
@media (max-width:780px) { .app-shell { grid-template-columns:1fr; } .sidebar { padding:18px; } .sidebar nav { display:flex; gap:8px; overflow-x:auto; padding-bottom:4px; } .sidebar a { flex:0 0 auto; min-height:44px; white-space:nowrap; } .content { padding:18px 14px 36px; } .topbar { align-items:stretch; flex-direction:column; } .sap-page-header,.sap-section,form,.result,.error { padding:18px; border-radius:18px; } .feature-nav,.grid,.kpi-grid,.form-grid { grid-template-columns:1fr; } .action-bar,.action-bar button,.secondary-link { width:100%; } }
        """

    def _nav_button(self, feature: str, title: str, description: str, active_feature: str) -> str:
        active = " active" if feature == active_feature else ""
        return (
            f"<button id='nav-{feature}' type='button' class='{active.strip()}' onclick=\"showFeature('{feature}')\">"
            f"<strong>{escape(title)}</strong><span>{escape(description)}</span></button>"
        )

    def _file_group(self, prefix: str, label: str) -> str:
        inputs = "".join(
            f"<input type='file' name='{prefix}_{index}' accept='.txt,.md,.markdown,.pdf,.doc,.docx,.rtf'>"
            for index in range(1, 5)
        )
        return f"""
        <label>{escape(label)} files / ファイル（最大4件）</label>
        <div class='file-grid'>{inputs}</div>
        <p class='hint'>Upload up to 4 files, or paste text below. Uploaded files and pasted text will be combined.</p>
        """

    def _business_context_fields(self, include_candidate: bool = True, include_consent: bool = False) -> str:
        candidate = ""
        if include_candidate:
            candidate = """
            <label>Candidate name / 候補者名</label>
            <input name='candidate_name' placeholder='e.g. Yamada Taro'>
            """
        consent = ""
        if include_consent:
            consent = """
            <label class='checkbox-label'><input type='checkbox' name='candidate_consent' value='confirmed_internal_use'> I confirm this candidate data is used for internal recruitment support only.</label>
            <p class='hint'>候補者情報は社内採用支援目的のみで利用することを確認してください。</p>
            """
        return f"""
        <div class='form-card'>
          <h3>Business Context / 業務コンテキスト</h3>
          <div class='form-grid'>
            <div>{candidate}</div>
            <div><label>Client company / クライアント企業</label><input name='client_company' placeholder='e.g. Client A, Rakuten, Accenture'></div>
            <div><label>Target role / 対象ポジション</label><input name='target_role' placeholder='e.g. Backend Engineer'></div>
            <div><label>Department / 部門</label><input name='department' placeholder='Optional department or team owner'></div>
            <div><label>Team / チーム</label><input name='team' placeholder='Optional recruitment team'></div>
            <div><label>Source / ソース</label><input name='source' placeholder='e.g. Client A Backend Role'></div>
          </div>
          {consent}
        </div>
        """

    def _jd_insight_form(self, active_feature: str) -> str:
        active = " active" if active_feature == "jd-insight" else ""
        return f"""
        <form id='form-jd-insight' class='feature-form{active}' method='post' action='/analyze' enctype='multipart/form-data'>
          <input type='hidden' name='feature' value='jd-insight'>
          <div class='section-heading'><h2>JD Insight</h2><span class='status-badge'>interview_ready.jd_insight</span></div>
          <p class='muted'>Analyze concrete JD requirements, hidden expectations, interview focus areas, risk points, and benchmark company signals.</p>
          {self._business_context_fields(include_candidate=False, include_consent=False)}
          <div class='form-card'>
            <h3>JD Input / 求人票入力</h3>
            <label>Target company / 対象企業</label>
            <input name='target_company' placeholder='e.g. Rakuten, Mercari, Accenture, client company name'>
            {self._file_group('jd_file', 'JD / Job Description')}
            <label>JD text / JDテキスト</label>
            <textarea name='jd_text' placeholder='Paste JD text here'></textarea>
          </div>
          <div class='form-card'>
            <h3>Benchmark Company / ベンチマーク企業</h3>
            {self._file_group('benchmark_file', 'Benchmark company / ベンチマーク企業資料')}
            <label>Benchmark company notes / ベンチマーク企業メモ</label>
            <textarea name='benchmark_text' placeholder='Paste target/benchmark company profile, interview style notes, hiring-manager feedback, peer company JD, etc.'></textarea>
          </div>
          <div class='action-bar'><button class='submit' type='submit'>Run JD Insight</button><a class='secondary-link' href='/reports'>View History</a></div>
        </form>
        """

    def _resume_match_form(self, active_feature: str) -> str:
        active = " active" if active_feature == "resume-match" else ""
        return f"""
        <form id='form-resume-match' class='feature-form{active}' method='post' action='/analyze' enctype='multipart/form-data'>
          <input type='hidden' name='feature' value='resume-match'>
          <div class='section-heading'><h2>Resume Match</h2><span class='status-badge'>interview_ready.resume_match</span></div>
          <p class='muted'>Analyze resume/JD fit with a 100-point score, up to 10 matching points, and up to 10 gap points.</p>
          {self._business_context_fields(include_candidate=True, include_consent=True)}
          <div class='grid'>
            <div class='form-card'>
              <h3>JD Input / 求人票</h3>
              {self._file_group('jd_file', 'JD / Job Description')}
              <label>JD text / JDテキスト</label>
              <textarea name='jd_text' placeholder='Paste JD text here'></textarea>
            </div>
            <div class='form-card'>
              <h3>Candidate Input / 候補者情報</h3>
              {self._file_group('resume_file', 'Resume / Candidate profile')}
              <label>Resume text / 履歴書・職務経歴書テキスト</label>
              <textarea name='resume_text' placeholder='Paste resume or candidate profile here'></textarea>
            </div>
          </div>
          <div class='action-bar'><button class='submit' type='submit'>Run Resume Match</button><a class='secondary-link' href='/reports'>View History</a></div>
        </form>
        """

    def _mock_interview_form(self, active_feature: str) -> str:
        active = " active" if active_feature == "mock-interview" else ""
        return f"""
        <form id='form-mock-interview' class='feature-form{active}' method='post' action='/analyze' enctype='multipart/form-data'>
          <input type='hidden' name='feature' value='mock-interview'>
          <div class='section-heading'><h2>AI Mock Interview</h2><span class='status-badge'>interview_ready.mock_interview</span></div>
          <p class='muted'>Generate text-based technical, behavioral, follow-up questions, scoring rubric, and JP/EN answer guidance.</p>
          {self._business_context_fields(include_candidate=True, include_consent=True)}
          <div class='grid'>
            <div class='form-card'>
              <h3>JD Input / 求人票</h3>
              {self._file_group('jd_file', 'JD / Job Description')}
              <label>JD text / JDテキスト</label>
              <textarea name='jd_text' placeholder='Paste JD text here'></textarea>
            </div>
            <div class='form-card'>
              <h3>Candidate Profile / 候補者プロフィール</h3>
              {self._file_group('resume_file', 'Resume / Candidate profile')}
              <label>Candidate profile text / 候補者プロフィールテキスト</label>
              <textarea name='resume_text' placeholder='Paste resume or candidate profile here'></textarea>
            </div>
          </div>
          <div class='action-bar'><button class='submit' type='submit'>Generate Mock Interview</button><a class='secondary-link' href='/reports'>View History</a></div>
        </form>
        """

    def _japan_risk_form(self, active_feature: str) -> str:
        active = " active" if active_feature == "japan-risk" else ""
        return f"""
        <form id='form-japan-risk' class='feature-form{active}' method='post' action='/analyze' enctype='multipart/form-data'>
          <input type='hidden' name='feature' value='japan-risk'>
          <div class='section-heading'><h2>Japanese Interview Risk Analysis</h2><span class='status-badge'>interview_ready.japan_risk</span></div>
          <p class='muted'>Analyze communication risks, cultural mismatch, unclear logic, excessive humility, over-assertion, and Japan interview concerns.</p>
          {self._business_context_fields(include_candidate=True, include_consent=True)}
          <div class='grid'>
            <div class='form-card'>
              <h3>Candidate Answers / 候補者回答</h3>
              {self._file_group('candidate_file', 'Candidate answers / profile')}
              <label>Candidate answers/profile text / 候補者回答・プロフィールテキスト</label>
              <textarea name='candidate_text' placeholder='Paste mock interview answers, self-introduction, resume summary, or profile here'></textarea>
            </div>
            <div class='form-card'>
              <h3>Optional JD / 任意求人票</h3>
              {self._file_group('jd_file', 'Optional JD / Job Description')}
              <label>Optional JD text / 任意のJDテキスト</label>
              <textarea name='jd_text' placeholder='Paste JD text here if available'></textarea>
            </div>
          </div>
          <div class='action-bar'><button class='submit' type='submit'>Analyze Japanese Interview Risks</button><a class='secondary-link' href='/reports'>View History</a></div>
        </form>
        """

    def _send_download(self, content: str, filename: str) -> None:
        payload = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, text: str, status: int = 200) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html: str, status: int = 200) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = HTTPServer((host, port), InterviewReadyHandler)
    print(f"Interview Readiness Engine Web UI running at http://{host}:{port} (single-request mode)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Web UI")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run InterviewReady local Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
