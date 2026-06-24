# InterviewReady Portal Integration Plan

Last updated: 2026-06-21

## 1. Purpose

InterviewReady will become a TACAI Portal-connected recruitment intelligence module for Japan-focused HR, recruitment agency, RPO, haken, SES, and client-site interview preparation workflows.

The module must keep its local-first deterministic rules engine while adopting TACAI platform controls:

- Unified login through `TACAI-Core/User_admin`.
- Permission-based Portal visibility and direct-route access control.
- Entity context from User_admin session only.
- Master Data alignment for Entity, Department, and Team context.
- TACAI/TAC suite UI vocabulary aligned with Portal, Timesheet, and SAP/Fiori-style business screens.
- Append-only auditability for sensitive candidate/JD analysis activities.

## 2. Approved Portal Placement

InterviewReady should be displayed in TACAI Portal between Expense and Master Data Management.

Approved navigation order:

1. Dashboard
2. Employee Mgmt
3. Timesheet
4. Payroll
5. Expense
6. InterviewReady
7. Master Data Management
8. User Management

Rationale:

- InterviewReady is a business module supporting recruitment operations, not a platform administration module.
- It is operationally closer to Employee Mgmt, Timesheet, Payroll, and Expense than to Master Data/User Management.
- Placing it before Master Data keeps core governance modules grouped at the end.

## 3. Business Scope

### 3.1 Current InterviewReady functions

Current Web UI functions remain valid and become Portal-controlled functions:

1. JD Insight — analyze JD requirements, hidden expectations, interview focus areas, risk points, and benchmark company signals.
2. Resume Match — compare resume/profile against JD with a 100-point score, matching points, and gap points.
3. AI Mock Interview — generate technical and behavioral interview questions with rubrics and follow-ups.
4. Japanese Interview Risks — detect Japan-specific communication and cultural interview risks.

### 3.2 Japan HR / recruitment use cases

InterviewReady should support:

- Recruitment agency candidate recommendation preparation.
- RPO candidate interview coaching.
- Haken / SES / client-site interview readiness.
- Client-specific JD and interview-style intelligence.
- Japanese communication risk coaching, including 報連相, ownership clarity, excessive humility, over-assertion, logical explanation, and client-facing stability.

## 4. Target Architecture

```text
TACAI Portal 8005
  ├── User_admin 8006
  │     ├── login / logout
  │     ├── session validation
  │     ├── RBAC permissions
  │     └── selected Entity context
  ├── Master Data 8007
  │     ├── Entity
  │     ├── Department
  │     └── Team
  ├── EmployeeAdmin 8004
  ├── Timesheet 8002
  ├── Payroll 8001
  ├── Expense 8003
  └── InterviewReady 8000
        ├── JD Insight
        ├── Resume Match
        ├── Mock Interview
        ├── Japan Interview Risk
        ├── Report History
        └── Audit Trail
```

## 5. Authentication and Authorization

InterviewReady must follow the TACAI module integration contract:

1. Validate `tacai_session_id` for every protected page.
2. Resolve the current user only through User_admin `/api/validate-session`.
3. Require `interview_ready.access` for module access.
4. Require feature-level permissions before running each analysis function.
5. Treat `user.entity` from User_admin as the only trusted Entity context.
6. Never accept `entity_id` or `entity_code` from query strings/forms as an authorization source.
7. Never implement a separate InterviewReady login/password system.
8. Use current User_admin user identity and Entity context in audit records.

## 6. Permission Design

### 6.1 Required permission keys

```text
interview_ready.access
interview_ready.jd_insight
interview_ready.resume_match
interview_ready.mock_interview
interview_ready.japan_risk
interview_ready.report.view
interview_ready.report.export
interview_ready.audit.view
```

### 6.2 Role mapping direction

| Role | Access direction |
|---|---|
| System Admin | All InterviewReady permissions. |
| HR Manager | All business analysis permissions and report viewing/export. |
| Finance | No InterviewReady access by default. |
| Manager | No default access in V1; may receive report view later if business approved. |
| Employee | No default access in V1. |

Future role recommendation:

- Add a dedicated `recruiter` or `recruitment_consultant` role when recruitment operations grow beyond HR Manager.

## 7. Portal Configuration Changes

### 7.1 `modules.json`

Add module metadata after Expense and before Master Data Management:

```json
{
  "module_key": "interview_ready",
  "label": "InterviewReady",
  "labels": {
    "ja": "面接準備 AI",
    "zh": "面试准备 AI",
    "en": "InterviewReady"
  },
  "description": "JD analysis, resume matching, mock interview, and Japan interview risk review",
  "descriptions": {
    "ja": "求人票分析、職務経歴書マッチング、模擬面接、面接リスク確認",
    "zh": "JD 分析、简历匹配、模拟面试和日本面试风险检查",
    "en": "JD analysis, resume matching, mock interview, and Japan interview risk review"
  },
  "url": "http://127.0.0.1:8000/",
  "status": "Connected module",
  "required_permission": "interview_ready.access",
  "enabled": true
}
```

### 7.2 `services.json`

Add InterviewReady service reference:

```json
"interview_ready": {
  "name": "InterviewReady",
  "url": "http://127.0.0.1:8000/",
  "health": "http://127.0.0.1:8000/health",
  "required_permission": "interview_ready.access"
}
```

## 8. UI / UX Alignment Plan

InterviewReady UI should align with TACAI Portal and TAC-timesheet while keeping the current Python standard-library implementation.

### 8.1 Standard layout vocabulary

Use TACAI/SAP-like components:

- `app-shell`
- `sidebar`
- `topbar`
- `current-user-chip`
- `sap-page-header`
- `sap-object-meta`
- `message-strip`
- `status-badge`
- `panel`
- `card`
- `wide-table`
- `primary-button`
- `secondary-button`

### 8.2 Recommended pages

1. InterviewReady Dashboard
   - Today’s analysis count.
   - Recent reports.
   - Quick actions for four functions.

2. JD Insight
   - Business context card.
   - JD upload/paste card.
   - Benchmark company card.
   - Result object page sections.

3. Resume Match
   - Candidate/JD business context.
   - Upload/paste inputs.
   - Score card, matching points, gap points.

4. Mock Interview
   - JD/candidate inputs.
   - Technical and behavioral interview output panels.

5. Japan Interview Risk
   - Candidate answer/profile inputs.
   - Risk score and Japan communication coaching output.

6. Report History
   - Date, candidate, client, role, feature, score/risk, user, entity, report link.

## 9. Input Standardization

Every analysis form should eventually include:

- Entity: read-only from User_admin session.
- Department / Team: from Master Data or short-term optional text fallback.
- Recruiter: read-only from current user.
- Client Company: short-term text, future client master reference.
- Target Role / JD Title.
- Candidate Name when candidate-specific.
- Source / Channel.
- Candidate consent confirmation for candidate data use.
- File upload and paste text inputs.

## 10. Master Data Strategy

### 10.1 V1 reference behavior

V1 must use User_admin session Entity as the authoritative Entity context.

Recommended V1 analysis metadata:

```json
{
  "analysis_id": "IR-000001",
  "entity_id": "ENT-0001",
  "department_id": "DEP-0001",
  "team_id": "TEAM-0001",
  "user_id": "USR-0001",
  "feature": "resume_match",
  "candidate_name": "Yamada Taro",
  "client_company": "Client A",
  "target_role": "Backend Engineer",
  "source": "Client A Backend Role",
  "created_at": "2026-06-21T09:00:00+09:00",
  "status": "completed"
}
```

### 10.2 Future recruitment master data

Do not overload the existing Organization Master Data too early. Future master/reference data should include:

- Client Company Master.
- Job Order / JD Master.
- Candidate Master.
- Skill Taxonomy Master.
- Interview Stage Master.
- Japan Interview Risk Taxonomy.

## 11. Compliance and HR Controls

InterviewReady processes sensitive candidate and client information. It should apply Japan HR and APPI-aware controls:

1. Record who ran the analysis and when.
2. Record which Entity the analysis belongs to.
3. Require permission for module and feature access.
4. Keep JD/client notes confidential within TACAI authorization controls.
5. Add candidate consent confirmation before storing candidate-specific analysis metadata.
6. Keep current local deterministic engine as the default to avoid external data transfer.
7. Before future external LLM use, add explicit data-processing consent, masking, provider configuration, and audit controls.

## 12. Audit Design

Every state-changing or sensitive analysis action should append an audit record using TACAI audit fields:

```json
{
  "module": "interview_ready",
  "record_id": "IR-000001",
  "action": "run_resume_match",
  "user": "hr@example.com",
  "timestamp": "2026-06-21T09:00:00+09:00",
  "before_value": null,
  "after_value": {
    "feature": "resume_match",
    "candidate_name": "Yamada Taro",
    "entity_id": "ENT-0001"
  }
}
```

Audit logs must be append-only and must never be deleted.

## 13. Implementation Milestones

### Milestone 1 — Portal registration

