# Interview Readiness Engine

Local-first MVP for IT headhunting interview preparation. It uses deterministic rules now, keeps the system runnable without API keys, and preserves seams for future LLM API integration.

## Run CLI locally

```bash
python3 -m app.cli analyze-jd --jd-file path/to/job_description.txt
python3 -m app.cli match-resume --jd-file path/to/jd.md --resume-file path/to/resume.txt --candidate-name "Candidate A"
python3 -m app.cli generate-interview --jd-file path/to/jd.txt --candidate-file path/to/resume.txt
python3 -m app.cli assess-risk --candidate-file path/to/answers.txt --jd-file path/to/jd.txt
python3 -m app.cli prep-report --jd-file path/to/jd.txt --resume-file path/to/resume.txt --candidate-name "Candidate A"
```

## Run local Web UI

```bash
python3 -m app.cli web --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000`. The Web UI is organized as four independent consultant functions:

1. **JD Insight** — analyze JD requirements, hidden expectations, interview focus areas, risk points, and benchmark company signals.
2. **Resume Match** — compare resume/profile against JD with a 100-point score plus up to 10 matching points and 10 gap points.
3. **AI Mock Interview** — generate technical and behavioral mock interview questions with rubrics and follow-ups.
4. **Japanese Interview Risks** — detect Japan-specific communication and cultural interview risks.

Each function has its own screen and supports up to 4 uploaded files per file input group, plus optional pasted text. Uploaded files and pasted text are combined for analysis.

## Input files

Supported directly with standard library:

- `.txt`
- `.md` / `.markdown`
- `.doc` / `.rtf` on macOS via `textutil`

Supported with optional document dependencies:

```bash
python3 -m pip install pypdf python-docx
```

- `.pdf`
- `.docx`

## Sample smoke-test inputs

Sample files are available under `samples/`:

```bash
python3 -m app.cli prep-report --jd-file samples/sample_jd.md --resume-file samples/sample_resume.md --candidate-name "Smoke Test Candidate"
```

## Outputs, history, audit, and memory

Reports are written to `outputs/interview_prep/`.

After TACAI Portal integration, Web UI analysis runs also write local governance records under `database/`:

- `database/analysis_runs.json` — analysis metadata, Entity/user context, candidate/client/role fields, consent status, input summary, result summary, and report path.
- `database/report_index.json` — lightweight report history index.
- `database/interview_ready_audit_logs.json` — append-only InterviewReady audit trail.

Memory is stored in:

- `memory/skill_profile.json`
- `memory/interview_patterns.json`
- `memory/candidate_history.json`

The current deployment assumption is internal consultant use, and real candidate information may be retained in local memory files. Candidate-specific Web UI analyses require confirmation that candidate data is used for internal recruitment support only.

## Implemented MVP modules

- JD Analyzer
- Resume Matcher with 100-point score, 1–10 matching points, and 1–10 gap points
- Text-based Mock Interview Engine
- Japan Interview Risk Engine
- Markdown report generation
- JSON memory updates after every CLI/Web interaction
- Local Web UI
