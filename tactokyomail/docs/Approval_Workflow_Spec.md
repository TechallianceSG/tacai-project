# Approval Workflow Specification — TAC Tokyo Mail

## 1. Overview

This document specifies the approval workflow for TAC Tokyo Mail email drafts. The workflow supports **snapshot-based undo** for pure approval steps (no data mutation), with an **append-only immutable audit trail**.

## 2. States

| State | Code | Description |
|---|---|---|
| Draft | `Draft` | Initial editable state. Item is not yet submitted for review. |
| Submitted | `Submitted` | Submitted for HR review. Awaiting HR confirmation. |
| HR Reviewed | `HR_Reviewed` | HR has confirmed/reviewed the draft. Awaiting manager approval. |
| Manager Approved | `Manager_Approved` | Manager/supervisor has approved. Awaiting final approval. |
| Final Approved | `Final_Approved` | Final approval granted. Email is ready to be sent. |
| Rejected | `Rejected` | Rejected at some stage. Can be resubmitted to Draft. |

## 3. State Transition Map

```
Draft ──submit──▶ Submitted ──hr_review──▶ HR_Reviewed ──manager_approve──▶ Manager_Approved ──final_approve──▶ Final_Approved
  ▲                    │    ◄──undo───         │           ◄──undo───            │                  ◄──undo───           │
  │                    │                       │                                │                                      │
  └──resubmit─── Rejected ◄──reject────────────┼────────────────────────────────┘                                      │
                                               │                                                                       │
                                               └───────────────────reject──────────────────────────────────────────────┘
```

### Transition Table

| From | Action | To | Undoable | Notes |
|---|---|---|---|---|
| `Draft` | `submit` | `Submitted` | Yes | Snapshot saved |
| `Submitted` | `hr_review` | `HR_Reviewed` | Yes | HR confirms, no data change |
| `HR_Reviewed` | `manager_approve` | `Manager_Approved` | Yes | Manager approves, no data change |
| `Manager_Approved` | `final_approve` | `Final_Approved` | Yes | Final approval, no data change |
| `Submitted` | `reject` | `Rejected` | No | Requires reject reason |
| `HR_Reviewed` | `reject` | `Rejected` | No | Requires reject reason |
| `Manager_Approved` | `reject` | `Rejected` | No | Requires reject reason |
| `Rejected` | `resubmit` | `Draft` | No | Clears rejection fields |
| `Submitted` | `undo` | `Draft` | N/A | Undo of submit |
| `HR_Reviewed` | `undo` | `Submitted` | N/A | Undo of hr_review |
| `Manager_Approved` | `undo` | `HR_Reviewed` | N/A | Undo of manager_approve |
| `Final_Approved` | `undo` | `Manager_Approved` | N/A | Undo of final_approve |

## 4. Undo Mechanism

### 4.1 Principle

Pure approval steps (HR review, manager approve, final approve) do **not** mutate business data — they only update the approval status and actor timestamps. These steps are therefore **safe to undo**.

Steps that DO mutate data (e.g., `send_email` which actually dispatches the email) would be marked `undoable: false` in the transition map and would show no undo button.

### 4.2 Snapshot-Based Restore

1. When a forward transition executes (e.g., `hr_review`), the record's **complete state before the transition** is saved as `before_value` in the audit log.
2. The audit entry is marked `undoable: true`.
3. When `undo` is invoked, the system:
   a. Finds the most recent `undoable: true` audit entry for this record
   b. Restores the record's status and reviewer/approver fields from that snapshot
   c. Creates a new audit entry with `action: "undo"` referencing the undone entry
4. The original audit entry is **never deleted** — it remains in the audit trail.

### 4.3 Undo Eligibility

Only states in `UNDOABLE_STATES = {"Submitted", "HR_Reviewed", "Manager_Approved", "Final_Approved"}` show the undo button. `Draft` and `Rejected` have no undo action.

