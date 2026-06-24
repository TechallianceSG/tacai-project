# OCR / AI Plan

## Purpose

OCR/AI will assist finance users by extracting draft data from supplier invoices and payment requests.

It must not replace finance confirmation.

## Supported file types

- PDF (first page OCR)
- JPG / JPEG
- PNG
- WEBP

## Implemented local-first OCR behavior

As of 2026-06-21, VendorPayables uses a local-first OCR flow adapted from the TAC-reimbursement expense module:

1. Images are processed with local Tesseract using Japanese + English language data (`jpn+eng`).
2. PDFs are converted from the first page with `pdftoppm` when Poppler is available, then processed with Tesseract.
3. On macOS, when Tesseract or Poppler is unavailable, the app falls back to Apple Vision via `backend/macos_vision_ocr.swift`.
4. OCR results are saved as `ocr_draft` with `ocr_status`.
5. Finance users must review and confirm draft values before submitting OCR-assisted payables.
6. OCR failures never block manual payable entry.
7. OCR attempts to match Vendor Master by qualified invoice number and vendor name.
8. If no recurring supplier match exists, users can switch to One-time Vendor mode; OCR suggestions can fill the actual one-time supplier name, qualified invoice number, and bank account text.


## Design principles

1. OCR/AI happens in the same New/Edit Payable screen.
2. Manual entry remains available at all times.
3. OCR output is stored as `ocr_draft`.
4. The final accounting/payment fields are the standard payable fields after user confirmation.
5. OCR failures should not block manual entry.

## Target extracted fields

- vendor name
- invoice number
- invoice date
- payment due date
- total amount
- amount excluding tax
- tax amount
- tax rate
- qualified invoice number
- bank account text if present
- notes/confidence warnings

## Draft output example

```json
{
  "vendor_name": "Example Recruiting Media Co., Ltd.",
  "invoice_number": "INV-2026-001",
  "invoice_date": "2026-06-01",
  "payment_due_date": "2026-07-31",
  "currency": "JPY",
  "total_amount": "110000",
  "amount_excluding_tax": "100000",
  "tax_amount": "10000",
  "tax_rate": "10%",
  "qualified_invoice_number": "T1234567890123",
  "bank_account_text": "Example Bank Tokyo Branch\n普通 1234567\n口座名義 Example Recruiting Media Co., Ltd.",
  "confidence_notes": ["Payment due date detected from footer."],
  "requires_manual_review": true,
  "raw_text_preview": "Short OCR text preview only; full OCR text is not stored in audit logs.",
  "source_attachment": "VP-2026-0001-invoice.pdf",
  "created_at": "2026-06-21T00:00:00+00:00"
}
```

## Audit and data handling

- OCR actions append audit events such as `ocr_started`, `ocr_draft_created`, `ocr_failed`, `ocr_not_available`, `ocr_replaced`, and `ocr_confirmed`.
- Audit logs store metadata and summary notes only; full raw OCR text is not written to audit logs.
- The final payment workflow, CSV export, and finance review use standard payable fields, not unconfirmed OCR suggestions.
