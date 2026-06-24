# Phase 3 Implementation Plan - Approval Workflow and Monthly Lock

## Implementation status

Implemented in the local MVP backend on 2026-06-15. The app now supports row-level submit/approve/reject/reopen actions and month-level locking through `database/month_locks.json`.

## Purpose

Phase 3 should turn the current timesheet records into confirmed monthly work data that can safely feed later CSV export, billing summaries, invoice preparation, and payroll integration.

Phase 1 and Phase 2 already provide:

- Timesheet create/edit/list/filter and soft delete.
- Employee master data.
- Project/customer master data.
- Master-data snapshots in timesheet rows.
- Monthly summaries by employee and by project/customer.

Phase 3 adds approval control and monthly closing rules on top of those records.

## Recommended scope

### In scope

1. Timesheet approval status transitions.
2. Submit, approve, reject, and reopen actions.
3. Monthly lock records or lock metadata.
4. Validation rules that prevent edits/deletes after approval or month lock.
5. UI actions and status messages for the local MVP.
6. Dependency-free local JSON persistence.

### Out of scope for Phase 3

1. Login and role-based permissions.
2. Email notification.
3. CSV/Excel export.
4. Billing rate and invoice generation.
5. Payroll integration.
6. Cross-midnight shifts.
7. Automatic night-work overlap calculation.

These should remain later phases unless explicitly prioritized.

## Status model

Use existing approval-like status values where possible and make the workflow explicit.

Recommended row statuses:

| Status | Meaning | Editable? |
|---|---|---:|
| `Draft` | Employee/admin is still preparing the row. | Yes |
| `Submitted` | Row is submitted for review. | No, except reopen/reject workflow |
| `Approved` | Row is approved and ready for monthly closing/export/billing. | No |
| `Rejected` | Row needs correction. | Yes, then resubmit |

Monthly lock should be separate from row status. A month can be locked after review, preventing changes to all active rows for that month.

Recommended locked behavior:

- Locked month blocks creating new rows for that month.
- Locked month blocks editing rows in that month.
- Locked month blocks deleting rows in that month.
- Locked month can be reopened only through an explicit admin action in a later phase or controlled local action.

## Data model additions

### Timesheet row fields

Add or standardize these fields in `database/timesheet_entries.json`:

| Field | Description |
|---|---|
| `approval_status` | `Draft`, `Submitted`, `Approved`, or `Rejected`. |
| `submitted_at` | UTC ISO datetime when submitted. |
| `submitted_by` | User/admin label for MVP, e.g. `local_user`. |
| `approved_at` | UTC ISO datetime when approved. |
| `approved_by` | Approver label for MVP. |
| `rejected_at` | UTC ISO datetime when rejected. |
| `rejected_by` | Rejector label for MVP. |
| `reject_reason` | Optional reason shown on row/detail screen. |
| `reopened_at` | UTC ISO datetime when reopened from Submitted/Approved if allowed. |
| `reopened_by` | Reopener label for MVP. |

For the local MVP, `*_by` can be a fixed value such as `local_user` until login/roles are implemented.

### Month lock storage

Recommended new file:

```text
database/month_locks.json
```

Suggested record shape:

```json
{
  "lock_id": "lock-YYYYMM-...",
  "work_month": "2026-06",
  "lock_status": "Locked",
  "locked_at": "2026-06-15T00:00:00+00:00",
  "locked_by": "local_user",
  "notes": "Optional closing note",
  "created_at": "2026-06-15T00:00:00+00:00",
  "updated_at": "2026-06-15T00:00:00+00:00"
}
```

Use a separate lock file rather than adding lock fields to every timesheet row. This keeps month-level state centralized and avoids rewriting many rows during lock/unlock operations.

## UI changes

### Timesheet list page

Add row-level actions based on status and month lock state:

| Current status | Available actions |
|---|---|
| Draft | Edit, Delete, Submit |
| Submitted | Approve, Reject, Reopen |
| Approved | Reopen if month is not locked |
| Rejected | Edit, Delete, Submit |
| Any status in locked month | No edit/delete/status-changing actions |

Add or keep filters for:

