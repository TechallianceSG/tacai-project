"""Payroll Release — 給与明細 / PDF / メール / 发放管理 (trilingual zh/ja/en)"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from datetime import datetime, timezone
from database import fetch_all, fetch_one, execute
from i18n import get_lang, load_i18n, t, SUPPORTED_LANGS
from services.payslip_pdf import generate_payslip_pdf, generate_payslip_html, generate_payslip_text
import smtplib, os, re
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

router = APIRouter(prefix="/release", tags=["Payroll Release"])

SHT = "pay_jp_monthly_salary_sheets"
REC = "pay_jp_monthly_salary_records"
PS = "pay_jp_payslips"
ED = "pay_jp_email_deliveries"
PAYSLIP_DIR = Path(__file__).resolve().parents[1] / "payslips"
PAYSLIP_DIR.mkdir(exist_ok=True)

SMTP_HOST = os.environ.get("PAYSLIP_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("PAYSLIP_SMTP_PORT", "587") or "587")
SMTP_USER = os.environ.get("PAYSLIP_SMTP_USERNAME", "").strip()
SMTP_PASS = os.environ.get("PAYSLIP_SMTP_PASSWORD", "")
SMTP_TLS = os.environ.get("PAYSLIP_SMTP_USE_TLS", "1").strip() not in ("0","false","no","off")
SENDER = os.environ.get("PAYSLIP_EMAIL_SENDER", "hradmin@tacjob.com").strip() or "hradmin@tacjob.com"
SENDER_NAME = os.environ.get("PAYSLIP_EMAIL_SENDER_NAME", "TACAI Pay JP").strip() or "TACAI Pay JP"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def now_iso(): return datetime.now(timezone.utc).isoformat()


def lang_switcher(lang: str, path: str) -> str:
    parts = []
    for l in SUPPORTED_LANGS:
        active = 'class="active"' if l == lang else ""
        parts.append(f'<a href="{path}?lang={l}" {active}>{l.upper()}</a>')
    return f'<div class="lang-switch">{"".join(parts)}</div>'


STYLE = """<style>
:root {
  --navy: #14213d;
  --blue: #1f6feb;
  --page-bg: #f6f8fb;
  --surface: #ffffff;
  --surface-muted: #f8fafc;
  --border: #d8dee9;
  --border-strong: #c8d1dc;
  --text: #17202a;
  --muted: #65758b;
  --accent: #1f6feb;
  --green: #0f766e;
  --danger: #b91c1c;
  --shadow-soft: 0 1px 2px rgba(15, 23, 42, 0.04);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Hiragino Sans','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.5;color:var(--text);background:var(--page-bg)}