## 5. Audit Logging

### 5.1 Required Fields

Every audit entry MUST contain:

| Field | Type | Description |
|---|---|---|
| `audit_id` | string | Unique sequential ID (e.g., `AUD-0001`) |
| `module` | string | Module name (`approval.email_draft`) |
| `record_id` | string | Approval item ID (e.g., `EML-0001`) |
| `action` | string | Action key (`create`, `submit`, `hr_review`, `undo`, etc.) |
| `user` | string | Actor performing the action |
| `timestamp` | string | ISO 8601 in JST |
| `timestamp_utc` | string | ISO 8601 in UTC |
| `before_value` | object | Record state before the action |
| `after_value` | object | Record state after the action |
| `undoable` | boolean | Whether this action can be undone |
| `undo_target_audit_id` | string | (undo only) ID of the audit entry being undone |

### 5.2 Immutability

Audit logs are **append-only** and must **never be deleted or modified**. The undo action creates a new entry — it does not remove or alter previous entries.

### 5.3 Undo Audit Entry Example

```json
{
  "audit_id": "AUD-0005",
  "module": "approval.email_draft",
  "record_id": "EML-0001",
  "action": "undo",
  "user": "hr_admin@tactokyo.com",
  "timestamp": "2026-06-25T14:35:00+09:00",
  "timestamp_utc": "2026-06-25T05:35:00+00:00",
  "before_value": { "status": "HR_Reviewed", "reviewed_by": "hr_admin", ... },
  "after_value": { "status": "Submitted", "reviewed_by": "", ... },
  "undoable": false,
  "undo_target_audit_id": "AUD-0004",
  "context": {
    "comment": "Incorrect review — undoing",
    "undone_action": "hr_review"
  }
}
```

## 6. API Reference

### 6.1 Page Routes (GET)

| Path | Description |
|---|---|
| `/` | Dashboard with status summary |
| `/approvals` | Approval item list (filterable by status) |
| `/approvals/{item_id}` | Approval item detail with action buttons |
| `/approval-new` | Create new approval item form |
| `/audit-logs` | Audit log viewer (filterable by item) |

### 6.2 Action Routes (POST)

| Path | Description |
|---|---|
| `/approval-new` | Create new approval item (as Draft) |
| `/approvals/{item_id}/submit` | Submit for review |
| `/approvals/{item_id}/hr-review` | HR confirms review |
| `/approvals/{item_id}/manager-approve` | Manager approves |
| `/approvals/{item_id}/final-approve` | Final approval |
| `/approvals/{item_id}/reject` | Reject (with reason in `comment` field) |
| `/approvals/{item_id}/undo` | Undo last undoable action |
| `/approvals/{item_id}/resubmit` | Resubmit from Rejected → Draft |

## 7. Extending the Workflow

### Adding a new approval step

1. Add the new state to `STATUSES` list
2. Add the state label to `STATUS_LABELS`
3. Add transitions to `TRANSITION_MAP`
4. If undoable, add to `UNDOABLE_STATES` and `UNDO_REVERSE_MAP`
5. Update `get_available_actions()` if special handling needed
6. Update `execute_transition()` to set any step-specific timestamp/actor fields

### Marking a step as non-undoable (data-mutating)

For steps that actually change business data (e.g., sending the email, updating a database):

```python
TRANSITION_MAP[("Final_Approved", "send_email")] = ("Sent", False)  # undoable=False
```

The UI will not show an undo button for this state because it won't be in `UNDOABLE_STATES`.

## 8. Technical Notes

- **Port:** 8006
- **Storage:** JSON files under `tactokyomail/database/`
- **Server:** Python `http.server` with `BaseHTTPRequestHandler`
- **Frontend:** Server-rendered HTML (no SPA framework)
- **Labels:** Trilingual (zh / ja / en)
- **Audit compliance:** All actions logged, audit logs immutable, undo creates new entries only