- Employee.
- Month.
- Customer.
- Project.
- Approval status.
- Lock status if useful.

### Monthly closing panel

Add a simple panel on `/timesheets`:

1. Select `work_month`.
2. Show summary counts:
   - Draft rows.
   - Submitted rows.
   - Approved rows.
   - Rejected rows.
   - Deleted rows excluded from active summary.
3. Show whether month is locked.
4. Show `Lock Month` button only when active rows for that month are all approved.
5. Show locked month metadata after lock.

## Backend route plan

Add POST routes:

| Route | Purpose |
|---|---|
| `/timesheet-submit` | Draft/Rejected → Submitted. |
| `/timesheet-approve` | Submitted → Approved. |
| `/timesheet-reject` | Submitted → Rejected with reason. |
| `/timesheet-reopen` | Submitted/Approved → Draft or Rejected depending on rule. |
| `/month-lock` | Lock a month after all active rows are approved. |

Optional later route:

| Route | Purpose |
|---|---|
| `/month-unlock` | Reopen a locked month, admin-only once login/roles exist. |

For Phase 3 MVP, unlocking can be omitted to keep closing rules simple.

## Validation rules

Add these rules before save/update/delete/status transitions:

1. Cannot create a timesheet row for a locked month.
2. Cannot edit a row in a locked month.
3. Cannot soft-delete a row in a locked month.
4. Cannot edit or delete a `Submitted` or `Approved` row unless it is reopened or rejected first.
5. Cannot approve a row unless current status is `Submitted`.
6. Cannot reject a row unless current status is `Submitted`.
7. Cannot submit a row unless current status is `Draft` or `Rejected`.
8. Cannot lock a month unless every active row in that month is `Approved`.
9. Month lock should ignore soft-deleted rows.

## Implementation steps

### Step 1 - Normalize existing status handling

- Confirm current `approval_status` values used by code and data.
- Ensure all newly saved rows default to `Draft` unless a different initial status is intentionally selected.
- Add a helper to normalize missing status on older rows to `Draft` at read/display time.

### Step 2 - Add month lock persistence

- Add `MONTH_LOCKS_PATH` constant.
- Add helpers:
  - `load_month_lock_records()`.
  - `save_month_lock_records(records)`.
  - `find_month_lock(work_month)`.
  - `is_month_locked(work_month)`.
  - `create_month_lock(work_month, notes)`.

### Step 3 - Add transition helpers

- Add helpers:
  - `submit_timesheet_record(record_id)`.
  - `approve_timesheet_record(record_id)`.
  - `reject_timesheet_record(record_id, reason)`.
  - `reopen_timesheet_record(record_id)`.
- Keep `created_at` unchanged.
- Refresh `updated_at` on every transition.
- Set the relevant timestamp and actor fields.

### Step 4 - Protect existing edit/delete/create flows

- In create flow, reject save if `work_date[:7]` is locked.
- In edit flow, reject update if the row month is locked.
- In delete flow, reject soft delete if the row month is locked.
- Reject edit/delete for `Submitted` and `Approved` rows unless reopened/rejected.

### Step 5 - Add list-page action buttons

- Show transition buttons next to each row according to current status.
- Hide all row actions for locked months.
- Add reject reason input or a simple reject form.

### Step 6 - Add monthly closing panel

- Calculate monthly status counts from active rows.
- Show whether selected month is lockable.
- Add `Lock Month` POST form.
- Validate all rows are approved before lock.

### Step 7 - Add manual test checklist

Create or update a manual checklist covering:

- Submit Draft row.
- Reject Submitted row with reason.
- Edit Rejected row and resubmit.
- Approve Submitted row.
- Block edit/delete for Submitted and Approved rows.
- Lock month after all rows are approved.
- Block create/edit/delete/status transitions in locked month.
- Confirm monthly summaries still exclude Deleted rows and include Approved rows.

## Recommended order of later phases

After Phase 3:

1. CSV export for confirmed/approved monthly timesheets.
2. Billing rate fields and billing summaries.
3. Invoice draft table.
4. Login and role-based permissions.
5. Cross-midnight and automatic night-work calculations.

This order keeps confirmed monthly work data stable before export and invoicing.