.header{background:linear-gradient(135deg,#14213d,#6a1b9a);color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.header h1{font-size:clamp(1.2rem,2.2vw,1.4rem);font-weight:700}
.header a{color:#fff;text-decoration:none;font-size:0.95rem;opacity:.85}
.container{max-width:1400px;margin:0 auto;padding:16px}
.card{background:var(--surface);border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;margin-bottom:16px;border:1px solid var(--border)}
.card-header{background:var(--surface-muted);padding:10px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
table{width:100%;border-collapse:collapse;font-size:1.0rem}
th{text-align:left;padding:10px 8px;border-bottom:2px solid var(--border-strong);color:#555;font-weight:800;white-space:nowrap;background:var(--surface-muted);font-size:0.95rem}
td{padding:7px 8px;border-bottom:1px solid #f0f0f0;vertical-align:top;line-height:1.4;font-size:1.0rem}
tr:hover{background:#f5f7ff}
.num{text-align:right;font-variant-numeric:tabular-nums}
.btn{padding:10px 18px;border:none;border-radius:8px;font-size:1.0rem;cursor:pointer;font-weight:800;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;min-height:42px;gap:4px}
.btn-primary{background:var(--accent);color:#fff}.btn-success{background:var(--green);color:#fff}
.btn-outline{background:var(--surface);color:var(--navy);border:1px solid var(--border)}
.btn-sm{padding:6px 12px;font-size:0.9rem;min-height:34px}
.btn-purple{background:#6a1b9a;color:#fff}.btn-email{background:#e65100;color:#fff}
.summary-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}
.summary-card{background:var(--surface);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow-soft);border:1px solid var(--border)}
.summary-card .val{font-size:2.0rem;font-weight:700;color:var(--navy)}
.summary-card .lbl{font-size:0.9rem;color:var(--muted)}
.footer-text{text-align:center;color:var(--muted);font-size:0.9rem;padding:12px}
.empty{text-align:center;color:var(--muted);padding:48px;font-size:1rem}
.lang-switch{display:flex;gap:4px}.lang-switch a{padding:4px 10px;border-radius:999px;font-size:0.82rem;color:#fff;text-decoration:none;border:1px solid rgba(255,255,255,.3);font-weight:600}
.lang-switch a.active{background:rgba(255,255,255,.2);border-color:#fff;font-weight:750}
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.5);z-index:1000;justify-content:center;align-items:center}
.modal-overlay.active{display:flex}
.modal-box{background:var(--surface);border-radius:14px;padding:24px;min-width:360px;max-width:800px;width:90%;max-height:90vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.2)}
.modal-box h2{font-size:1.2rem;color:var(--navy);margin-bottom:12px}
.modal-actions{display:flex;gap:12px;justify-content:flex-end;margin-top:16px}
.modal-actions .btn-no{background:#e0e0e0;color:#333;min-width:80px}
.modal-actions .btn-yes{background:var(--accent);color:#fff;min-width:80px}
.preview-employee{padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:0.9rem}
.preview-employee:last-child{border-bottom:none}
</style>"""


# ═══════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════

@router.get("/{sheet_id}/payslips")
async def get_payslips(sheet_id: str):
    records = fetch_all(f"SELECT * FROM {REC} WHERE sheet_id=%s ORDER BY employee_number", (sheet_id,))
    return {"data": records, "count": len(records)}

@router.get("/payslip/{record_id}/html", response_class=HTMLResponse)
async def payslip_html(request: Request, record_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    r = fetch_one(f"SELECT * FROM {REC} WHERE record_id=%s", (record_id,))
    if not r: raise HTTPException(404, "Not found")
    return HTMLResponse(generate_payslip_html(r, msgs))

@router.get("/payslip/{record_id}/pdf")
async def payslip_pdf(request: Request, record_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    r = fetch_one(f"SELECT * FROM {REC} WHERE record_id=%s", (record_id,))
    if not r: raise HTTPException(404, "Not found")
    pdf_bytes = generate_payslip_pdf(r, msgs)
    filename = f"{r['payroll_month']}_{r['employee_number']}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})

@router.post("/payslip/{record_id}/send-email")
async def send_single_email(request: Request, record_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    r = fetch_one(f"SELECT * FROM {REC} WHERE record_id=%s", (record_id,))
    if not r: raise HTTPException(404, "Not found")
    return _send_email_for_record(r, msgs)

@router.post("/{sheet_id}/send-all-emails")
async def send_all_emails(request: Request, sheet_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    records = fetch_all(f"SELECT * FROM {REC} WHERE sheet_id=%s ORDER BY employee_number", (sheet_id,))
    sent = 0; failed = 0
    for r in records:
        result = _send_email_for_record(r, msgs)
        if result.get("ok"): sent += 1
        else: failed += 1
    return {"ok": True, "sent": sent, "failed": failed, "total": len(records)}


def _send_email_for_record(record: dict, msgs: dict) -> dict:
    email = (record.get("email") or "").strip()
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": f"Invalid email: {email}"}
    month = record['payroll_month']
    if not SMTP_HOST:
        pdf_bytes = generate_payslip_pdf(record, msgs)
        path = PAYSLIP_DIR / f"{month}_{record['employee_number']}.pdf"
        path.write_bytes(pdf_bytes)
        return {"ok": True, "queued": True, "note": t(msgs, "release.pdf_saved")}

    try:
        pdf_bytes = generate_payslip_pdf(record, msgs)
        msg = EmailMessage()
        msg["From"] = formataddr((SENDER_NAME, SENDER))
        msg["To"] = email
        msg["Subject"] = t(msgs, "release.email_subject_default", month=month)
        msg.set_content(generate_payslip_text(record, msgs))
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                           filename=f"payslip_{month}_{record['employee_number']}.pdf")
        ctx = None
        if SMTP_TLS:
            import ssl
            ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as srv:
            if SMTP_TLS: srv.starttls(context=ctx)
            if SMTP_USER: srv.login(SMTP_USER, SMTP_PASS)
            srv.send_message(msg)
        return {"ok": True, "sent": True, "email": email}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ═══════════════════════════════════════════════
# CSV Export
# ═══════════════════════════════════════════════

@router.get("/{sheet_id}/csv-export")
async def csv_export(sheet_id: str):
    records = fetch_all(f"SELECT * FROM {REC} WHERE sheet_id=%s ORDER BY employee_number", (sheet_id,))
    import csv, io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Employee Number","Name","Type","Gross Pay","Deductions","Net Pay","Employer Cost"])
    for r in records:
        w.writerow([r.get("employee_number"), r.get("employee_name"), r.get("salary_type"),
                     r.get("gross_pay",0), r.get("deduction_total",0), r.get("net_pay",0), r.get("employer_cost_total",0)])
    out.seek(0)
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{sheet_id}.csv"'})


# ═══════════════════════════════════════════════
# Release Management HTML Page
# ═══════════════════════════════════════════════

@router.get("/{sheet_id}", response_class=HTMLResponse)
async def release_page(request: Request, sheet_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    th = lambda k: t(msgs, k)

    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if not s: return HTMLResponse("<h2>Not found</h2>", status_code=404)
    records = fetch_all(f"SELECT * FROM {REC} WHERE sheet_id=%s ORDER BY employee_number", (sheet_id,))
    smtp_ready = bool(SMTP_HOST)
    total_records = len(records)

    parts = [f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><title>{th('release.title')} - {sheet_id}</title>{STYLE}</head><body>
<div class="header"><div><h1>📤 {th('release.title')}</h1><span style="font-size:0.95rem;opacity:.85">{sheet_id} | {s['payroll_month']} | {t(msgs,'monthly.status')}: {s['status']}</span></div>
<div>{lang_switcher(lang, f'/release/{sheet_id}')}<a href="/api/monthly-sheets/page/detail?sheet_id={sheet_id}&lang={lang}" style="display:inline-block;padding:8px 16px;background:rgba(255,255,255,.2);border-radius:8px;color:#fff;text-decoration:none;font-weight:700">{th('release.back')}</a> <a href="/?lang={lang}" style="color:#fff">{th('release.home')}</a></div></div>
<div class="container">
<div class="summary-cards">
<div class="summary-card"><div class="val">{total_records}</div><div class="lbl">{th('release.employee_count')}</div></div>
<div class="summary-card"><div class="val">¥{int(s.get('gross_total',0) or 0):,}</div><div class="lbl">{th('release.gross_total')}</div></div>
<div class="summary-card"><div class="val">¥{int(s.get('deduction_total',0) or 0):,}</div><div class="lbl">{th('release.ded_total')}</div></div>
<div class="summary-card"><div class="val">¥{int(s.get('net_total',0) or 0):,}</div><div class="lbl">{th('release.net_total')}</div></div>
<div class="summary-card"><div class="val">{'✅' if smtp_ready else '⚠️'}</div><div class="lbl">{th('release.smtp_status')}</div></div>
</div>
<div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center">
<button class="btn btn-email" onclick="previewEmail()" style="font-size:1.05rem;padding:12px 24px">{th('release.send_selected')}</button>
<button class="btn btn-email" onclick="sendAll()" style="background:#c62828">{th('release.send_all')}</button>
<a class="btn btn-outline" href="/release/{sheet_id}/csv-export">{th('release.csv_export')}</a>
<a class="btn btn-purple" href="/api/monthly-sheets/page/list?lang={lang}">{th('release.back')}</a>
<span id="sel-info" style="font-size:1rem;color:var(--muted);margin-left:8px;font-weight:600"></span>
<span style="font-size:0.95rem;color:var(--muted);margin-left:auto">{th('release.smtp_ready') if smtp_ready else th('release.smtp_not_ready')}</span>
</div>
<div class="card"><div style="overflow-x:auto"><table>
<tr><th style="width:40px"><input type="checkbox" id="selectAll" onchange="toggleAll(this.checked)" title="{th('release.select_all')}/{th('release.deselect_all')}"></th><th>{th('monthly.table_emp_no')}</th><th>{th('monthly.table_name')}</th><th>{th('monthly.table_type')}</th><th>{th('monthly.table_gross')}</th><th>{th('monthly.table_ded_total')}</th><th>{th('monthly.table_net')}</th><th style="width:260px">{t(msgs,'salary_master.notes')}</th></tr>"""]

    for r in records:
        rid = r['record_id']
        parts.append(f"""<tr>
<td><input type="checkbox" class="emp-checkbox" value="{rid}" onchange="updateSelCount()"></td>
<td>{r['employee_number']}</td><td><strong>{r['employee_name']}</strong></td><td style="font-size:0.9rem">{r.get('salary_type','')}</td>
<td class="num">¥{int(r.get('gross_pay',0) or 0):,}</td><td class="num">¥{int(r.get('deduction_total',0) or 0):,}</td>
<td class="num" style="font-weight:700;color:#2e7d32">¥{int(r.get('net_pay',0) or 0):,}</td>
<td style="white-space:nowrap">
<a class="btn btn-outline btn-sm" href="/release/payslip/{rid}/html?lang={lang}" target="_blank">{th('release.ops_view_html')}</a>
<a class="btn btn-outline btn-sm" href="/release/payslip/{rid}/pdf?lang={lang}" target="_blank">{th('release.ops_download_pdf')}</a>
<button class="btn btn-primary btn-sm" onclick="printPayslip('{rid}')">{th('release.ops_print')}</button>
<button class="btn btn-email btn-sm" onclick="sendOne('{rid}')">{th('release.ops_send_email')}</button>
</td></tr>""")
    parts.append(f'</table></div></div><div class="footer-text">{t(msgs,"general.records", count=str(total_records))}</div></div>')

    # Email subject/body defaults (bilingual JP/EN with placeholders)
    email_subject_default = f"【TACAI】{s['payroll_month']} 給与明細 / Payslip for {s['payroll_month']}"
    email_body_default = f"""{{employee_name}} 様

お世話になっております。
{s['payroll_month']}分の給与明細を添付しておりますので、ご確認ください。
ご不明な点がございましたら、HRまでお問い合わせください。

---
Dear {{employee_name}},

Please find attached your payslip for {s['payroll_month']}.
If you have any questions, please contact HR.

Best regards,
TACAI Pay JP
---
本メールは自動送信です。This is an automated email."""

    parts.append(f"""<div class="modal-overlay" id="emailPreviewModal">
<div class="modal-box">
<h2>{th('release.email_preview')}</h2>

<div style="margin-bottom:12px">
<label style="font-weight:700;display:block;margin-bottom:4px;font-size:0.95rem">{th('release.email_subject')}:</label>
<input id="emailSubject" value="{email_subject_default}" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:8px;font-size:1rem">
</div>

<div style="margin-bottom:12px">
<label style="font-weight:700;display:block;margin-bottom:4px;font-size:0.95rem">{th('release.email_body')}:</label>
<textarea id="emailBody" rows="10" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:8px;font-size:0.95rem;font-family:monospace;line-height:1.5">{email_body_default}</textarea>
</div>

<div style="margin-bottom:12px">
<label style="font-weight:700;display:block;margin-bottom:4px;font-size:0.95rem">{th('release.selected_count', count='<span id="previewCount">0</span>')}:</label>
<div id="previewArea" style="max-height:250px;overflow-y:auto;border:1px solid var(--border);padding:8px;border-radius:8px;background:#f9f9f9;font-size:0.9rem">
</div>
</div>

<div class="modal-actions">
<button class="btn btn-no" onclick="closeEmailPreview()">{th('btn.cancel')}</button>
<button class="btn btn-yes" onclick="confirmSendEmail()" style="background:var(--accent);color:#fff;font-size:1.05rem;padding:12px 28px">{th('release.confirm_send')}</button>
</div>
</div></div>""")

    # JS i18n strings
    send_one_confirm = th('release.send_one_confirm')
    send_all_confirm = th('release.send_all_confirm', count=str(total_records))
    sent_ok = th('release.sent_ok')
    pdf_saved = th('release.pdf_saved')
    send_success = th('release.send_success')
    send_fail = th('release.send_fail')
    select_employees = th('release.select_employees')
    sel_count_label = th('release.selected_count')

    parts.append(f"""<script>
function toggleAll(checked) {{
  document.querySelectorAll('.emp-checkbox').forEach(function(cb) {{ cb.checked = checked; }});
  updateSelCount();
}}
function getSelected() {{
  return Array.from(document.querySelectorAll('.emp-checkbox:checked')).map(function(cb) {{ return cb.value; }});
}}
function updateSelCount() {{
  var n = getSelected().length;
  document.getElementById('sel-info').textContent = n > 0 ? '{sel_count_label}'.replace('{{count}}', n) : '';
}}
function sendOne(rid) {{
  if (!confirm('{send_one_confirm}')) return;
  fetch('/release/payslip/'+rid+'/send-email', {{method:'POST'}})
    .then(function(r){{ return r.json(); }})
    .then(function(d){{ alert(d.ok?('{sent_ok}'+(d.sent?'':' ({pdf_saved})')):'{send_fail}: '+d.error); }});
}}
async function sendAll() {{
  if (!confirm('{send_all_confirm}')) return;
  var r = await fetch('/release/{sheet_id}/send-all-emails', {{method:'POST'}});
  var d = await r.json();
  alert(d.ok?'{send_success}'.replace('{{sent}}',d.sent).replace('{{failed}}',d.failed):'{send_fail}: '+JSON.stringify(d));
}}
function printPayslip(rid) {{ window.open('/release/payslip/'+rid+'/html?lang={lang}','_blank').print(); }}

function previewEmail() {{
  var selected = getSelected();
  if (selected.length === 0) {{ alert('{select_employees}'); return; }}
  document.getElementById('previewCount').textContent = selected.length;

  var area = document.getElementById('previewArea');
  area.innerHTML = '';
  document.querySelectorAll('.emp-checkbox:checked').forEach(function(cb) {{
    var tr = cb.closest('tr');
    var name = tr.querySelector('td:nth-child(3)').textContent.trim();
    var number = tr.querySelector('td:nth-child(2)').textContent.trim();
    var div = document.createElement('div');
    div.className = 'preview-employee';
    div.innerHTML = '<strong>'+number+'</strong> — '+name;
    area.appendChild(div);
  }});

  document.getElementById('emailPreviewModal').classList.add('active');
}}
function closeEmailPreview() {{
  document.getElementById('emailPreviewModal').classList.remove('active');
}}
async function confirmSendEmail() {{
  var selected = getSelected();
  var subject = document.getElementById('emailSubject').value;
  var body = document.getElementById('emailBody').value;
  if (!confirm(selected.length+' ')) return;

  var sent = 0, failed = 0;
  for (var i = 0; i < selected.length; i++) {{
    var resp = await fetch('/release/payslip/'+selected[i]+'/send-email', {{method:'POST'}});
    var d = await resp.json();
    if (d.ok) sent++; else failed++;
  }}
  alert('{send_success}'.replace('{{sent}}',sent).replace('{{failed}}',failed));
  closeEmailPreview();
}}
document.getElementById('emailPreviewModal').addEventListener('click', function(e) {{ if (e.target === this) closeEmailPreview(); }});
</script></body></html>""")
    return HTMLResponse("\n".join(parts))
