"""Command-line interface for the Interview Readiness Engine."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from core import (
    DocumentLoader,
    JDAnalyzer,
    JapanInterviewRiskEngine,
    MemoryStore,
    MockInterviewEngine,
    ReportWriter,
    ResumeMatcher,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="interview-ready", description="Interview Readiness Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_jd = subparsers.add_parser("analyze-jd", help="Analyze a job description and generate an interview prep report")
    _add_jd_input(analyze_jd)
    _add_common_metadata(analyze_jd)
    analyze_jd.set_defaults(func=handle_analyze_jd)

    match_resume = subparsers.add_parser("match-resume", help="Match a resume against a job description")
    _add_jd_input(match_resume)
    _add_resume_input(match_resume)
    _add_common_metadata(match_resume)
    match_resume.set_defaults(func=handle_match_resume)

    generate_interview = subparsers.add_parser("generate-interview", help="Generate a text-based mock interview")
    _add_jd_input(generate_interview)
    profile_input = generate_interview.add_mutually_exclusive_group(required=False)
    profile_input.add_argument("--candidate-file", type=Path, help="Candidate profile/resume file")
    profile_input.add_argument("--candidate-text", help="Candidate profile/resume text")
    _add_common_metadata(generate_interview)
    generate_interview.set_defaults(func=handle_generate_interview)

    assess_risk = subparsers.add_parser("assess-risk", help="Assess Japan-specific interview risks from candidate profile or answers")
    risk_input = assess_risk.add_mutually_exclusive_group(required=True)
    risk_input.add_argument("--candidate-file", type=Path, help="Candidate profile or answer file")
    risk_input.add_argument("--candidate-text", help="Candidate profile or answer text")
    _add_optional_jd_input(assess_risk)
    _add_common_metadata(assess_risk)
    assess_risk.set_defaults(func=handle_assess_risk)

    full_prep = subparsers.add_parser("prep-report", help="Generate combined JD, resume, mock interview, and Japan risk report")
    _add_jd_input(full_prep)
    _add_resume_input(full_prep)
    _add_common_metadata(full_prep)
    full_prep.set_defaults(func=handle_prep_report)

    web = subparsers.add_parser("web", help="Run the local Web UI")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    web.set_defaults(func=handle_web)

    return parser


def _add_common_metadata(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate-name", help="Optional candidate name for memory/report tagging")
    parser.add_argument("--source", default="manual-input", help="Source label for this analysis")


def _add_jd_input(parser: argparse.ArgumentParser) -> None:
    jd_input = parser.add_mutually_exclusive_group(required=True)
    jd_input.add_argument("--jd-file", type=Path, help="Path to JD file: .txt, .md, .pdf, .docx, .doc, .rtf")
    jd_input.add_argument("--jd-text", help="Job description text provided directly on the command line")


def _add_optional_jd_input(parser: argparse.ArgumentParser) -> None:
    jd_input = parser.add_mutually_exclusive_group(required=False)
    jd_input.add_argument("--jd-file", type=Path, help="Optional JD file: .txt, .md, .pdf, .docx, .doc, .rtf")
    jd_input.add_argument("--jd-text", help="Optional job description text")


def _add_resume_input(parser: argparse.ArgumentParser) -> None:
    resume_input = parser.add_mutually_exclusive_group(required=True)
    resume_input.add_argument("--resume-file", type=Path, help="Path to resume file: .txt, .md, .pdf, .docx, .doc, .rtf")
    resume_input.add_argument("--resume-text", help="Resume text provided directly on the command line")


def handle_analyze_jd(args: argparse.Namespace) -> int:
    jd_text = _resolve_text(args.jd_text, args.jd_file)
    analysis = JDAnalyzer().analyze(jd_text, source=args.source)
    return _persist_and_print(analysis, args.candidate_name, args.source, "jd_analysis", "JD analysis complete")


def handle_match_resume(args: argparse.Namespace) -> int:
    jd_text = _resolve_text(args.jd_text, args.jd_file)
    resume_text = _resolve_text(args.resume_text, args.resume_file)
    analysis = ResumeMatcher().match(resume_text, jd_text, candidate_name=args.candidate_name, source=args.source)
    return _persist_and_print(analysis, args.candidate_name, args.source, "resume_match", "Resume match complete")


def handle_generate_interview(args: argparse.Namespace) -> int:
    jd_text = _resolve_text(args.jd_text, args.jd_file)
    candidate_text = _resolve_text(args.candidate_text, args.candidate_file, required=False)
    analysis = MockInterviewEngine().generate(jd_text, candidate_text, candidate_name=args.candidate_name, source=args.source)
    return _persist_and_print(analysis, args.candidate_name, args.source, "mock_interview", "Mock interview generated")


def handle_assess_risk(args: argparse.Namespace) -> int:
    candidate_text = _resolve_text(args.candidate_text, args.candidate_file)
    jd_text = _resolve_text(args.jd_text, args.jd_file, required=False)
    analysis = JapanInterviewRiskEngine().analyze(candidate_text, jd_text, candidate_name=args.candidate_name, source=args.source)
    return _persist_and_print(analysis, args.candidate_name, args.source, "japan_risk", "Japan interview risk assessment complete")


def handle_prep_report(args: argparse.Namespace) -> int:
    jd_text = _resolve_text(args.jd_text, args.jd_file)
    resume_text = _resolve_text(args.resume_text, args.resume_file)
    analysis = ResumeMatcher().match(resume_text, jd_text, candidate_name=args.candidate_name, source=args.source)
    mock = MockInterviewEngine().generate(jd_text, resume_text, candidate_name=args.candidate_name, source=args.source)
    risk = JapanInterviewRiskEngine().analyze(resume_text, jd_text, candidate_name=args.candidate_name, source=args.source)

    analysis["mock_interview"] = mock.get("mock_interview")
    analysis["interview_questions"] = mock.get("interview_questions", analysis.get("interview_questions", {}))
    analysis["japan_risk"] = risk.get("japan_risk")
    analysis["jd_breakdown"]["risk_points"].extend(risk.get("jd_breakdown", {}).get("risk_points", []))
    analysis["weaknesses"].extend(risk.get("weaknesses", []))
    analysis["strengths"].extend(risk.get("strengths", []))
    analysis["summary"] = f"Full prep report for {args.candidate_name or 'candidate'}: fit score {analysis['candidate_fit_score']}/100; Japan risk {risk['japan_risk']['communication_risk_score']}/100."
    return _persist_and_print(analysis, args.candidate_name, args.source, "full_prep", "Full interview prep report complete")


def handle_web(args: argparse.Namespace) -> int:
    from app.web import run

    run(host=args.host, port=args.port)
    return 0


def _resolve_text(text: str | None, path: Path | None, required: bool = True) -> str:
    if text:
        return text
    if path:
        return DocumentLoader().load(path)
    if required:
        raise ValueError("Text or file input is required.")
    return ""


def _persist_and_print(
    analysis: dict,
    candidate_name: str | None,
    source: str,
    interaction_type: str,
    done_message: str,
) -> int:
    MemoryStore().record_analysis(analysis, candidate_name=candidate_name, source=source, interaction_type=interaction_type)
    report_path = ReportWriter().write_interview_prep_report(analysis, candidate_name=candidate_name, source=source)
    print(done_message)
    print(f"Report: {report_path}")
    print(f"Summary: {analysis['summary']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 - CLI should surface concise operational failures.
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