- Add InterviewReady module after Expense and before Master Data Management.
- Add service health reference.
- Add Portal LAN/mobile conversion support for port 8000.
- Confirm authorized users can see the module card.

### Milestone 2 — User_admin permission integration

- Add InterviewReady permission keys to permission catalog and seed definitions.
- Grant all InterviewReady permissions to System Admin and HR Manager.
- Keep Finance, Manager, and Employee without InterviewReady access by default.

### Milestone 3 — InterviewReady route hardening

- Add `/health` public route.
- Require `interview_ready.access` for all business pages.
- Require feature-level permissions before POST analysis execution.
- Reject sessions missing Entity context.
- Keep login redirect and logout behavior aligned with other modules.

### Milestone 4 — UI first pass

- Introduce TACAI Portal/Timesheet visual vocabulary.
- Convert current feature buttons/forms into object-page/card sections.
- Add SAP/Fiori-like success/error message strips.
- Preserve current analysis engine behavior.

### Milestone 5 — Report history and audit

- Add `database/analysis_runs.json`.
- Add `database/interview_ready_audit_logs.json`.
- Add report index and report history page.
- Record candidate/JD context and Entity/user metadata.

### Milestone 6 — Recruitment platform expansion

- Add client/job/candidate reference model.
- Add richer Japan HR interview coaching outputs.
- Add recruiter call scripts and pre-interview checklists.
- Add future controlled LLM provider integration only after approval.

## 14. Verification Checklist

1. `python3 -m py_compile app/web.py` passes for InterviewReady.
2. `python3 -m py_compile backend/app.py` passes for Portal.
3. `python3 -m py_compile backend/app.py` passes for User_admin.
4. Portal `/health` returns OK.
5. InterviewReady `/health` returns OK without login.
6. User_admin login creates `tacai_session_id`.
7. Portal dashboard shows InterviewReady between Expense and Master Data for authorized users.
8. Direct InterviewReady access redirects unauthenticated users to User_admin login.
9. Users without `interview_ready.access` cannot open InterviewReady.
10. Feature-level permissions are checked before analysis execution.
11. LAN/mobile mode works with `TACAI_PUBLIC_HOST` and port 8000.

## 15. Current Execution Status

### Completed on 2026-06-21 — Phase 1 platform registration

1. Formal documentation in this file.
2. Portal module/service registration.
3. User_admin permission catalog/data/source updates.
4. InterviewReady module and feature permission hardening.
5. Syntax/config verification.

### Completed on 2026-06-21 — Phase 2 UI first pass

1. Reworked InterviewReady Web UI into a TACAI Portal-like app shell with sidebar, topbar, current-user chip, SAP/Fiori-like page header, KPI cards, feature cards, and responsive layout.
2. Standardized form layout into business context cards, document input cards, action bars, status badges, message strips, panels, score cards, and wide tables.
3. Preserved the existing deterministic local engines and current four business functions.
4. Added Portal return link and Report History navigation.

### Completed on 2026-06-21 — Phase 3 report history and audit baseline

1. Added local JSON storage files under `database/`:
   - `analysis_runs.json`
   - `interview_ready_audit_logs.json`
   - `report_index.json`
2. Added analysis metadata capture for Entity, user, department/team text, client company, target role, candidate name, source, consent status, input summary, result summary, report path, and completion status.
3. Added candidate consent confirmation requirement for candidate-specific features: Resume Match, Mock Interview, and Japan Interview Risk.
4. Added `/reports` report history page and `/report?id=IR-xxxxxx` report detail page protected by `interview_ready.report.view`.
5. Added `/audit` append-only audit viewer protected by `interview_ready.audit.view`.
6. Added unit coverage for analysis-run history/index writing.

### Completed on 2026-06-21 — Phase 4 report export/download controls

1. Added `/report/export?id=IR-xxxxxx` Markdown report download protected by `interview_ready.report.export`.
2. Added report-detail download control that is only shown to users with export permission.
3. Added safe report lookup/path handling so downloads resolve from analysis records and remain inside the InterviewReady project directory.
4. Added successful export audit records with `export_report` action and report metadata.
5. Added unit coverage for export button visibility and report path safety.

## 16. Next Execution Scope

Recommended next phases:

1. Browser-side visual review for spacing, mobile layout, sidebar usability, form balance, report detail download control placement, and result readability.
2. Add stricter department/team dropdown integration from Master Data once Master Data exposes a stable read API for InterviewReady.
3. Add richer Japan HR coaching output: recruiter call script, candidate pre-interview checklist, Haken/client-site readiness notes, and client-style coaching recommendation.
