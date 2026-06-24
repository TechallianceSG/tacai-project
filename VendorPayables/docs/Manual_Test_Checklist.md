# Manual Test Checklist

## Setup

```bash
cd /Users/terencewang/Documents/claude-project/VendorPayables
python3 -m py_compile backend/app.py
python3 backend/app.py --host 127.0.0.1 --port 8008
```

Health check:

```bash
curl -s http://127.0.0.1:8008/health
```

Expected:

```json
{"status":"ok"}
```

## Browser checks

Open `http://127.0.0.1:8008/`.

- [ ] Dashboard opens.
- [ ] Language switcher works for English, Japanese, and Chinese.
- [ ] Vendor list opens.
- [ ] New vendor can be created.
- [ ] Vendor can be edited.
- [ ] Vendor can be deactivated.
- [ ] Payables list opens.
- [ ] New payable draft can be saved.
- [ ] Payable can record invoice date, received date, payment due date, and actual payment date.
- [ ] Payable can upload PDF/JPG/PNG attachment.
- [ ] Invalid attachment type is rejected.
- [ ] Draft can be submitted.
- [ ] Submitted can be approved.
- [ ] Submitted can be rejected.
- [ ] Approved can be scheduled.
- [ ] Scheduled can be marked paid.
- [ ] Paid requires actual payment date.
- [ ] CSV export downloads.
- [ ] Audit log entries are created for create/update/upload/status/export actions.

## OCR checks

Optional local OCR tool checks:

```bash
tesseract --version
tesseract --list-langs
pdftoppm -v
swift --version
```

Manual OCR flow:

- [ ] Open `/payables/new`.
- [ ] Upload a supported Japanese supplier invoice image or PDF.
- [ ] Click `Extract from invoice/request`.
- [ ] OCR creates or updates a Draft payable and shows the OCR Draft Review panel.
- [ ] Empty standard payable fields are prefilled from OCR suggestions.
- [ ] Manually entered fields are preserved over OCR suggestions.
- [ ] `ocr_status` is `draft` after successful OCR.
- [ ] Submit without OCR review confirmation is blocked.
- [ ] Submit with OCR review confirmation changes `ocr_status` to `confirmed`.
- [ ] Unsupported/no attachment OCR attempts fail gracefully and do not block manual payable entry.
- [ ] OCR audit events are appended without storing full raw OCR text.

## Data checks

```bash
python3 -m json.tool database/vendor_payables.json
python3 -m json.tool database/vendors.json
python3 -m json.tool database/audit_logs.json
python3 -m json.tool database/report_exports.json
```
