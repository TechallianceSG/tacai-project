# CLAUDE.md


Project Name: InterviewReady

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.


This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product decisions

Confirmed MVP direction:

- Use a local deterministic rules engine first; do not require LLM API keys yet.
- Keep CLI runnable locally and provide a local Web UI for internal consultant use.
- Support common recruitment files: `.txt`, `.md`, `.pdf`, `.docx`, `.doc`, `.rtf`.
- Current memory policy allows retaining real candidate information because the MVP is for internal use.
- Add LLM APIs later behind abstractions; do not make current engines depend on a specific provider.

## Commands

Run from [InterviewReady/](./):

```bash
python3 -m app.cli analyze-jd --jd-file path/to/job_description.txt
python3 -m app.cli analyze-jd --jd-text "Senior Python/AWS engineer..." --candidate-name "Candidate A"
python3 -m app.cli match-resume --jd-file path/to/jd.md --resume-file path/to/resume.txt --candidate-name "Candidate A"
python3 -m app.cli generate-interview --jd-file path/to/jd.txt --candidate-file path/to/resume.txt
python3 -m app.cli assess-risk --candidate-file path/to/answers.txt --jd-file path/to/jd.txt
python3 -m app.cli prep-report --jd-file path/to/jd.txt --resume-file path/to/resume.txt --candidate-name "Candidate A"
python3 -m app.cli web --host 127.0.0.1 --port 8000
```

Development checks:

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_jd_analyzer
python3 -m unittest tests.test_jd_analyzer.TestJDAnalyzer.test_jd_analyzer_extracts_core_outputs
```

Optional document parsing dependencies:

```bash
python3 -m pip install pypdf python-docx
```

`.txt` and `.md` work without dependencies. `.pdf` needs `pypdf`, `.docx` needs `python-docx`, and `.doc`/`.rtf` use macOS `textutil` when available.

## Architecture

This is a local-first recruitment intelligence engine for IT headhunting. Current engines are deterministic and dependency-light so the system can run locally without API keys.

- [app/cli.py](app/cli.py) is the operational CLI entry point. It parses commands, loads documents, invokes core engines, writes memory, and generates reports.
- [app/web.py](app/web.py) is the local Web UI. It intentionally uses Python standard library HTTP server and presents four TACAI Portal-controlled consultant functions: JD Insight, Resume Match, AI Mock Interview, and Japanese Interview Risks. Each function supports paste-in text plus up to 4 uploaded files per input group and calls the same core engines as CLI. The Web UI uses User_admin session/permission/Entity control, TACAI/SAP-style shell components, report history, and append-only audit logging.
- [core/document_loader.py](core/document_loader.py) centralizes file text extraction for JD/resume/candidate inputs.
- [core/llm_client.py](core/llm_client.py) is the future provider seam. Current engines should continue to work with `LocalRulesOnlyLLMClient`; add real providers later without making API keys mandatory.
- [core/jd_analyzer.py](core/jd_analyzer.py) converts JD text into required skills, hidden expectations, interview focus areas, risk points, interview questions, and JP/EN answer guidance.
- [core/resume_matcher.py](core/resume_matcher.py) compares resume text against JD analysis, computes transparent 0–100 fit scores, and produces consultant-friendly 1–10 matching points plus 1–10 gap points with evidence/action guidance.
- [core/mock_interview_engine.py](core/mock_interview_engine.py) generates text-based technical and behavioral interviews with rubrics and follow-ups.
- [core/japan_risk_engine.py](core/japan_risk_engine.py) detects Japan-market interview communication risks such as unclear logic, excessive humility, over-assertion, missing ownership, and weak client-facing evidence.
- [core/memory_store.py](core/memory_store.py) owns persistent JSON learning. Every CLI/Web analysis should call it so [memory/skill_profile.json](memory/skill_profile.json), [memory/interview_patterns.json](memory/interview_patterns.json), and [memory/candidate_history.json](memory/candidate_history.json) stay current.
- [core/report_writer.py](core/report_writer.py) renders reports into [outputs/interview_prep/](outputs/interview_prep/) using the required sections: Summary, JD breakdown, Candidate fit score, Strengths, Weaknesses, Interview questions, and Suggested answers in EN/JP.
- [database/analysis_runs.json](database/analysis_runs.json), [database/report_index.json](database/report_index.json), and [database/interview_ready_audit_logs.json](database/interview_ready_audit_logs.json) store Web UI governance records for Portal-integrated report history and audit.
- [knowledge_base/skill_taxonomy.json](knowledge_base/skill_taxonomy.json) and [knowledge_base/japan_risk_taxonomy.json](knowledge_base/japan_risk_taxonomy.json) are editable rule knowledge bases.

Preserve the flow for new capabilities: document/input loading -> core engine -> MemoryStore update -> ReportWriter output. Future LLM integration should be additive, with local rules remaining as fallback.


# MEMORY MANAGEMENT

The project must maintain a small active context window.
Memory Structure
1. memory/
2. archive/

File Size Policy
Green Zone
0KB - 30KB
Normal operation.
Yellow Zone
30KB - 100KB
Monitor growth and prepare for summarization.
Red Zone
Over 100KB
Archive and compress immediately.
Archive Rules
When any file under `/memory` exceeds 100KB:
Create archive copy.
Generate concise summary.
Replace active memory file with summary.
Never delete archive records.
Archive Naming Convention
1. archive/<module>/<filename>_YYYY_MM.md

Example:
1. archive/project_status/project_status_2026_06.md
2. archive/recruitment/recruitment_2026_06.md
3. archive/payroll/payroll_2026_06.md

Loading Rules
Do not automatically load archive files.
Only load:
CLAUDE.md
memory/project_status.md
related module memory file
Archive files should only be opened when explicitly requested.
Memory Update Rules
After every major task:
Update project_status.md
Update related module memory
Update decisions.md (if architectural decisions were made)
Update changelog.md (if system changes occurred)
Historical Preservation Policy
Never delete historical records.
When summarizing:
Preserve key decisions
Preserve business rules
Preserve architecture decisions
Preserve implementation status
Preserve unresolved issues
Archive files are the source of truth for historical details.


## Startup Loading Priority

On project startup, load files in this order:

1. CLAUDE.md
2. memory/project_status.md
3. memory/current_tasks.md
4. Related module memory

Do not load archive files automatically.


# Audit Rules

All modules must implement audit logging.

Required fields:

- module
- record_id
- action
- user
- timestamp
- before_value
- after_value

Audit logs must never be deleted.

Audit logs are read-only.

Future centralized audit viewer may be added.


