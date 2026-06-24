# OCR Vendor Invoice Prompt Draft

Extract draft values from a supplier invoice or payment request for Japan vendor payables.

Return JSON only. Do not guess unclear values. Use `null` when unknown.

Fields:

```json
{
  "vendor_name": null,
  "invoice_number": null,
  "invoice_date": null,
  "payment_due_date": null,
  "currency": "JPY",
  "total_amount": null,
  "amount_excluding_tax": null,
  "tax_amount": null,
  "tax_rate": null,
  "qualified_invoice_number": null,
  "bank_account_text": null,
  "confidence_notes": [],
  "requires_manual_review": true
}
```

Rules:

- `invoice_date` and `payment_due_date` must use `YYYY-MM-DD` when detected.
- Japanese qualified invoice number should look like `T` plus 13 digits.
- Amounts should be numeric strings without commas.
- OCR output is draft assistance only; finance users must confirm final payable fields.
