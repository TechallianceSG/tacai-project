# Workflow Specification

## Status model

| Status | Meaning | Editable? | Finance action |
|---|---|---:|---|
| `Draft` | Record is being prepared. | Yes | Submit or cancel. |
| `Submitted` | Payable is ready for finance review. | Limited | Approve, reject, or cancel. |
| `Approved` | Payable is approved for payment. | Limited | Schedule, mark paid, or cancel. |
| `Scheduled` | Payable is included in a payment schedule. | No core fields | Mark paid. |
| `Paid` | Payment is completed. | No core fields | Reference only. |
| `Rejected` | Finance rejected the request. | Yes | Correct and resubmit. |
| `Cancelled` | Record was cancelled. | No | Reference only. |

## Allowed transitions

```text
Draft -> Submitted
Draft -> Cancelled
Submitted -> Approved
Submitted -> Rejected
Submitted -> Cancelled
Rejected -> Draft
Approved -> Scheduled
Approved -> Paid
Approved -> Cancelled
Scheduled -> Paid
```

## Manual entry flow

1. Finance/business user opens New Payable.
2. User selects a vendor from Master Data Management. Vendor creation/update belongs in Master Data Management, not VendorPayables.
3. User enters invoice/request details.
4. User uploads invoice/request attachment if available.
5. User saves as Draft or submits as Submitted.
6. System saves `vendor_id` plus vendor code/name/qualified-invoice/payment-terms snapshots on the payable record.
7. System validates submitted records.
8. System writes audit log.

## Finance approval flow

1. Finance opens Payables List and filters Submitted records.
2. Finance checks vendor, invoice number, attachment, tax, due date, and amount.
3. Finance approves or rejects.
4. Approved records can be scheduled or marked paid.
5. Paid records require actual payment date.
6. Every transition writes audit log.

## OCR/AI-assisted flow, later phase

1. User uploads PDF/JPG/PNG invoice/request in the same form.
2. User clicks Extract from invoice/request.
3. System stores OCR/AI result in `ocr_draft`.
4. Empty standard fields may be prefilled.
5. User confirms/corrects all values.
6. Workflow uses confirmed standard fields, not raw OCR output.

## Audit events

At minimum, log:

- payable create/update
- vendor snapshot copied from Master Data Management
- attachment upload
- submit
- approve
- reject
- schedule
- mark paid
- cancel
- CSV export
