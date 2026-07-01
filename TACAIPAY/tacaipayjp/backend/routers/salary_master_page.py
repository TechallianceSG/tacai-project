"""Salary Master HTML pages with i18n — 給与マスタ 一覧・閲覧・編集 (zh/ja/en)"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from database import fetch_all, fetch_one
from i18n import t, get_lang, load_i18n, SUPPORTED_LANGS, DEFAULT_LANG
from auth import check_permission

router = APIRouter(tags=["Salary Master Pages"])

SALARY_TYPE_OPTIONS = [
    ("monthly", "salary_master.type_monthly"),
    ("hourly", "salary_master.type_hourly"),
    ("daily", "salary_master.type_daily"),
    ("monthly_fixed_ot", "salary_master.type_fixed_ot"),
    ("monthly_hour", "salary_master.type_monthhour"),
]

SALARY_TYPE_BADGE_CLASS = {
    "monthly": "badge-monthly", "hourly": "badge-hourly",
    "daily": "badge-active", "monthly_fixed_ot": "badge-fixedot",
    "monthly_hour": "badge-fixedot",
}

STYLE = """<style>
:root {
  color-scheme: light;
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
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Hiragino Sans','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.45;color:var(--text);background:var(--page-bg)}
.header{background:linear-gradient(135deg,#14213d,#1e3a5f);color:#fff;padding:14px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.header h1{font-size:clamp(1.15rem,2.2vw,1.35rem);font-weight:700;line-height:1.15;margin:0}
.header a{color:#fff;text-decoration:none;font-size:0.9rem;opacity:.85}.header a:hover{opacity:1}
.lang-switch{display:flex;gap:4px}.lang-switch a{padding:4px 10px;border-radius:999px;font-size:0.82rem;color:#fff;text-decoration:none;border:1px solid rgba(255,255,255,.3);font-weight:600}
.lang-switch a.active{background:rgba(255,255,255,.2);border-color:#fff;font-weight:750}
.container{max-width:1500px;margin:0 auto;padding:16px}
.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:16px;background:var(--surface);padding:12px 16px;border-radius:14px;box-shadow:var(--shadow-soft);border:1px solid var(--border)}
.toolbar input,.toolbar select{padding:8px 12px;border:1px solid var(--border-strong);border-radius:10px;font-size:0.95rem;min-height:40px}
.toolbar input{width:240px}.toolbar select{min-width:140px}
.toolbar input:focus,.toolbar select:focus{outline:3px solid var(--focus);border-color:var(--accent)}
.btn{padding:10px 18px;border:none;border-radius:8px;font-size:1.0rem;cursor:pointer;font-weight:800;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;min-height:42px;gap:4px}
.btn-primary{background:var(--accent);color:#fff}.btn-primary:hover{background:var(--accent-dark)}
.btn-success{background:var(--green);color:#fff}.btn-success:hover{opacity:.9}
.btn-outline{background:var(--surface);color:var(--navy);border:1px solid var(--border);font-weight:700}
.btn-outline:hover{background:var(--surface-muted);color:var(--blue);border-color:var(--blue)}
.btn-sm{padding:6px 12px;font-size:0.85rem;min-height:34px}
.btn-danger{background:var(--danger);color:#fff}
.card{background:var(--surface);border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;border:1px solid var(--border);margin-bottom:16px}
.card-header{background:var(--surface-muted);padding:10px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
table{width:100%;border-collapse:collapse;font-size:0.95rem}
th{text-align:left;padding:10px 8px;border-bottom:2px solid var(--border-strong);color:#555;font-weight:800;white-space:nowrap;position:sticky;top:0;background:var(--surface-muted);font-size:0.9rem}
td{padding:7px 8px;border-bottom:1px solid #f0f0f0;vertical-align:top;line-height:1.4}
tr:hover{background:#f5f7ff}
.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{padding:3px 8px;border-radius:999px;font-size:0.85rem;font-weight:800;display:inline-block}
.badge-active{background:#dcfce7;color:#166534}.badge-inactive{background:#f5f5f5;color:#999}
.badge-monthly{background:#e3f2fd;color:#1565c0}.badge-hourly{background:#fff3e0;color:#e65100}
.badge-fixedot{background:#f3e5f5;color:#7b1fa2}
.chip{display:inline-flex;align-items:center;gap:4px}.chip .dot{width:6px;height:6px;border-radius:50%}
.dot-green{background:#4caf50}.dot-red{background:#f44336}
.empty{text-align:center;color:var(--muted);padding:48px;font-size:1rem}
.footer-text{text-align:center;color:var(--muted);font-size:0.85rem;padding:12px 0}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.form-two-col{display:grid;grid-template-columns:1fr 1fr;gap:0;border-top:1px solid var(--border)}
.form-col{padding:0 8px}
.form-col:first-child{padding-left:0;border-right:1px solid #f0f0f0}
.form-col:last-child{padding-right:0}
@media(max-width:900px){.form-two-col{grid-template-columns:1fr}.form-col:first-child{border-right:none}}
.form-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;padding:12px 16px}
.form-grid-full{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;padding:12px 16px}
.field label{display:block;font-size:0.85rem;color:var(--muted);margin-bottom:2px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px}
.field input,.field select{width:100%;padding:8px 12px;border:1px solid var(--border-strong);border-radius:10px;font-size:1rem;min-height:42px;transition:border-color .15s;background:#fff;color:var(--text)}
.field input:focus,.field select:focus{outline:3px solid var(--focus);border-color:var(--accent)}
.field input[readonly]{background:var(--surface-muted);color:var(--muted)}
.field input[type="checkbox"]{width:auto;min-height:auto}
.field .readonly-hint{font-size:0.75rem;color:var(--muted);margin-top:2px}
.section-title{font-size:1.08rem;font-weight:700;color:var(--navy);padding:10px 16px 6px;border-top:1px solid var(--border);background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%);letter-spacing:0.3px}
.form-actions{padding:16px;display:flex;gap:8px;justify-content:flex-end;border-top:2px solid var(--border-strong);background:var(--surface-muted)}
.nav-breadcrumb{font-size:0.9rem;margin-bottom:12px;color:var(--muted)}
.nav-breadcrumb a{color:var(--navy)}
.summary-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.summary-card{background:var(--surface);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow-soft);border:1px solid var(--border)}
.summary-card .val{font-size:2.0rem;font-weight:700;color:var(--navy)}
.summary-card .lbl{font-size:0.85rem;color:var(--muted);margin-top:4px}

/* View / Detail page styles */
.object-page{display:grid;gap:0.8rem}
.object-header{border:1px solid var(--border);border-radius:16px;background:linear-gradient(135deg,#ffffff 0%,#eef4ff 100%);box-shadow:var(--shadow-soft);padding:16px;display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,0.78fr);gap:1rem;align-items:start}
.object-header-content{min-width:0}
.object-header h2{margin:0 0 0.35rem;font-size:clamp(1.2rem,2.2vw,1.5rem);line-height:1.18;color:#0f172a}
.object-header .muted{max-width:58rem;line-height:1.38;margin:0.25rem 0 0;color:var(--muted);font-size:0.9rem}
.eyebrow{margin:0 0 0.18rem;color:var(--accent);font-size:0.74rem;font-weight:800;letter-spacing:0.055em;text-transform:uppercase}
.object-meta{display:grid;gap:0.42rem;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));align-items:stretch}
.meta-chip{border:1px solid #d6e4f2;border-radius:12px;background:rgba(255,255,255,0.8);padding:0.48rem 0.56rem;min-width:0;box-shadow:0 4px 10px rgba(15,23,42,0.035)}
.meta-chip-label{display:block;color:var(--muted);font-size:0.74rem;font-weight:800;letter-spacing:0.035em;text-transform:uppercase;margin-bottom:0.16rem}
.meta-chip-value{display:block;color:#0f172a;font-weight:750;overflow-wrap:anywhere;line-height:1.28;font-size:1rem}

.detail-section{border:1px solid var(--border);border-radius:14px;background:var(--surface);overflow:hidden;box-shadow:var(--shadow-soft)}
.detail-section .section-header{padding:0.78rem 1rem;border-bottom:1px solid var(--border);background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%);display:flex;justify-content:space-between;align-items:center;gap:0.8rem}
.detail-section .section-header h3{margin:0;color:#0f172a;font-size:1.08rem}
.detail-grid{display:grid;gap:0.7rem;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));padding:1rem}
.detail-field{border:1px solid var(--border);border-radius:10px;background:var(--surface-muted);padding:10px 12px;min-width:0;box-shadow:var(--shadow-soft)}
.detail-field.long{grid-column:span 2}
.detail-label{color:var(--muted);font-size:0.78rem;font-weight:800;letter-spacing:0.025em;text-transform:uppercase;margin-bottom:0.24rem}
.detail-value{color:var(--text);font-size:0.98rem;line-height:1.42;min-height:1.2rem;overflow-wrap:anywhere;white-space:pre-wrap}
.detail-value.empty{color:var(--muted)}
.object-actions{display:flex;gap:0.55rem;flex-wrap:wrap;justify-content:flex-start;margin-top:0.7rem}

@media(max-width:720px){
  .object-header{display:block;padding:14px}
  .object-meta{justify-content:flex-start;margin-top:0.75rem}
  .detail-grid{grid-template-columns:1fr}
  .detail-field.long{grid-column:auto}
  .summary-cards{grid-template-columns:1fr 1fr}
}
</style>"""


def money_fmt(v):
    if v is None or (isinstance(v, (int, float)) and v == 0):
        return "-"
    return f"¥{int(v):,}" if v >= 1000 else f"¥{v:.2f}"


def badge_active(active):
    if active:
        return '<span class="badge badge-active">active</span>'
    return '<span class="badge badge-inactive">inactive</span>'


def badge_salary_type(st, msgs):
    labels = {k: t(msgs, v) for k, v in SALARY_TYPE_OPTIONS}
    cls = SALARY_TYPE_BADGE_CLASS.get(st, "")
    return f'<span class="badge {cls}">{labels.get(st, st)}</span>'


def badge_si(eligible, msgs):
    if eligible:
        return f'<span class="chip"><span class="dot dot-green"></span>{t(msgs,"badge.si_yes")}</span>'
    return f'<span class="chip"><span class="dot dot-red"></span>{t(msgs,"badge.si_no")}</span>'


def lang_switcher(lang, path):
    parts = []
    labels = {"zh": "简体中文", "ja": "日本語", "en": "English"}
    for l in SUPPORTED_LANGS:
        active = 'class="active"' if l == lang else ""
        parts.append(f'<a href="{path}?lang={l}" {active}>{labels[l]}</a>')
    return f'<div class="lang-switch">{"".join(parts)}</div>'


@router.get("/salary-master", response_class=HTMLResponse)
async def salary_master_list(
    request: Request,
    entity_id: Optional[str] = None,
    department: Optional[str] = None,
    team: Optional[str] = None,
    salary_type: Optional[str] = None,
    search: Optional[str] = None,
):
    lang = get_lang(request)
    msgs = load_i18n(lang)

    # Get distinct filter values from DB
    entities = fetch_all(
        "SELECT DISTINCT entity_id FROM pay_jp_salary_master WHERE entity_id IS NOT NULL ORDER BY entity_id"
    )
    depts = fetch_all(
        "SELECT DISTINCT department_label FROM pay_jp_salary_master WHERE department_label IS NOT NULL AND department_label != '' ORDER BY department_label"
    )
    teams = fetch_all(
        "SELECT DISTINCT team_label FROM pay_jp_salary_master WHERE team_label IS NOT NULL AND team_label != '' ORDER BY team_label"
    )

    where = ["1=1"]
    params = []
    if entity_id:
        where.append("entity_id=%s")
        params.append(entity_id)
    if department:
        where.append("department_label=%s")
        params.append(department)
    if team:
        where.append("team_label=%s")
        params.append(team)
    if salary_type:
        where.append("salary_type=%s")
        params.append(salary_type)
    if search:
        where.append(
            "(employee_name ILIKE %s OR employee_number ILIKE %s OR department_label ILIKE %s)"
        )
        params.extend([f"%{search}%"] * 3)
    sql = f"SELECT * FROM pay_jp_salary_master WHERE {' AND '.join(where)} ORDER BY employee_number"
    rows = fetch_all(sql, tuple(params) if params else None)

    monthly_count = sum(1 for r in rows if r.get("salary_type") == "monthly")
    hourly_count = sum(1 for r in rows if r.get("salary_type") in ("hourly", "monthly_hour"))
    si_count = sum(1 for r in rows if r.get("social_insurance_eligible"))

    ent_opts = "".join(
        f'<option value="{r["entity_id"]}" {"selected" if entity_id==r["entity_id"] else ""}>{r["entity_id"]}</option>'
        for r in entities
    )
    dept_opts = "".join(
        f'<option value="{r["department_label"]}" {"selected" if department==r["department_label"] else ""}>{r["department_label"]}</option>'
        for r in depts
    )
    team_opts = "".join(
        f'<option value="{r["team_label"]}" {"selected" if team==r["team_label"] else ""}>{r["team_label"]}</option>'
        for r in teams
    )
    st_opts = "".join(
        f'<option value="{v}" {"selected" if salary_type==v else ""}>{t(msgs,k)}</option>'
        for v, k in SALARY_TYPE_OPTIONS
    )

    parts = []
    parts.append(
        f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{t(msgs,'salary_master.title')} — {t(msgs,'app.title')}</title>{STYLE}</head><body>
<div class="header"><div><h1>📋 {t(msgs,'salary_master.title')}</h1></div><div style="display:flex;align-items:center;gap:16px">{lang_switcher(lang,request.url.path)}<a href="/">{t(msgs,'nav.dashboard')}</a> | <a href="/salary-master/new?lang={lang}" style="display:inline-block;padding:7px 14px;font-size:0.85rem;font-weight:700;color:#fff;background:var(--green);text-decoration:none;border-radius:8px">{t(msgs,'btn.create')}</a><a href="/salary-master/import?lang={lang}" style="display:inline-block;padding:7px 14px;font-size:0.85rem;font-weight:700;color:#fff;background:#6a1b9a;text-decoration:none;border-radius:8px">{t(msgs,'salary_master.import_btn')}</a></div></div>
<div class="container"><div class="nav-breadcrumb"><a href="/">🏠 {t(msgs,'nav.dashboard')}</a> » <strong>{t(msgs,'salary_master.title')}</strong></div>
<div class="summary-cards">
<div class="summary-card"><div class="val">{len(rows)}</div><div class="lbl">{t(msgs,'salary_master.total')}</div></div>
<div class="summary-card"><div class="val">{si_count}</div><div class="lbl">{t(msgs,'salary_master.si_eligible')}</div></div>
<div class="summary-card"><div class="val">{monthly_count}</div><div class="lbl">{t(msgs,'salary_master.monthly_count')}</div></div>
<div class="summary-card"><div class="val">{hourly_count}</div><div class="lbl">{t(msgs,'salary_master.hourly_count')}</div></div>
</div>
<div class="toolbar">
<form method="get" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<input name="search" value="{search or ''}" placeholder="{t(msgs,'salary_master.search_placeholder')}" style="width:200px">
<select name="entity_id" onchange="this.form.submit()"><option value="">全法人</option>{ent_opts}</select>
<select name="department" onchange="this.form.submit()"><option value="">全部署</option>{dept_opts}</select>
<select name="team" onchange="this.form.submit()"><option value="">全チーム</option>{team_opts}</select>
<select name="salary_type" onchange="this.form.submit()"><option value="">{t(msgs,'salary_master.all_types')}</option>{st_opts}</select>
<input type="hidden" name="lang" value="{lang}">
<button style="padding:7px 16px;font-size:0.85rem;font-weight:700;color:#fff;background:var(--accent);border:none;border-radius:8px;cursor:pointer">{t(msgs,'btn.search')}</button>
</form></div>"""
    )

    if not rows:
        parts.append(
            f'<div class="card"><div class="empty">{t(msgs,"salary_master.no_records")}</div></div>'
        )
    else:
        parts.append(
            f'<div class="card"><div class="card-header"><strong>{t(msgs,"salary_master.title")}</strong><span style="font-size:0.9rem;color:var(--muted)">{t(msgs,"salary_master.record_count",count=str(len(rows)))}</span></div><div style="overflow-x:auto"><table>'
        )
        parts.append(
            f'<tr><th>{t(msgs,"salary_master.employee_number")}</th><th>{t(msgs,"salary_master.employee_name")}</th><th>{t(msgs,"salary_master.salary_type")}</th><th>{t(msgs,"salary_master.basic_salary")}</th><th>{t(msgs,"salary_master.hourly_rate")}</th><th>{t(msgs,"salary_master.commute")}</th><th>交通費</th><th>電話</th><th>PJ賞与</th><th>{t(msgs,"salary_master.social_insurance")}</th><th>{t(msgs,"salary_master.dependents")}</th><th>{t(msgs,"salary_master.bank")}</th><th>{t(msgs,"salary_master.notes")}</th><th></th></tr>'
        )
        for r in rows:
            emp_no_link = f'<a href="/salary-master/{r["salary_master_id"]}/view?lang={lang}" style="font-weight:600">{r["employee_number"]}</a>'
            parts.append(
                f"""<tr>
<td>{emp_no_link}</td>
<td><strong>{r['employee_name']}</strong><br><span style="font-size:0.82rem;color:var(--muted)">{r.get('department_label','')} / {r.get('team_label','')}</span></td>
<td>{badge_salary_type(r.get('salary_type','monthly'), msgs)} {badge_active(r.get('active',True))}</td>
<td class="num">{money_fmt(r.get('basic_salary'))}</td>
<td class="num">{money_fmt(r.get('hourly_rate'))}</td>
<td class="num">{money_fmt(r.get('commute_allowance'))}</td>
<td class="num">{money_fmt(r.get('transport_allowance'))}</td>
<td class="num">{money_fmt(r.get('phone_allowance'))}</td>
<td class="num">{money_fmt(r.get('project_bonus'))}</td>
<td>{badge_si(r.get('social_insurance_eligible',True), msgs)}</td>
<td class="num">{r.get('dependents_count',0)}</td>
<td style="font-size:0.85rem">{r.get('bank_name','') or '-'}</td>
<td style="font-size:0.85rem;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r.get('notes','') or '-'}</td>
<td style="white-space:nowrap"><a href="/salary-master/{r['salary_master_id']}/view?lang={lang}" style="display:inline-block;padding:5px 10px;font-size:0.8rem;font-weight:600;color:var(--navy);text-decoration:none;border:1px solid var(--border);border-radius:6px;margin-right:4px">{t(msgs,'salary_master.view_btn')}</a><a href="/salary-master/{r['salary_master_id']}/edit?lang={lang}" style="display:inline-block;padding:5px 10px;font-size:0.8rem;font-weight:600;color:var(--accent);text-decoration:none;border:1px solid var(--accent);border-radius:6px">{t(msgs,'salary_master.edit_btn')}</a></td>
</tr>"""
            )
        parts.append("</table></div></div>")

    parts.append(
        f'<div class="footer-text">{t(msgs,"app.title")} | <a href="/docs">API</a></div></div></body></html>'
    )
    return HTMLResponse("\n".join(parts))


@router.get("/salary-master/import", response_class=HTMLResponse)
async def salary_master_import(request: Request):
    """Import page — shows EmployeeAdmin employees with checkboxes, grayed-out existing ones."""
    lang = get_lang(request)
    msgs = load_i18n(lang)

    # Fetch importable employees from EmployeeAdmin
    try:
        ea = fetch_all(
            "SELECT employee_id, employee_number, email, payroll FROM emp_employees WHERE payroll IS NOT NULL ORDER BY employee_number"
        )
    except Exception:
        ea = []
    existing = fetch_all("SELECT employee_id FROM pay_jp_salary_master")
    existing_ids = {r["employee_id"] for r in existing}

    rows_html = ""
    for emp in ea:
        payroll = emp.get("payroll", {})
        if isinstance(payroll, str):
            import json; payroll = json.loads(payroll)
        eid = emp["employee_id"]
        already = eid in existing_ids
        name = payroll.get("employee_name", emp.get("display_name", ""))
        dept = payroll.get("department_label", "")
        entity = payroll.get("entity_id", "")
        st = payroll.get("salary_type", "monthly")

        if already:
            rows_html += f"""<tr style="background:#f5f5f5;color:#bbb">
<td><input type="checkbox" disabled></td>
<td style="text-decoration:line-through">{emp.get('employee_number','')}</td>
<td style="text-decoration:line-through">{name}</td>
<td>{dept}</td><td>{entity}</td><td>{st}</td>
<td><span class="badge badge-inactive">{t(msgs,'salary_master.already_imported')}</span></td></tr>"""
        else:
            rows_html += f"""<tr>
<td><input type="checkbox" class="import-checkbox" value="{eid}"></td>
<td>{emp.get('employee_number','')}</td>
<td><strong>{name}</strong></td>
<td>{dept}</td><td>{entity}</td><td>{st}</td>
<td><span class="badge badge-active">New</span></td></tr>"""

    html = f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{t(msgs,'salary_master.import_title')}</title>{STYLE}</head><body>
<div class="header"><div><h1>📥 {t(msgs,'salary_master.import_title')}</h1></div><div>{lang_switcher(lang,request.url.path)}<a href="/salary-master?lang={lang}">{t(msgs,'salary_master.back')}</a></div></div>
<div class="container"><div class="nav-breadcrumb"><a href="/salary-master?lang={lang}">{t(msgs,'salary_master.title')}</a> » <strong>{t(msgs,'salary_master.import_title')}</strong></div>
<div class="toolbar">
<button class="btn btn-success" onclick="importSelected()" style="font-size:1.05rem;padding:12px 24px">{t(msgs,'salary_master.import_execute')}</button>
<button class="btn btn-outline" onclick="document.querySelectorAll('.import-checkbox').forEach(cb=>cb.checked=!cb.checked)">☑ Toggle All</button>
<span id="status" style="font-size:1rem;color:var(--muted);margin-left:12px"></span>
</div>
<div class="card"><div style="overflow-x:auto"><table>
<tr><th style="width:40px"></th><th>社員番号</th><th>氏名</th><th>部署</th><th>法人</th><th>種別</th><th>状態</th></tr>
{rows_html if rows_html else '<tr><td colspan="7" class="empty">EmployeeAdminにデータがありません</td></tr>'}
</table></div></div>
<div class="footer-text">{len(ea)} employees from EmployeeAdmin | 灰色 = {t(msgs,'salary_master.already_imported')}</div></div>
<script>
async function importSelected() {{
  var selected = Array.from(document.querySelectorAll('.import-checkbox:checked')).map(cb => cb.value);
  if (selected.length === 0) {{ alert('{t(msgs,'salary_master.import_select')}'); return; }}
  document.getElementById('status').textContent = '処理中...';
  var resp = await fetch('/api/salary-master/import-selected', {{
    method: 'POST', headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{employee_ids: selected}})
  }});
  var d = await resp.json();
  if (resp.ok) {{
    document.getElementById('status').textContent = '✅ {len(existing_ids)}件取込済 + '+d.imported+'件新規取込';
    setTimeout(function(){{ location.reload(); }}, 1500);
  }} else {{
    alert('❌ '+(d.detail||JSON.stringify(d)));
  }}
}}
</script></body></html>"""
    return HTMLResponse(html)


@router.get("/salary-master/new", response_class=HTMLResponse)
async def salary_master_new(request: Request):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    return HTMLResponse(salary_master_form_html({}, "new", lang, msgs, can_edit_empno=False))


@router.get("/salary-master/{sm_id}/view", response_class=HTMLResponse)
async def salary_master_view(request: Request, sm_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    row = fetch_one(
        f"SELECT * FROM pay_jp_salary_master WHERE salary_master_id=%s", (sm_id,)
    )
    if not row:
        return HTMLResponse("<h2>Not found</h2>", status_code=404)
    return HTMLResponse(salary_master_view_html(row, lang, msgs))


@router.get("/salary-master/{sm_id}/edit", response_class=HTMLResponse)
async def salary_master_edit(request: Request, sm_id: str):
    lang = get_lang(request)
    msgs = load_i18n(lang)
    row = fetch_one(
        f"SELECT * FROM pay_jp_salary_master WHERE salary_master_id=%s", (sm_id,)
    )
    if not row:
        return HTMLResponse("<h2>Not found</h2>", status_code=404)
    # Check if user can edit employee_number
    can_edit_empno = await check_permission(
        request, "tacaipay_jp.salary_master.edit_employee_number"
    )
    return HTMLResponse(salary_master_form_html(row, "edit", lang, msgs, can_edit_empno))


def salary_master_view_html(row: dict, lang: str, msgs: dict) -> str:
    """Read-only detail view — like employeeadmin detail page pattern."""
    sm_id = row.get("salary_master_id", "")
    vals = lambda k, default="": row.get(k, default) if row else default

    def detail_row(label_key, value, fallback="-", is_money=False):
        label = t(msgs, label_key)
        if is_money and value:
            display = f"¥{int(value):,}" if float(value) >= 1000 else f"¥{float(value):.2f}"
        elif isinstance(value, bool):
            display = t(msgs, "badge.si_yes") if value else t(msgs, "badge.si_no")
        else:
            display = str(value) if value else fallback
        return f'<div class="detail-field"><div class="detail-label">{label}</div><div class="detail-value{" empty" if not value else ""}">{display}</div></div>'

    # Build salary type label
    st_val = vals("salary_type", "monthly")
    st_label = t(msgs, f"salary_type.{st_val}", st_val)

    employ_page = f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{t(msgs,'salary_master.view')} — {t(msgs,'app.title')}</title>{STYLE}</head><body>
<div class="header"><div><h1>📄 {t(msgs,'salary_master.title')} — {t(msgs,'salary_master.view')}</h1></div><div>{lang_switcher(lang, f'/salary-master/{sm_id}/view')}<a href="/salary-master?lang={lang}">{t(msgs,'salary_master.back')}</a></div></div>
<div class="container"><div class="nav-breadcrumb"><a href="/salary-master?lang={lang}">📋 {t(msgs,'salary_master.title')}</a> » <strong>{vals('employee_number')}</strong></div>

<div class="object-page">
<div class="object-header">
  <div class="object-header-content">
    <div class="eyebrow">{t(msgs,'salary_master.employee_number')}</div>
    <h2>{vals('employee_name')}</h2>
    <div class="muted">{vals('employee_number')} — {vals('email','-')}</div>
    <div class="object-actions">
      <a class="btn btn-outline" href="/salary-master/{sm_id}/edit?lang={lang}">{t(msgs,'btn.edit')}</a>
      <a class="btn btn-outline" href="/salary-master?lang={lang}">{t(msgs,'btn.back_to_list')}</a>
    </div>
  </div>
  <div class="object-meta">
    <div class="meta-chip"><span class="meta-chip-label">{t(msgs,'salary_master.salary_type')}</span><span class="meta-chip-value">{st_label}</span></div>
    <div class="meta-chip"><span class="meta-chip-label">{t(msgs,'salary_master.entity')}</span><span class="meta-chip-value">{vals('entity_id','-')}</span></div>
    <div class="meta-chip"><span class="meta-chip-label">{t(msgs,'salary_master.department')}</span><span class="meta-chip-value">{vals('department_label','-')}</span></div>
    <div class="meta-chip"><span class="meta-chip-label">{t(msgs,'salary_master.team')}</span><span class="meta-chip-value">{vals('team_label','-')}</span></div>
  </div>
</div>

<div class="detail-section">
  <div class="section-header"><h3>{t(msgs,'section.basic_info')}</h3></div>
  <div class="detail-grid">
    {detail_row('salary_master.employee_number', vals('employee_number'))}
    {detail_row('salary_master.employee_name', vals('employee_name'))}
    {detail_row('salary_master.email', vals('email'))}
    {detail_row('salary_master.entity', vals('entity_id'))}
    {detail_row('salary_master.department', vals('department_label'))}
    {detail_row('salary_master.team', vals('team_label'))}
    {detail_row('field.country_code', vals('country_code'))}
    {detail_row('field.employment_status', vals('employment_status'))}
  </div>
</div>

<div class="detail-section">
  <div class="section-header"><h3>{t(msgs,'section.salary_setting')}</h3></div>
  <div class="detail-grid">
    {detail_row('salary_master.salary_type', st_label)}
    {detail_row('salary_master.basic_salary', vals('basic_salary'), is_money=True)}
    {detail_row('salary_master.hourly_rate', vals('hourly_rate'), is_money=True)}
    {detail_row('label.daily_rate', vals('daily_rate'), is_money=True)}
    {detail_row('label.standard_work_days', vals('standard_work_days'))}
    {detail_row('label.standard_work_hours', vals('standard_work_hours'))}
    {detail_row('label.standard_monthly_hours', vals('standard_monthly_hours'))}
    {detail_row('label.overtime_hourly_rate', vals('overtime_hourly_rate'), is_money=True)}
  </div>
</div>

<div class="detail-section">
  <div class="section-header"><h3>{t(msgs,'section.allowance_ot')}</h3></div>
  <div class="detail-grid">
    {detail_row('label.commute_allowance', vals('commute_allowance'), is_money=True)}
    {detail_row('label.housing_allowance', vals('housing_allowance'), is_money=True)}
    {detail_row('label.family_allowance', vals('family_allowance'), is_money=True)}
    {detail_row('label.position_allowance', vals('position_allowance'), is_money=True)}
    {detail_row('label.fixed_allowance', vals('fixed_allowance'), is_money=True)}
    {detail_row('label.fixed_ot_hours', vals('fixed_overtime_hours'))}
    {detail_row('label.fixed_ot_amount', vals('fixed_overtime_amount'), is_money=True)}
    {detail_row('label.performance_bonus', vals('performance_bonus'), is_money=True)}
    {detail_row('label.recurring_deductions', vals('recurring_deductions'), is_money=True)}
  </div>
</div>

<div class="detail-section">
  <div class="section-header"><h3>{t(msgs,'section.social_insurance')}</h3></div>
  <div class="detail-grid">
    {detail_row('label.si_eligible', vals('social_insurance_eligible'))}
    {detail_row('label.ei_eligible', vals('employment_insurance_eligible'))}
    {detail_row('label.dependents_count', vals('dependents_count'))}
    {detail_row('label.resident_tax', vals('monthly_resident_tax'), is_money=True)}
    {detail_row('label.prefecture', vals('prefecture_code'))}
    {detail_row('label.age', vals('age_at_fiscal_year_start'))}
  </div>
</div>

<div class="detail-section">
  <div class="section-header"><h3>{t(msgs,'section.bank_info')}</h3></div>
  <div class="detail-grid">
    {detail_row('label.bank_name', vals('bank_name'))}
    {detail_row('label.bank_branch_name', vals('bank_branch_name'))}
    {detail_row('label.bank_account_type', vals('bank_account_type'))}
    {detail_row('label.bank_account_name', vals('bank_account_name'))}
    {detail_row('label.bank_account_number', vals('bank_account_number'))}
  </div>
</div>
</div>

<div class="footer-text">{t(msgs,'app.title')} | <a href="/salary-master?lang={lang}">{t(msgs,'salary_master.back')}</a></div></div></body></html>"""
    return employ_page


def salary_master_form_html(
    row: dict, mode: str, lang: str, msgs: dict, can_edit_empno: bool
) -> str:
    is_edit = mode == "edit"
    is_new = mode == "new"
    if is_edit:
        title = t(msgs, "salary_master.edit")
    else:
        title = t(msgs, "salary_master.new")
    sm_id = row.get("salary_master_id", "")
    vals = lambda k, default="": row.get(k, default) if row else default

    def render_field(label_key, key, typ, extra=None):
        label = t(msgs, label_key) if label_key else ""
        if typ == "select":
            if isinstance(extra, list) and extra and isinstance(extra[0], tuple):
                opts = "".join(
                    f'<option value="{v}" {"selected" if str(vals(key))==v else ""}>{t(msgs,k) if isinstance(k,str) and k.startswith("salary") else v}</option>'
                    for v, k in extra
                )
            else:
                opts = "".join(
                    f'<option value="{o}" {"selected" if str(vals(key))==o else ""}>{o}</option>'
                    for o in (extra or [])
                )
            return f'<div class="field"><label>{label}</label><select name="{key}">{opts}</select></div>'
        if typ == "checkbox":
            chk = "checked" if vals(key) or vals(key) == "true" else ""
            return f'<div class="field"><label>{label}</label><input type="checkbox" name="{key}" value="true" {chk}></div>'
        # Determine readonly status
        is_readonly = False
        readonly_hint = ""
        if is_edit and key in ("employee_name", "email", "entity_id"):
            is_readonly = True
        elif is_edit and key == "employee_number" and not can_edit_empno:
            is_readonly = True
            readonly_hint = f'<div class="readonly-hint">{t(msgs,"salary_master.employee_number_readonly_hint")}</div>'
        readonly_attr = "readonly" if is_readonly else ""
        val = vals(key)
        if typ == "number":
            try:
                val = int(float(val)) if val and str(val).replace(".", "").replace("-", "").isdigit() else (val or "")
            except (ValueError, TypeError):
                pass
        hint = readonly_hint
        return f'<div class="field"><label>{label}</label><input type="{typ}" name="{key}" value="{val}" {readonly_attr}>{hint}</div>'

    # Build two-column layout: left (basic + salary) | right (allowance + insurance)
    parts = [
        f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} — {t(msgs,'app.title')}</title>{STYLE}</head><body>
<div class="header"><div><h1>📝 {t(msgs,'salary_master.title')} — {title}</h1></div><div>{lang_switcher(lang, ('/salary-master/' + sm_id + '/edit') if is_edit else '/salary-master/new')}<a href="/salary-master?lang={lang}">{t(msgs,'salary_master.back')}</a></div></div>
<div class="container"><div class="card"><form id="salaryForm">"""
    ]

    parts.append(f'<div class="form-two-col"><div class="form-col">')

    # Basic Info
    parts.append(
        f'<div class="section-title">{t(msgs,"section.basic_info")}</div><div class="form-grid">'
    )
    for lk, k, typ, ex in [
        ("salary_master.employee_number", "employee_number", "text", None),
        ("salary_master.employee_name", "employee_name", "text", None),
        ("salary_master.email", "email", "email", None),
        ("salary_master.entity", "entity_id", "text", None),
        ("salary_master.department", "department_label", "text", None),
        ("salary_master.team", "team_label", "text", None),
    ]:
        parts.append(render_field(lk, k, typ, ex))
    parts.append("</div>")

    # Salary Setting
    parts.append(
        f'<div class="section-title">{t(msgs,"section.salary_setting")}</div><div class="form-grid">'
    )
    for lk, k, typ, ex in [
        ("salary_master.salary_type", "salary_type", "select", SALARY_TYPE_OPTIONS),
        ("salary_master.basic_salary", "basic_salary", "number", None),
        ("salary_master.hourly_rate", "hourly_rate", "number", None),
        ("label.daily_rate", "daily_rate", "number", None),
        ("label.standard_work_days", "standard_work_days", "number", None),
        ("label.standard_work_hours", "standard_work_hours", "number", None),
        ("label.standard_monthly_hours", "standard_monthly_hours", "number", None),
        ("label.overtime_hourly_rate", "overtime_hourly_rate", "number", None),
    ]:
        parts.append(render_field(lk, k, typ, ex))
    parts.append("</div>")

    parts.append(f'</div><div class="form-col">')

    # Allowances & OT
    parts.append(
        f'<div class="section-title">{t(msgs,"section.allowance_ot")}</div><div class="form-grid">'
    )
    for lk, k, typ, ex in [
        ("label.commute_allowance", "commute_allowance", "number", None),
        ("label.housing_allowance", "housing_allowance", "number", None),
        ("label.family_allowance", "family_allowance", "number", None),
        ("label.position_allowance", "position_allowance", "number", None),
        ("label.fixed_allowance", "fixed_allowance", "number", None),
        ("label.transport_allowance", "transport_allowance", "number", None),
        ("label.phone_allowance", "phone_allowance", "number", None),
        ("label.project_bonus", "project_bonus", "number", None),
        ("label.fixed_ot_hours", "fixed_overtime_hours", "number", None),
        ("label.fixed_ot_amount", "fixed_overtime_amount", "number", None),
        ("label.performance_bonus", "performance_bonus", "number", None),
        ("label.recurring_deductions", "recurring_deductions", "number", None),
    ]:
        parts.append(render_field(lk, k, typ, ex))
    parts.append("</div>")

    # Social Insurance
    parts.append(
        f'<div class="section-title">{t(msgs,"section.social_insurance")}</div><div class="form-grid">'
    )
    for lk, k, typ, ex in [
        ("label.si_eligible", "social_insurance_eligible", "checkbox", None),
        ("label.ei_eligible", "employment_insurance_eligible", "checkbox", None),
        ("label.dependents_count", "dependents_count", "number", None),
        ("label.resident_tax", "monthly_resident_tax", "number", None),
        ("label.prefecture", "prefecture_code", "text", None),
        ("label.age", "age_at_fiscal_year_start", "number", None),
    ]:
        parts.append(render_field(lk, k, typ, ex))
    parts.append("</div>")

    parts.append(f"</div></div>")  # close form-two-col

    # Bank Info (full width)
    parts.append(
        f'<div class="section-title">{t(msgs,"section.bank_info")}</div><div class="form-grid-full">'
    )
    for lk, k, typ, ex in [
        ("label.bank_name", "bank_name", "text", None),
        ("label.bank_branch_name", "bank_branch_name", "text", None),
        (
            "label.bank_account_type",
            "bank_account_type",
            "select",
            [("ordinary", "bank_account_type.ordinary"), ("current", "bank_account_type.current"), ("savings", "bank_account_type.savings")],
        ),
        ("label.bank_account_name", "bank_account_name", "text", None),
        ("label.bank_account_number", "bank_account_number", "text", None),
    ]:
        parts.append(render_field(lk, k, typ, ex))
    parts.append("</div>")

    # Notes
    parts.append(
        f'<div class="form-grid-full"><div class="field"><label>{t(msgs,"salary_master.notes")}</label><input name="notes" value="{vals("notes","")}"></div></div>'
    )

    api_url = f"/api/salary-master/{sm_id}" if is_edit else "/api/salary-master/"
    method = "PUT" if is_edit else "POST"

    # Build JS safe strings
    save_success = t(msgs, "save.success")
    save_error = t(msgs, "save.error")

    parts.append(
        f"""<div class="form-actions">
<button type="button" class="btn btn-outline" onclick="history.back()">{t(msgs,'btn.cancel')}</button>
<button type="submit" class="btn btn-success">{t(msgs,'btn.save')}</button>
</div></form></div></div>
<script>
document.getElementById('salaryForm').addEventListener('submit', async (e) => {{
e.preventDefault();
const fd = new FormData(e.target);
const data = {{}};
const numeric = ['basic_salary','hourly_rate','daily_rate','standard_work_days','standard_work_hours','standard_monthly_hours','overtime_hourly_rate','commute_allowance','housing_allowance','family_allowance','position_allowance','fixed_allowance','transport_allowance','phone_allowance','project_bonus','fixed_overtime_hours','fixed_overtime_amount','performance_bonus','recurring_deductions','monthly_resident_tax','age_at_fiscal_year_start'];
const bools = ['social_insurance_eligible','employment_insurance_eligible'];
fd.forEach((v,k) => {{
  if (bools.includes(k)) data[k] = v === 'true';
  else if (numeric.includes(k)) data[k] = parseFloat(v) || 0;
  else if (k === 'dependents_count') data[k] = parseInt(v) || 0;
  else data[k] = v;
}});
const resp = await fetch('{api_url}', {{method:'{method}',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
if (resp.ok) {{ alert('{save_success}'); window.location.href='/salary-master?lang={lang}'; }}
else {{ const e = await resp.json(); alert('{save_error}: '+JSON.stringify(e)); }}
}});
</script></body></html>"""
    )
    return "\n".join(parts)
