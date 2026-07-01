"""Monthly Salary Sheets — 月度工资表 API + HTML pages (trilingual zh/ja/en)"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import datetime, timezone
from database import fetch_all, fetch_one, execute, execute_returning
from i18n import t, get_lang, load_i18n, SUPPORTED_LANGS

router = APIRouter(prefix="/api/monthly-sheets", tags=["Monthly Sheets"])

SHT = "pay_jp_monthly_salary_sheets"
REC = "pay_jp_monthly_salary_records"

def now_iso(): return datetime.now(timezone.utc).isoformat()


# ── API ──
@router.get("/")
async def list_sheets(entity_id: Optional[str]=None, month: Optional[str]=None):
    where=["1=1"]; params=[]
    if entity_id: where.append("entity_id=%s"); params.append(entity_id)
    if month: where.append("payroll_month=%s"); params.append(month)
    rows = fetch_all(f"SELECT * FROM {SHT} WHERE {' AND '.join(where)} ORDER BY payroll_month DESC, sheet_id", tuple(params) if params else None)
    return {"data": rows, "count": len(rows)}

@router.post("/create")
async def create_sheet(request: Request):
    body = await request.json()
    month = body.get("payroll_month", datetime.now().strftime("%Y-%m"))
    entity_id = body.get("entity_id", "ENT-0004")

    employees = fetch_all(
        "SELECT * FROM pay_jp_salary_master WHERE entity_id=%s AND active=true ORDER BY employee_number",
        (entity_id,))
    if not employees: raise HTTPException(400, "No active employees found")

    sheet_id = f"MSS-JP-{month}-{entity_id}"
    existing = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if existing: raise HTTPException(400, f"Sheet already exists: {sheet_id}")

    sheet = {"sheet_id": sheet_id, "country_code": "JP", "entity_id": entity_id,
             "payroll_month": month, "status": "draft", "version": 1,
             "employee_count": len(employees), "standard_work_days": 22,
             "standard_work_hours": 176, "attendance_source": "manual",
             "created_by": body.get("created_by", "HR"), "created_at": now_iso(), "updated_at": now_iso()}

    cols = ",".join(sheet.keys()); ph = ",".join(["%s"]*len(sheet))
    execute(f"INSERT INTO {SHT}({cols}) VALUES({ph})", tuple(sheet.values()))

    for emp in employees:
        rec_id = f"{sheet_id}-{emp['employee_id']}"
        rec = {
            "record_id": rec_id, "sheet_id": sheet_id, "payroll_month": month,
            "country_code": "JP", "entity_id": entity_id,
            "employee_id": emp["employee_id"], "employee_number": emp["employee_number"],
            "employee_name": emp["employee_name"], "email": emp.get("email",""),
            "department_label": emp.get("department_label",""), "team_label": emp.get("team_label",""),
            "salary_type": emp.get("salary_type","monthly"), "basic_salary": emp.get("basic_salary",0),
            "hourly_rate": emp.get("hourly_rate",0), "daily_rate": emp.get("daily_rate",0),
            "standard_work_days": emp.get("standard_work_days",22),
            "standard_work_hours": emp.get("standard_work_hours",176),
            "standard_monthly_hours": emp.get("standard_monthly_hours",160),
            "commute_allowance": emp.get("commute_allowance",0),
            "housing_allowance": emp.get("housing_allowance",0),
            "family_allowance": emp.get("family_allowance",0),
            "position_allowance": emp.get("position_allowance",0),
            "fixed_allowance": emp.get("fixed_allowance",0),
            "fixed_overtime_amount": emp.get("fixed_overtime_amount",0),
            "transport_allowance": emp.get("transport_allowance",0),
            "phone_allowance": emp.get("phone_allowance",0),
            "project_bonus": emp.get("project_bonus",0),
            "recurring_deductions": emp.get("recurring_deductions",0),
            "social_insurance_eligible": emp.get("social_insurance_eligible",True),
            "employment_insurance_eligible": emp.get("employment_insurance_eligible",True),
            "age_at_fiscal_year_start": emp.get("age_at_fiscal_year_start",0),
            "record_status": "draft", "created_at": now_iso(), "updated_at": now_iso(),
        }
        rcols = ",".join(rec.keys()); rph = ",".join(["%s"]*len(rec))
        execute(f"INSERT INTO {REC}({rcols}) VALUES({rph})", tuple(rec.values()))

    return {"ok": True, "sheet_id": sheet_id, "employee_count": len(employees)}


# ── HTML Pages ──
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
  --accent-dark: #1d4ed8;
  --green: #0f766e;
  --amber: #b45309;
  --danger: #b91c1c;
  --focus: rgba(31, 111, 235, 0.18);
  --shadow-soft: 0 1px 2px rgba(15, 23, 42, 0.04);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Hiragino Sans','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.5;color:var(--text);background:var(--page-bg)}
.header{background:linear-gradient(135deg,#14213d,#1e3a5f);color:#fff;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.header h1{font-size:clamp(1.2rem,2.2vw,1.4rem);font-weight:700}
.header a{color:#fff;text-decoration:none;font-size:0.95rem;opacity:.85}
.container{max-width:1400px;margin:0 auto;padding:16px}
.card{background:var(--surface);border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;margin-bottom:16px;border:1px solid var(--border)}
.card-header{background:var(--surface-muted);padding:10px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
table{width:100%;border-collapse:collapse;font-size:1.0rem}
th{text-align:left;padding:12px 10px;border-bottom:2px solid var(--border-strong);color:#555;font-weight:800;white-space:nowrap;background:var(--surface-muted);font-size:0.95rem}
td{padding:10px 10px;border-bottom:1px solid #f0f0f0;vertical-align:middle;line-height:1.5;font-size:1.0rem}
tr:hover{background:#f5f7ff}
.num{text-align:right;font-variant-numeric:tabular-nums}
.btn{padding:10px 18px;border:none;border-radius:8px;font-size:1.0rem;cursor:pointer;font-weight:800;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;min-height:42px;gap:4px}
.btn-primary{background:var(--accent);color:#fff}.btn-success{background:var(--green);color:#fff}.btn-outline{background:var(--surface);color:var(--navy);border:1px solid var(--border)}
.btn-sm{padding:6px 12px;font-size:0.9rem;min-height:34px}.btn-danger{background:var(--danger);color:#fff}
.badge{padding:3px 8px;border-radius:999px;font-size:0.9rem;font-weight:800;display:inline-block}
.badge-draft{background:#fff3e0;color:#e65100}.badge-calculated{background:#e3f2fd;color:#1565c0}
.badge-finalized{background:#dcfce7;color:#166534}
.form-row{display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap;padding:16px}
.field label{display:block;font-size:0.85rem;color:var(--muted);margin-bottom:4px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px}
.field input,.field select{padding:8px 12px;border:1px solid var(--border-strong);border-radius:10px;font-size:1rem;min-height:40px}
.toolbar{background:var(--surface);padding:12px 16px;border-radius:14px;box-shadow:var(--shadow-soft);margin-bottom:16px;border:1px solid var(--border)}
.footer-text{text-align:center;color:var(--muted);font-size:0.85rem;padding:12px}
.empty{text-align:center;color:var(--muted);padding:48px;font-size:1rem}
.nav-breadcrumb{font-size:0.9rem;margin-bottom:12px;color:var(--muted)}
.nav-breadcrumb a{color:var(--navy)}
.badge-voided{background:#f5f5f5;color:#999}
.lang-switch{display:flex;gap:4px}.lang-switch a{padding:4px 10px;border-radius:999px;font-size:0.82rem;color:#fff;text-decoration:none;border:1px solid rgba(255,255,255,.3);font-weight:600}
.lang-switch a.active{background:rgba(255,255,255,.2);border-color:#fff;font-weight:750}
/* Modal */
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.5);z-index:1000;justify-content:center;align-items:center}
.modal-overlay.active{display:flex}
.modal-box{background:var(--surface);border-radius:14px;padding:24px;min-width:360px;max-width:480px;box-shadow:0 8px 32px rgba(0,0,0,.2)}
.modal-box h2{font-size:1.1rem;color:var(--danger);margin-bottom:12px}
.modal-box p{font-size:1rem;color:#555;margin-bottom:20px;line-height:1.5}
.modal-actions{display:flex;gap:12px;justify-content:flex-end}
.modal-actions .btn-no{background:#e0e0e0;color:#333;min-width:80px}
.modal-actions .btn-yes{background:var(--danger);color:#fff;min-width:80px}
.editable{background:#FFF9C4!important;cursor:text;border:1px solid #F9A825;border-radius:4px;padding:4px 6px;font-size:0.9rem;text-align:right;width:80px}
.editable:focus{outline:2px solid #FF6F00;background:#FFF176}.readonly{background:#F5F5F5!important;color:#BDBDBD!important;cursor:not-allowed;border:none;padding:4px 6px;font-size:0.9rem;text-align:right;width:80px}
.summary-bar{background:var(--navy);color:#fff;padding:14px 18px;border-radius:14px;margin:16px 0;display:flex;gap:24px;flex-wrap:wrap}
.summary-bar .val{font-size:1.5rem;font-weight:700}.summary-bar .lbl{font-size:0.85rem;opacity:.8}
.btn-calc{background:#e65100;color:#fff;padding:10px 24px;font-size:1rem;font-weight:800;border-radius:8px}
.record-card{background:var(--surface);border-radius:14px;box-shadow:var(--shadow-soft);padding:20px;margin-bottom:16px;border:1px solid var(--border)}
.section-title{font-size:1.1rem;font-weight:700;color:var(--navy);padding:8px 0;border-bottom:2px solid var(--border);margin-bottom:12px}
.form-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:16px}
.result-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
.result-card{background:var(--surface-muted);border-radius:10px;padding:12px 16px;border:1px solid var(--border)}
.result-card .lbl{font-size:0.85rem;color:var(--muted);margin-bottom:4px}
.result-card .val{font-size:1.2rem;font-weight:700;color:var(--navy)}
.btn-edit-active{background:#e65100!important;color:#fff!important}.filter-bar{background:var(--surface);padding:10px 14px;border-radius:12px;margin-bottom:12px;border:1px solid var(--border)}
/* Sticky columns — 社員番号 + 氏名 水平滚动时保持可见 */
thead th.sticky-col1{position:sticky;left:0;z-index:3;background:var(--surface-muted)}
thead th.sticky-col2{position:sticky;left:80px;z-index:3;background:var(--surface-muted)}
tbody td.sticky-col1{position:sticky;left:0;z-index:2;background:#fff}
tbody td.sticky-col2{position:sticky;left:80px;z-index:2;background:#fff}
tr:hover td.sticky-col1,tr:hover td.sticky-col2{background:#f5f7ff}
thead th.sticky-col2,tbody td.sticky-col2{box-shadow:2px 0 5px -2px rgba(0,0,0,0.12)}
</style>"""


