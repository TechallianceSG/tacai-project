# UI Design

## Design direction

VendorPayables uses a simple SAP-like enterprise admin style consistent with TAC MVP modules:

- compact top navigation
- light blue / gray background
- card dashboard
- dense operational tables
- status badges
- clear primary and secondary buttons
- trilingual labels

## Language support

Supported languages:

- English (`en`)
- Japanese (`ja`)
- Simplified Chinese (`zh`)

Language is selected by `?lang=en|ja|zh` and passed through navigation links.

## Pages

### Dashboard

Cards:

- Open payables
- Overdue payables
- Due this month
- Paid this month
- Total open amount

Also show recent payable records.

### Payables List

Columns:

- Payable No.
- Vendor
- Invoice No.
- Invoice Date
- Received Date
- Due Date
- Actual Payment Date
- Amount
- Status
- Action

Filters:

- status
- vendor keyword
- due month

### New/Edit Payable

Sections:

1. Vendor
2. Invoice/request dates
3. Amount and tax
4. Business context
5. Attachment and OCR placeholder
6. Notes and action buttons

The same screen supports manual entry and future OCR/AI extraction.

### Payable Detail

Sections:

- Object header with status badge
- Vendor and invoice data
- Amount and tax data
- Payment timeline
- Attachment
- Status actions
- Audit summary

### Vendor Master

Columns:

- Vendor Code
- Vendor Name
- Type
- Qualified Invoice No.
- Payment Terms
- Active
- Action

## Status badge colors

- Draft: gray
- Submitted: blue
- Approved: green
- Scheduled: purple
- Paid: dark green
- Rejected: red
- Cancelled: dark gray