def lang_switcher(lang: str, path: str) -> str:
    parts = []
    for l in SUPPORTED_LANGS:
        active = 'class="active"' if l == lang else ""
        parts.append(f'<a href="{path}?lang={l}" {active}>{l.upper()}</a>')
    return f'<div class="lang-switch">{"".join(parts)}</div>'


def status_badge(s: str, msgs: dict) -> str:
    cls_map = {"draft":"badge-draft","calculated":"badge-calculated","finalized":"badge-finalized",
               "hr_confirmed":"badge-calculated","approved":"badge-finalized","voided":"badge-voided",
               "confirmed":"badge-finalized"}
    cls = cls_map.get(s, "")
    label = t(msgs, f"status.{s}", s)
    return f'<span class="badge {cls}" style="font-size:0.9rem;padding:4px 12px">{label}</span>'


def money_fmt(v):
    if v is None or v==0: return "-"
    return f"¥{int(v):,}"


def sval(v):
    if v is None: return ""
    if isinstance(v, float) and v == 0: return ""
    if isinstance(v, int) and v == 0: return ""
    return str(v)


@router.get("/page/list", response_class=HTMLResponse)
async def sheets_list_page(request: Request):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    rows = fetch_all(f"SELECT * FROM {SHT} ORDER BY payroll_month DESC, sheet_id")

    parts = [f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><title>{t(msgs,'monthly.title')} — {t(msgs,'app.title')}</title>{STYLE}</head><body>
<div class="header"><div><h1>📅 {t(msgs,'monthly.title')}</h1></div><div>{lang_switcher(lang,'/api/monthly-sheets/page/list')}<a href="/" style="color:#fff">🏠</a></div></div>
<div class="container"><div class="nav-breadcrumb"><a href="/">🏠 {t(msgs,'nav.dashboard')}</a> » <strong>{t(msgs,'monthly.title')}</strong></div>
<div class="toolbar"><form method="get" action="/api/monthly-sheets/page/create" style="display:flex;gap:12px;align-items:flex-end">
<div class="field"><label>{t(msgs,'monthly.month')}</label><input name="month" value="2026-06" style="width:120px"></div>
<div class="field"><label>{t(msgs,'monthly.entity')}</label><select name="entity_id"><option value="ENT-0004">TAKK - Tech Alliance株式会社</option></select></div>
<input type="hidden" name="lang" value="{lang}">
<button class="btn btn-success">{t(msgs,'monthly.create_new')}</button>
</form></div>"""]

    if not rows:
        parts.append(f'<div class="card"><div class="empty">{t(msgs,"monthly.no_sheets")}</div></div>')
    else:
        parts.append(f'<div class="card"><table><tr><th>{t(msgs,"monthly.sheet_id")}</th><th>{t(msgs,"monthly.month")}</th><th>{t(msgs,"monthly.entity")}</th><th>{t(msgs,"monthly.employee_count")}</th><th>{t(msgs,"monthly.standard_days")}</th><th>{t(msgs,"monthly.status")}</th><th>{t(msgs,"monthly.created_date")}</th><th></th></tr>')
        for r in rows:
            is_voided = r['status'] == 'voided'
            actions = f"<a class='btn btn-primary' href='/api/monthly-sheets/page/detail?sheet_id={r['sheet_id']}&lang={lang}' style='font-size:0.9rem;padding:8px 16px'>{t(msgs,'monthly.detail_calc')}</a>"
            if is_voided:
                actions += f" <button class='btn btn-danger' onclick='confirmDelete(\"{r['sheet_id']}\")' style='font-size:0.9rem;padding:8px 16px'>{t(msgs,'monthly.delete')}</button>"
            else:
                actions += f" <button class='btn btn-danger' onclick='confirmVoid(\"{r['sheet_id']}\")' style='font-size:0.9rem;padding:8px 16px'>{t(msgs,'monthly.void')}</button>"
            if r['status'] == 'confirmed':
                actions += f" <a class='btn' href='/release/{r['sheet_id']}?lang={lang}' style='background:#6a1b9a;color:#fff;font-size:0.9rem;padding:8px 16px;font-weight:700'>{t(msgs,'monthly.release')}</a>"
            parts.append(f"<tr><td><a href='/api/monthly-sheets/page/detail?sheet_id={r['sheet_id']}&lang={lang}' style='font-weight:600;color:var(--accent)'>{r['sheet_id']}</a></td><td>{r['payroll_month']}</td><td>{r['entity_id']}</td><td class='num'>{r['employee_count']}</td><td class='num'>{r['standard_work_days']}{t(msgs,'monthly.standard_days')[-2:] if lang=='ja' else ' days'}</td><td>{status_badge(r['status'], msgs)}</td><td>{str(r['created_at'])[:10]}</td><td>{actions}</td></tr>")
        parts.append(f'</table></div><div class="footer-text">{t(msgs,"general.records", count=str(len(rows)))}</div>')

    # Modal JS strings
    void_title = t(msgs, "monthly.confirm_void_title")
    void_msg_tmpl = t(msgs, "monthly.confirm_void_msg", sheet_id="__SID__")
    delete_title = t(msgs, "monthly.confirm_delete_title")
    delete_msg_tmpl = t(msgs, "monthly.confirm_delete_msg", sheet_id="__SID__")
    void_ok = t(msgs, "monthly.void_success", sheet_id="__SID__")
    void_fail = t(msgs, "monthly.void_fail")
    delete_ok = t(msgs, "monthly.delete_success", sheet_id="__SID__")
    delete_fail = t(msgs, "monthly.delete_fail")

    parts.append(f"""<div class="modal-overlay" id="confirmModal">
<div class="modal-box"><h2 id="modalTitle">{void_title}</h2><p id="modalMsg"></p>
<div class="modal-actions"><button class="btn btn-no" onclick="closeModal()">{t(msgs,'monthly.confirm_no')}</button><button class="btn btn-yes" id="modalYes">{t(msgs,'monthly.confirm_yes')}</button></div></div></div>
<script>
var pendingAction = null;
function confirmVoid(sheetId) {{
  pendingAction = {{type:'void',sheetId:sheetId}};
  document.getElementById('modalTitle').textContent = '{void_title}';
  document.getElementById('modalMsg').textContent = '{void_msg_tmpl}'.replace('__SID__', sheetId);
  document.getElementById('confirmModal').classList.add('active');
}}
function confirmDelete(sheetId) {{
  pendingAction = {{type:'delete',sheetId:sheetId}};
  document.getElementById('modalTitle').textContent = '{delete_title}';
  document.getElementById('modalMsg').textContent = '{delete_msg_tmpl}'.replace('__SID__', sheetId);
  document.getElementById('confirmModal').classList.add('active');
}}
function closeModal() {{ pendingAction = null; document.getElementById('confirmModal').classList.remove('active'); }}
document.getElementById('modalYes').addEventListener('click', async function() {{
  if (!pendingAction) return;
  var a = pendingAction; pendingAction = null;
  document.getElementById('confirmModal').classList.remove('active');
  var url = '/api/monthly-sheets/'+a.sheetId+(a.type==='void'?'/void':'');
  var method = a.type==='void'?'POST':'DELETE';
  var resp = await fetch(url, {{method:method}});
  var data = await resp.json();
  if (resp.ok) {{
    alert(('{void_ok}').replace('__SID__', a.sheetId));
    location.reload();
  }} else {{
    alert('{void_fail}: '+(data.detail||JSON.stringify(data)));
  }}
}});
document.getElementById('confirmModal').addEventListener('click', function(e) {{ if (e.target===this) closeModal(); }});
</script>""")

    parts.append('</div></body></html>')
    return HTMLResponse("\n".join(parts))


@router.get("/page/create", response_class=HTMLResponse)
async def sheets_create_page(request: Request, month: str="2026-06", entity_id: str="ENT-0004"):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    sheet_id = f"MSS-JP-{month}-{entity_id}"
    already_msg = t(msgs, "monthly.already_exists", sheet_id=sheet_id, count="N")
    already_msg_parts = already_msg.split("N")

    return HTMLResponse(f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><title>{t(msgs,'btn.create')}...</title></head><body>
<form id="f" style="display:none"><input name="sheet_id" value="{sheet_id}"></form>
<script>
async function create() {{
  const check = await fetch('/api/monthly-sheets/{sheet_id}');
  if (check.ok) {{
    const d = await check.json();
    alert('{already_msg_parts[0]}'+d.sheet.employee_count+'{already_msg_parts[1] if len(already_msg_parts) > 1 else ""}');
    window.location.href = '/api/monthly-sheets/page/detail?sheet_id={sheet_id}&lang={lang}';
    return;
  }}
  const resp = await fetch('/api/monthly-sheets/create', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{payroll_month:'{month}', entity_id:'{entity_id}', created_by:'HR'}})
  }});
  const data = await resp.json();
  if (resp.ok) {{
    alert('✅ '+data.sheet_id+' ('+data.employee_count+' {t(msgs,'monthly.employee_count')[:-1] if lang=='ja' else 'employees'})');
    window.location.href = '/api/monthly-sheets/page/detail?sheet_id='+data.sheet_id+'&lang={lang}';
  }} else {{
    alert('❌ '+(data.detail||JSON.stringify(data)));
    window.location.href = '/api/monthly-sheets/page/list?lang={lang}';
  }}
}}
create();
</script></body></html>""")


@router.get("/page/detail", response_class=HTMLResponse)
async def sheets_detail_page(request: Request, sheet_id: str, department: str="", team: str=""):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if not s: return HTMLResponse("<h2>Not found</h2>", status_code=404)

    dept_rows = fetch_all(f"SELECT DISTINCT department_label FROM {REC} WHERE sheet_id=%s AND department_label IS NOT NULL AND department_label != '' ORDER BY department_label", (sheet_id,))
    team_rows = fetch_all(f"SELECT DISTINCT team_label FROM {REC} WHERE sheet_id=%s AND team_label IS NOT NULL AND team_label != '' ORDER BY team_label", (sheet_id,))

    where = ["sheet_id=%s"]; params = [sheet_id]
    if department: where.append("department_label=%s"); params.append(department)
    if team: where.append("team_label=%s"); params.append(team)
    records = fetch_all(f"SELECT * FROM {REC} WHERE {' AND '.join(where)} ORDER BY employee_number", tuple(params))

    dept_opts = f"<option value=''>{t(msgs,'monthly.filter_all_dept')}</option>" + "".join(f'<option value="{r["department_label"]}" {"selected" if department==r["department_label"] else ""}>{r["department_label"]}</option>' for r in dept_rows)
    team_opts = f"<option value=''>{t(msgs,'monthly.filter_all_team')}</option>" + "".join(f'<option value="{r["team_label"]}" {"selected" if team==r["team_label"] else ""}>{r["team_label"]}</option>' for r in team_rows)

    # Table headers with i18n
    th = lambda k: t(msgs, k)

    parts = [f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><title>{sheet_id}</title>{STYLE}
<style>.filter-bar{{background:var(--surface);padding:10px 14px;border-radius:12px;margin-bottom:12px;border:1px solid var(--border)}}</style></head><body>
<div class="header"><div><h1>📋 {sheet_id}</h1><span style="font-size:0.9rem;opacity:.85">{th('monthly.month')}:{s['payroll_month']} | {th('monthly.entity')}:{s['entity_id']} | {th('monthly.standard_days')}:{s['standard_work_days']}日/{s['standard_work_hours']}h | {status_badge(s['status'],msgs)}</span></div>
<div>{lang_switcher(lang,f'/api/monthly-sheets/page/detail?sheet_id={sheet_id}')}<a href="/api/monthly-sheets/page/list?lang={lang}" style="color:#fff">← {th('monthly.back_to_sheet')}</a></div></div>
<div class="container"><div class="filter-bar"><form method="get" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<input type="hidden" name="sheet_id" value="{sheet_id}"><input type="hidden" name="lang" value="{lang}">
<strong style="font-size:0.95rem">{th('monthly.filter_dept')}</strong>
<select name="department" onchange="this.form.submit()">{dept_opts}</select>
<select name="team" onchange="this.form.submit()">{team_opts}</select>
<span style="font-size:0.9rem;color:var(--muted);margin-left:8px">{len(records)} {th('monthly.employee_count')[:-1] if lang=='ja' else ''}</span>
<button type="button" class="btn btn-outline btn-sm" id="btnEditMode" onclick="toggleEditMode()" style="margin-left:auto">{th('monthly.edit_data')}</button>
<button type="button" class="btn btn-success btn-sm" id="btnSave" onclick="saveAll()" style="display:none">{th('monthly.bulk_save')}</button>
<button type="button" class="btn btn-calc" onclick="calculate()">{th('monthly.run_calc')}</button>
<button type="button" class="btn btn-primary btn-sm" onclick="confirmSheet()" id="btnConfirm" style="background:#2e7d32;display:{'inline-block' if s['status']=='calculated' else 'none'}">{th('monthly.confirm_sheet')}</button>
<a href="/release/{sheet_id}?lang={lang}" class="btn btn-primary btn-sm" id="btnRelease" style="background:#6a1b9a;display:{'inline-block' if s['status']=='confirmed' else 'none'}">{th('monthly.goto_release')}</a>
</form></div>"""]

    if s['status'] == 'confirmed':
        parts.append(f"""<div style="background:linear-gradient(135deg,#6a1b9a,#9c27b0);color:#fff;padding:16px 20px;border-radius:10px;margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
<div><div style="font-size:1.15rem;font-weight:700">{th('monthly.release_ready_title')}</div><div style="font-size:0.9rem;opacity:.9">{th('monthly.release_ready_desc')}</div></div>
<a href="/release/{sheet_id}?lang={lang}" class="btn btn-primary" style="background:#fff;color:#6a1b9a;font-size:16px;font-weight:700;padding:14px 28px;border-radius:10px;text-decoration:none;box-shadow:0 4px 12px rgba(0,0,0,.2)">{th('monthly.release_goto')}</a>
</div>""")

    parts.append(f"""<div class="card"><div style="overflow-x:auto"><table><thead><tr>
<th class="sticky-col1" style="width:80px">{th('monthly.table_emp_no')}</th><th class="sticky-col2" style="width:90px">{th('monthly.table_name')}</th><th style="width:55px">{th('monthly.table_type')}</th>
<th style="width:50px;background:#e8f5e9">{th('monthly.table_std_days')}</th><th style="width:50px;background:#fff9c4">{th('monthly.table_work_days')}</th><th style="width:42px;background:#fff9c4">{th('monthly.table_paid_leave')}</th><th style="width:42px;background:#fff9c4">{th('monthly.table_sick_leave')}</th><th style="width:50px;background:#fff9c4">{th('monthly.table_work_hours')}</th><th style="width:48px;background:#fff9c4">{th('monthly.table_ot_hours')}</th><th style="width:48px;background:#fff9c4">{th('monthly.table_night_hours')}</th>
<th style="width:70px">{th('monthly.table_basic_salary')}</th><th style="width:55px">{th('monthly.table_hourly_rate')}</th><th style="width:65px">{th('monthly.table_commute')}</th><th style="width:65px">{th('monthly.table_housing')}</th><th style="width:65px">{th('monthly.table_transport')}</th><th style="width:55px">{th('monthly.table_phone')}</th><th style="width:75px">{th('monthly.table_project_bonus')}</th>
<th style="width:70px;background:#e3f2fd">{th('monthly.table_gross')}</th><th style="width:45px"></th>
<th style="width:60px;background:#fce4ec">{th('monthly.table_health_ins')}</th><th style="width:60px;background:#fce4ec">{th('monthly.table_pension')}</th><th style="width:52px;background:#fce4ec">{th('monthly.table_employment')}</th><th style="width:62px;background:#fce4ec">{th('monthly.table_income_tax')}</th><th style="width:62px;background:#fce4ec">{th('monthly.table_ded_total')}</th>
<th style="width:72px;background:#e8f5e9">{th('monthly.table_net')}</th>
<th style="width:75px;background:#f3e5f5">{th('monthly.table_employer_cost')}</th>
</tr></thead><tbody>""")

    for r in records:
        st = r.get('salary_type','monthly')
        is_monthly = st == 'monthly'
        is_hourly = st in ('hourly','monthhour')

        def e_attr(key, val, editable, w="65px"):
            # Default to readonly; edit mode toggle switches to editable via JS
            cls = "readonly"
            ro = " readonly"
            editable_flag = "true" if editable else "false"
            return f'class="{cls}" style="width:{w}" data-key="{key}" data-editable="{editable_flag}" value="{val}"{ro}'

        record_edit_url = f"/api/monthly-sheets/page/record-edit?record_id={r['record_id']}&lang={lang}"
        emp_detail_url = f"/api/monthly-sheets/page/record-edit?record_id={r['record_id']}&lang={lang}"
        parts.append(f"""<tr data-rid="{r['record_id']}" data-st="{st}">
<td class="sticky-col1" style="font-size:0.85rem"><a href="{emp_detail_url}" style="font-weight:600;color:var(--accent)" title="{th('monthly.record_edit')}">{r['employee_number']}</a></td>
<td class="sticky-col2" style="font-size:0.9rem"><strong>{r['employee_name']}</strong></td>
<td style="font-size:0.85rem">{st}</td>
<td><input {e_attr("standard_work_days",sval(r.get('standard_work_days')),True,"50px")}></td>
<td><input {e_attr("actual_work_days",sval(r.get('actual_work_days')),is_monthly or st == 'monthly_fixed_ot',"50px")}></td>
<td><input {e_attr("paid_leave_days",sval(r.get('paid_leave_days')),is_monthly,"45px")}></td>
<td><input {e_attr("sick_leave_days",sval(r.get('sick_leave_days')),is_monthly,"45px")}></td>
<td><input {e_attr("actual_work_hours",sval(r.get('actual_work_hours')),is_hourly,"55px")}></td>
<td><input {e_attr("overtime_hours",sval(r.get('overtime_hours')),True,"50px")}></td>
<td><input {e_attr("late_night_hours",sval(r.get('late_night_hours')),True,"50px")}></td>
<td><input {e_attr("basic_salary",sval(r.get('basic_salary')),is_monthly or st in ('monthly_fixed_ot','daily'),"75px")}></td>
<td><input {e_attr("hourly_rate",sval(r.get('hourly_rate')),is_hourly,"60px")}></td>
<td><input {e_attr("commute_allowance",sval(r.get('commute_allowance')),True,"70px")}></td>
<td><input {e_attr("housing_allowance",sval(r.get('housing_allowance')),True,"70px")}></td>
<td><input {e_attr("transport_allowance",sval(r.get('transport_allowance')),True,"70px")}></td>
<td><input {e_attr("phone_allowance",sval(r.get('phone_allowance')),True,"55px")}></td>
<td><input {e_attr("project_bonus",sval(r.get('project_bonus')),True,"80px")}></td>
<td class="num" style="font-weight:600;color:#1a237e">{money_fmt(r.get('gross_pay'))}</td>
<td style="white-space:nowrap"><a href="{record_edit_url}" class="btn btn-outline btn-sm" style="font-size:0.8rem;padding:4px 8px" title="{th('monthly.record_edit')}">✏️</a></td>
<td class="num" style="color:#c62828">{money_fmt(r.get('health_insurance_employee'))}</td>
<td class="num" style="color:#c62828">{money_fmt(r.get('pension_employee'))}</td>
<td class="num" style="color:#c62828">{money_fmt(r.get('employment_insurance_employee'))}</td>
<td class="num" style="color:#c62828">{money_fmt(r.get('income_tax'))}</td>
<td class="num" style="color:#c62828">{money_fmt(r.get('deduction_total'))}</td>
<td class="num" style="font-weight:700;color:#2e7d32;font-size:1rem">{money_fmt(r.get('net_pay'))}</td>
<td class="num" style="font-size:0.85rem;color:var(--muted)">{money_fmt(r.get('employer_cost_total'))}</td>
</tr>""")

    parts.append(f"""</tbody></table></div></div>
<div class="summary-bar"><div class="item"><div class="val" id="sumGross">-</div><div class="lbl">{th('monthly.summary_gross')}</div></div>
<div class="item"><div class="val" id="sumSI">-</div><div class="lbl">{th('monthly.summary_si')}</div></div>
<div class="item"><div class="val" id="sumTax">-</div><div class="lbl">{th('monthly.summary_tax')}</div></div>
<div class="item"><div class="val" id="sumDed">-</div><div class="lbl">{th('monthly.summary_ded')}</div></div>
<div class="item"><div class="val" id="sumNet">-</div><div class="lbl">{th('monthly.summary_net')}</div></div>
<div class="item"><div class="val" id="sumEmployer">-</div><div class="lbl">{th('monthly.summary_employer')}</div></div>
</div><div class="footer-text">{t(msgs,"general.records", count=str(len(records)))} | {th('monthly.edit_hint_yellow')} | {th('monthly.edit_hint_gray')}</div></div>

<script>
var editMode = false;
var labelEdit = "{th('monthly.edit_data')}";
var labelExit = "{th('monthly.exit_edit')}";

function toggleEditMode() {{
  editMode = !editMode;
  var btn = document.getElementById('btnEditMode');
  var btnSave = document.getElementById('btnSave');
  if (editMode) {{
    btn.textContent = labelExit;
    btn.classList.add('btn-edit-active');
    btnSave.style.display = 'inline-flex';
    document.querySelectorAll('input[data-editable="true"]').forEach(function(inp) {{
      inp.classList.remove('readonly');
      inp.classList.add('editable');
      inp.removeAttribute('readonly');
    }});
  }} else {{
    btn.textContent = labelEdit;
    btn.classList.remove('btn-edit-active');
    btnSave.style.display = 'none';
    document.querySelectorAll('input.editable').forEach(function(inp) {{
      inp.classList.remove('editable');
      inp.classList.add('readonly');
      inp.setAttribute('readonly', '');
    }});
  }}
}}

function sval(v){{return v===null||v===undefined||v===0?'':String(v);}}
function money_fmt(v){{if(!v||v===0)return'-';return '¥'+Math.round(v).toLocaleString();}}

var calcConfirmMsg = "{th('monthly.calc_confirm_msg')}";
var calcFailMsg = "{th('monthly.calc_fail')}";
var confirmMsg = "{th('monthly.confirm_msg')}";
var confirmSuccess = "{th('monthly.confirm_success')}";
var bulkSaveSuccess = "{th('monthly.bulk_save_success')}";
var bulkSaveFail = "{th('monthly.bulk_save_fail')}";

async function confirmSheet(){{if(!confirm(confirmMsg))return;var r=await fetch('/api/monthly-sheets/{sheet_id}/confirm',{{method:'POST'}});var d=await r.json();if(r.ok){{alert(confirmSuccess);location.reload();}}else{{alert('❌ '+(d.detail||JSON.stringify(d)));}}}}

function nvl(td){{var t=(td.textContent||'').replace(/[^0-9.-]/g,'');var n=parseFloat(t);return isNaN(n)?0:n;}}
function updateSummary(){{var g=0,si=0,tax=0,ded=0,n=0,emp=0;document.querySelectorAll('[data-rid]').forEach(function(tr){{var tds=tr.querySelectorAll('td.num');if(tds.length>=10){{g+=nvl(tds[0]);si+=nvl(tds[1])+nvl(tds[2])+nvl(tds[3]);tax+=nvl(tds[4]);ded+=nvl(tds[5]);n+=nvl(tds[6]);emp+=nvl(tds[7]);}}}});document.getElementById('sumGross').textContent=money_fmt(g);document.getElementById('sumSI').textContent=money_fmt(si);document.getElementById('sumTax').textContent=money_fmt(tax);document.getElementById('sumDed').textContent=money_fmt(ded);document.getElementById('sumNet').textContent=money_fmt(n);document.getElementById('sumEmployer').textContent=money_fmt(emp);}}
updateSummary();

async function saveAll(){{if(!editMode)return;var recs=[];document.querySelectorAll('[data-rid]').forEach(function(tr){{var rec={{record_id:tr.dataset.rid}};tr.querySelectorAll('input.editable').forEach(function(inp){{var v=inp.value;rec[inp.dataset.key]=v===''?null:parseFloat(v)||0;}});recs.push(rec);}});if(recs.length===0)return;var resp=await fetch('/api/monthly-sheets/records/bulk-save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{records:recs}})}});var d=await resp.json();if(resp.ok){{alert(bulkSaveSuccess.replace('{{count}}',d.saved));location.reload();}}else{{alert(bulkSaveFail+': '+(d.detail||JSON.stringify(d)));}}}}

async function calculate(){{if(!confirm(calcConfirmMsg))return;var resp=await fetch('/api/monthly-sheets/{sheet_id}/calculate',{{method:'POST'}});var d=await resp.json();if(resp.ok){{alert('✅ '+d.calculated+' records\\nGross: '+money_fmt(d.gross_total)+'\\nNet: '+money_fmt(d.net_total));location.reload();}}else{{alert(calcFailMsg+': '+(d.detail||JSON.stringify(d)));}}}}
</script></body></html>""")
    return HTMLResponse("\n".join(parts))


# ── Single Record Edit Page ──

@router.get("/page/record-edit", response_class=HTMLResponse)
async def record_edit_page(request: Request, record_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    th = lambda k: t(msgs, k)

    r = fetch_one(f"SELECT * FROM {REC} WHERE record_id=%s", (record_id,))
    if not r: return HTMLResponse("<h2>Not found</h2>", status_code=404)
    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (r["sheet_id"],))
    is_locked = s and s.get("status") not in ("draft",)

    st = r.get("salary_type", "monthly")
    is_monthly = st == "monthly"
    is_hourly = st in ("hourly", "monthhour")

    def field_row(label, key, val, editable=True, w="200px", typ="number"):
        cls = "editable" if editable and not is_locked else "readonly"
        ro = " readonly" if (not editable or is_locked) else ""
        bg = "#FFF9C4" if (editable and not is_locked) else "#F5F5F5"
        color = "" if (editable and not is_locked) else "color:#BDBDBD"
        display_val = sval(val)
        return f"""<div class="field">
<label>{label}</label>
<input type="{typ}" name="{key}" value="{display_val}" class="{cls}"
 style="width:{w};padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:1rem;background:{bg};{color}"{ro}>
</div>"""

    back_url = f"/api/monthly-sheets/page/detail?sheet_id={r['sheet_id']}&lang={lang}"

    html = f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><title>{r['employee_name']} — {th('monthly.record_edit')}</title>{STYLE}
<style>.record-card .editable{{background:#FFF9C4!important;cursor:text;border:1px solid #F9A825!important;border-radius:8px;padding:8px 12px;font-size:1rem;text-align:right}}
.record-card .editable:focus{{outline:2px solid #FF6F00;background:#FFF176}}
.record-card .readonly{{background:#F5F5F5!important;color:#BDBDBD!important;cursor:not-allowed;border:1px solid #ddd!important;padding:8px 12px;font-size:1rem;text-align:right}}
</style></head><body>
<div class="header"><div><h1>✏️ {th('monthly.record_edit_title')}</h1><span style="font-size:0.95rem;opacity:.85">{r['employee_number']} — {r['employee_name']} | {r.get('payroll_month','')}</span></div>
<div>{lang_switcher(lang,f'/api/monthly-sheets/page/record-edit?record_id={record_id}')}<a href="{back_url}" style="color:#fff">{th('monthly.back_to_sheet')}</a></div></div>
<div class="container">

<div class="record-card">
<div class="section-title">{th('section.basic_info')}</div>
<div class="form-grid">
<div class="field"><label>{th('monthly.table_emp_no')}</label><input value="{r['employee_number']}" readonly style="background:#F5F5F5;color:#999;width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:1rem"></div>
<div class="field"><label>{th('monthly.table_name')}</label><input value="{r['employee_name']}" readonly style="background:#F5F5F5;color:#999;width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:1rem"></div>
<div class="field"><label>{th('monthly.table_type')}</label><input value="{st}" readonly style="background:#F5F5F5;color:#999;width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:1rem"></div>
<div class="field"><label>{th('salary_master.department')}</label><input value="{r.get('department_label','')} / {r.get('team_label','')}" readonly style="background:#F5F5F5;color:#999;width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:1rem"></div>
</div></div>

<div class="record-card">
<div class="section-title">{th('monthly.section.attendance')}</div>
<div class="form-grid">
{field_row(th('label.standard_work_days'),"standard_work_days",r.get('standard_work_days'),True,"150px")}
{field_row(th('monthly.table_work_days'),"actual_work_days",r.get('actual_work_days'),is_monthly or st=='monthly_fixed_ot',"150px")}
{field_row(th('monthly.table_paid_leave'),"paid_leave_days",r.get('paid_leave_days'),is_monthly,"150px")}
{field_row(th('monthly.table_sick_leave'),"sick_leave_days",r.get('sick_leave_days'),is_monthly,"150px")}
{field_row(th('monthly.table_work_hours'),"actual_work_hours",r.get('actual_work_hours'),is_hourly,"150px")}
{field_row(th('monthly.table_ot_hours'),"overtime_hours",r.get('overtime_hours'),True,"150px")}
{field_row(th('monthly.table_night_hours'),"late_night_hours",r.get('late_night_hours'),True,"150px")}
</div></div>

<div class="record-card">
<div class="section-title">{th('monthly.section.allowance')}</div>
<div class="form-grid">
{field_row(th('salary_master.basic_salary'),"basic_salary",r.get('basic_salary'),is_monthly or st in ('monthly_fixed_ot','daily'),"180px")}
{field_row(th('salary_master.hourly_rate'),"hourly_rate",r.get('hourly_rate'),is_hourly,"180px")}
{field_row(th('label.commute_allowance'),"commute_allowance",r.get('commute_allowance'),True,"180px")}
{field_row(th('label.housing_allowance'),"housing_allowance",r.get('housing_allowance'),True,"180px")}
{field_row(th('label.transport_allowance'),"transport_allowance",r.get('transport_allowance'),True,"180px")}
{field_row(th('label.phone_allowance'),"phone_allowance",r.get('phone_allowance'),True,"180px")}
{field_row(th('label.project_bonus'),"project_bonus",r.get('project_bonus'),True,"180px")}
{field_row(th('label.performance_bonus'),"performance_bonus",r.get('performance_bonus'),True,"180px")}
</div></div>

<div class="record-card">
<div class="section-title">{th('monthly.section.deduction')}</div>
<div class="form-grid">
{field_row(th('label.recurring_deductions'),"recurring_deductions",r.get('recurring_deductions'),True,"180px")}
{field_row(th('label.other_deduction'),"other_deduction",r.get('other_deduction'),True,"180px")}
</div></div>
"""

    if r.get("gross_pay") or r.get("net_pay"):
        html += f"""<div class="record-card">
<div class="section-title">{th('monthly.section.result')}</div>
<div class="result-grid">
<div class="result-card"><div class="lbl">{th('payslip.item.basic_salary')}</div><div class="val">{money_fmt(r.get('base_pay_calculated'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.gross_pay')}</div><div class="val" style="color:#1a237e">{money_fmt(r.get('gross_pay'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.health_insurance')}</div><div class="val" style="color:#c62828">{money_fmt(r.get('health_insurance_employee'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.pension')}</div><div class="val" style="color:#c62828">{money_fmt(r.get('pension_employee'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.employment_insurance')}</div><div class="val" style="color:#c62828">{money_fmt(r.get('employment_insurance_employee'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.income_tax')}</div><div class="val" style="color:#c62828">{money_fmt(r.get('income_tax'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.deduction_total')}</div><div class="val" style="color:#c62828">{money_fmt(r.get('deduction_total'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.net_pay')}</div><div class="val" style="color:#2e7d32;font-size:1.5rem">{money_fmt(r.get('net_pay'))}</div></div>
<div class="result-card"><div class="lbl">{th('payslip.item.employer_cost')}</div><div class="val" style="color:var(--muted)">{money_fmt(r.get('employer_cost_total'))}</div></div>
</div></div>"""

    html += f"""<div style="display:flex;gap:12px;justify-content:flex-end;margin-top:16px">
<a class="btn btn-outline" href="{back_url}">{th('btn.cancel')}</a>
<button class="btn btn-success" onclick="saveRecord('{r['record_id']}')" style="font-size:1.1rem;padding:12px 28px">{th('btn.save')}</button>
</div>
</div>
<script>
function sval(v){{return v===null||v===undefined||v===0?'':String(v);}}
function saveRecord(rid) {{
  var rec = {{record_id: rid}};
  document.querySelectorAll('input.editable').forEach(function(inp) {{
    var v = inp.value;
    rec[inp.name] = v === '' ? null : parseFloat(v) || 0;
  }});
  fetch('/api/monthly-sheets/records/bulk-save', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{records: [rec]}})
  }}).then(r => r.json()).then(d => {{
    if (d.saved) {{ alert('{th("save.success")}'); window.location.href = '{back_url}'; }}
    else {{ alert('{th("save.error")}: '+JSON.stringify(d)); }}
  }});
}}
</script></body></html>"""
    return HTMLResponse(html)


# ── Single sheet API (after page routes to avoid path conflicts) ──

@router.get("/{sheet_id}")
async def get_sheet(sheet_id: str):
    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if not s: raise HTTPException(404, "Not found")
    records = fetch_all(f"SELECT * FROM {REC} WHERE sheet_id=%s ORDER BY employee_number", (sheet_id,))
    return {"sheet": s, "records": records, "count": len(records)}


# ── Bulk Save & Calculate APIs ──

@router.post("/records/bulk-save")
async def bulk_save_records(request: Request):
    body = await request.json()
    records = body.get("records", [])
    allowed = {"basic_salary","hourly_rate","daily_rate","standard_work_days","standard_work_hours",
               "standard_monthly_hours","actual_work_days","actual_work_hours","paid_leave_days",
               "unpaid_leave_days","sick_leave_days","overtime_hours","late_night_hours","holiday_hours",
               "absence_days","commute_allowance","housing_allowance","family_allowance",
               "position_allowance","fixed_allowance","performance_bonus","bonus","other_payment",
               "transport_allowance","phone_allowance","project_bonus",
               "fixed_overtime_amount","recurring_deductions","other_deduction"}
    saved = 0
    for rec in records:
        rid = rec.pop("record_id", None)
        if not rid: continue
        updates = {k: v for k, v in rec.items() if k in allowed}
        if not updates: continue
        updates["updated_at"] = now_iso()
        sets = ",".join(f"{k}=%s" for k in updates)
        execute(f"UPDATE {REC} SET {sets} WHERE record_id=%s", tuple(updates.values()) + (rid,))
        saved += 1
    return {"ok": True, "saved": saved}

@router.post("/{sheet_id}/calculate")
async def calculate_sheet(sheet_id: str):
    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if not s: raise HTTPException(404, "Sheet not found")
    records = fetch_all(f"SELECT * FROM {REC} WHERE sheet_id=%s", (sheet_id,))
    from services.calculation import calc_salary_preview

    si_rates = fetch_all("SELECT * FROM pay_jp_social_insurance_rates WHERE is_current=true")
    tax_brackets = fetch_all("SELECT * FROM pay_jp_withholding_tax_brackets WHERE is_current=true AND table_type='monthly' ORDER BY min_salary")
    grades = fetch_all("SELECT * FROM pay_jp_standard_remuneration_grades WHERE is_current=true")

    def get_rate(rate_type, pref=None):
        for r in si_rates:
            if r["rate_type"] == rate_type:
                if r["prefecture"] is None or r["prefecture"] == pref:
                    return float(r["employee_rate"]), float(r["employer_rate"])
        return 0.0, 0.0

    def lookup_tax(monthly_pay, deps):
        for b in tax_brackets:
            if b["min_salary"] <= monthly_pay < b["max_salary"]:
                dep_key = f"tax_dep_{min(deps,7)}"
                return float(b.get(dep_key, 0))
        return 0.0

    gross_total = 0; net_total = 0; si_employee_total = 0; tax_total = 0
    ded_total = 0; emp_total = 0; calculated = 0

    for r in records:
        st = r.get("salary_type","monthly")
        actual_h = float(r.get("actual_work_hours") or 0)
        actual_d = float(r.get("actual_work_days") or 0)

        preview = calc_salary_preview(r, actual_hours=actual_h, actual_days=actual_d)
        base_pay = preview.get("base_pay", 0)

        gross = preview.get("gross_pay", 0)
        gross += float(r.get("commute_allowance") or 0) + float(r.get("housing_allowance") or 0)
        gross += float(r.get("family_allowance") or 0) + float(r.get("position_allowance") or 0)
        gross += float(r.get("fixed_allowance") or 0) + float(r.get("fixed_overtime_amount") or 0)
        gross += float(r.get("performance_bonus") or 0) + float(r.get("bonus") or 0)
        gross += float(r.get("transport_allowance") or 0) + float(r.get("phone_allowance") or 0)
        gross += float(r.get("project_bonus") or 0)

        si_eligible = r.get("social_insurance_eligible", True)
        prefecture = str(r.get("prefecture_code", "13"))[:2]
        health_emp_rate, health_emr_rate = get_rate("health", prefecture) if si_eligible else (0,0)
        pension_emp_rate, pension_emr_rate = get_rate("pension") if si_eligible else (0,0)
        nursing_care_age = int(r.get("age_at_fiscal_year_start") or 0)
        if nursing_care_age == 0 and r.get("employee_id"):
            sm = fetch_one("SELECT age_at_fiscal_year_start FROM pay_jp_salary_master WHERE employee_id=%s", (r["employee_id"],))
            if sm and sm.get("age_at_fiscal_year_start"):
                nursing_care_age = int(sm["age_at_fiscal_year_start"])
        care_emp_rate, care_emr_rate = get_rate("nursing_care") if si_eligible and nursing_care_age >= 40 else (0,0)
        empins_emp_rate, empins_emr_rate = get_rate("employment") if r.get("employment_insurance_eligible", True) else (0,0)
        child_rate, child_emr_rate = get_rate("child_allowance")

        health_emp = int(round(gross * health_emp_rate / 100))
        pension_emp = int(round(gross * pension_emp_rate / 100))
        care_emp = int(round(gross * care_emp_rate / 100))
        empins_emp = int(round(gross * empins_emp_rate / 100))
        si_employee = health_emp + pension_emp + care_emp + empins_emp

        health_emr = int(round(gross * health_emr_rate / 100))
        pension_emr = int(round(gross * pension_emr_rate / 100))
        care_emr = int(round(gross * care_emr_rate / 100))
        empins_emr = int(round(gross * empins_emr_rate / 100))
        child_emr = int(round(gross * child_emr_rate / 100))
        accident_rate = 0.0035
        accident_emr = int(round(gross * accident_rate))
        employer_cost = int(round(gross + health_emr + pension_emr + care_emr + empins_emr + child_emr + accident_emr))

        taxable = gross - si_employee
        deps = int(r.get("dependents_count") or 0)
        income_tax = lookup_tax(taxable, deps)
        resident_tax = float(r.get("monthly_resident_tax") or 0)

        other_ded = float(r.get("recurring_deductions") or 0) + float(r.get("other_deduction") or 0)
        deduction = int(round(si_employee + income_tax + resident_tax + other_ded))
        net = int(round(gross - deduction))

        execute(f"""UPDATE {REC} SET base_pay_calculated=%s, gross_pay=%s,
            health_insurance_employee=%s, pension_employee=%s, employment_insurance_employee=%s,
            care_insurance_employee=%s, income_tax=%s, deduction_total=%s, net_pay=%s,
            employer_cost_total=%s, calculation_messages=%s, updated_at=%s WHERE record_id=%s""",
            (base_pay, gross, health_emp, pension_emp, empins_emp, care_emp,
             income_tax, deduction, net, employer_cost,
             f"社保(本人): 健保{health_emp:,.0f}+年金{pension_emp:,.0f}+雇用{empins_emp:,.0f}={si_employee:,.0f}; 源泉所得税: {income_tax:,.0f} (課税{taxable:,.0f} 扶養{deps}人)",
             now_iso(), r["record_id"]))

        gross_total += gross; si_employee_total += si_employee; tax_total += income_tax + resident_tax
        ded_total += deduction; net_total += net; emp_total += employer_cost; calculated += 1

    execute(f"UPDATE {SHT} SET gross_total=%s, deduction_total=%s, net_total=%s, employer_cost_total=%s, status='calculated', updated_at=%s WHERE sheet_id=%s",
            (gross_total, ded_total, net_total, emp_total, now_iso(), sheet_id))
    return {"ok": True, "calculated": calculated, "gross_total": gross_total,
            "si_employee": si_employee_total, "deduction_total": ded_total,
            "net_total": net_total, "employer_cost_total": emp_total}


@router.post("/{sheet_id}/confirm")
async def confirm_sheet(sheet_id: str):
    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if not s: raise HTTPException(404, "Sheet not found")
    if s["status"] != "calculated":
        raise HTTPException(400, f"Must be calculated status (current: {s['status']})")
    execute(f"UPDATE {SHT} SET status='confirmed', updated_at=%s WHERE sheet_id=%s", (now_iso(), sheet_id))
    execute(f"UPDATE {REC} SET record_status='confirmed', updated_at=%s WHERE sheet_id=%s", (now_iso(), sheet_id))
    return {"ok": True, "sheet_id": sheet_id, "status": "confirmed"}


@router.post("/{sheet_id}/void")
async def void_sheet(sheet_id: str):
    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if not s: raise HTTPException(404, "Sheet not found")
    if s["status"] == "voided":
        raise HTTPException(400, "Sheet already voided")
    execute(f"UPDATE {SHT} SET status='voided', updated_at=%s WHERE sheet_id=%s", (now_iso(), sheet_id))
    execute(f"UPDATE {REC} SET record_status='voided', updated_at=%s WHERE sheet_id=%s", (now_iso(), sheet_id))
    return {"ok": True, "sheet_id": sheet_id, "status": "voided"}

@router.delete("/{sheet_id}")
async def delete_sheet(sheet_id: str):
    s = fetch_one(f"SELECT * FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    if not s: raise HTTPException(404, "Sheet not found")
    if s["status"] != "voided":
        raise HTTPException(400, "Sheet must be voided before deletion")
    execute(f"DELETE FROM {REC} WHERE sheet_id=%s", (sheet_id,))
    execute(f"DELETE FROM {SHT} WHERE sheet_id=%s", (sheet_id,))
    return {"ok": True, "sheet_id": sheet_id, "deleted": True}
