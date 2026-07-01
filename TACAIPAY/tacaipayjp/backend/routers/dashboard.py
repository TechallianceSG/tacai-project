"""Trilingual HTML dashboard — served at / (zh/ja/en)"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import fetch_all
from i18n import t, get_lang, load_i18n, SUPPORTED_LANGS

router = APIRouter(tags=["dashboard"])


def lang_switcher(lang: str, path: str) -> str:
    labels = {"zh": "简体中文", "ja": "日本語", "en": "English"}
    parts = []
    for l in SUPPORTED_LANGS:
        active = 'class="active"' if l == lang else ""
        parts.append(f'<a href="{path}?lang={l}" {active}>{labels[l]}</a>')
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
  --accent-dark: #1d4ed8;
  --green: #0f766e;
  --amber: #b45309;
  --danger: #b91c1c;
  --focus: rgba(31, 111, 235, 0.18);
  --shadow-soft: 0 1px 2px rgba(15, 23, 42, 0.04);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Hiragino Sans','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.45;color:var(--text);background:var(--page-bg)}
.header{background:linear-gradient(135deg,#14213d,#1e3a5f);color:#fff;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.header h1{font-size:clamp(1.15rem,2.2vw,1.35rem);font-weight:700;line-height:1.15;margin:0}
.header .sub{font-size:0.9rem;opacity:.85}
.lang-switch{display:flex;gap:4px}.lang-switch a{padding:4px 10px;border-radius:999px;font-size:0.82rem;color:#fff;text-decoration:none;border:1px solid rgba(255,255,255,.3);font-weight:600}
.lang-switch a.active{background:rgba(255,255,255,.2);border-color:#fff;font-weight:750}
.container{max-width:1400px;margin:0 auto;padding:20px}
.module-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:24px}
.module-card{background:var(--surface);border-radius:14px;padding:20px;box-shadow:var(--shadow-soft);transition:all .2s;text-decoration:none;color:var(--text);display:block;border-left:4px solid var(--navy);border:1px solid var(--border)}
.module-card:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.15);text-decoration:none}
.module-card .icon{font-size:28px;margin-bottom:8px}
.module-card .title{font-size:1.1rem;font-weight:700;color:var(--navy);margin-bottom:4px}
.module-card .desc{font-size:0.9rem;color:var(--muted)}
.module-card.card-salary{border-left-color:var(--green)}
.module-card.card-sheet{border-left-color:#e65100}
.module-card.card-params{border-left-color:#1565c0}
.module-card.card-api{border-left-color:#6a1b9a}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:24px}
.card{background:var(--surface);border-radius:14px;box-shadow:var(--shadow-soft);overflow:hidden;border:1px solid var(--border);margin-bottom:16px}
.card-header{background:var(--surface-muted);padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.card-header h3{font-size:1rem;color:var(--navy)}
.card-header .count{font-size:0.85rem;color:var(--muted)}
.card-body{padding:12px 16px}
table{width:100%;border-collapse:collapse;font-size:1.0rem}
th{text-align:left;padding:10px 8px;border-bottom:2px solid var(--border-strong);color:#555;font-weight:800;white-space:nowrap;font-size:0.95rem}
td{padding:7px 8px;border-bottom:1px solid #f0f0f0;vertical-align:top;line-height:1.4}
tr:hover{background:#f5f7ff}
.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:3px 8px;border-radius:999px;font-size:0.85rem;font-weight:800}
.badge-active{background:#dcfce7;color:#166534}
.badge-inactive{background:#f5f5f5;color:#999}
.section{margin-bottom:32px}
.section-title{font-size:1.25rem;color:var(--navy);margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid var(--navy)}
.empty{text-align:center;color:var(--muted);padding:24px;font-size:1rem}
.footer{text-align:center;color:var(--muted);font-size:0.85rem;padding:16px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
nav{margin-bottom:16px;display:flex;flex-wrap:wrap;gap:8px}
nav a{padding:10px 18px;background:var(--surface);border-radius:8px;box-shadow:var(--shadow-soft);font-size:0.95rem;color:var(--text);text-decoration:none;font-weight:700;border:1px solid var(--border)}
nav a.active{background:var(--navy);color:#fff}
nav a:hover{text-decoration:none;border-color:var(--blue);color:var(--blue)}
nav a.active:hover{color:#fff}
</style>"""

COL_HEADERS_JA = {
    "rate_type": "種別", "prefecture": "都道府県", "employee_rate": "本人負担",
    "employer_rate": "会社負担", "applicable_from": "適用開始",
    "grade_number": "等級", "min_monthly_amount": "下限 (月額)",
    "max_monthly_amount": "上限 (月額)", "standard_monthly_amount": "標準報酬月額",
    "min_salary": "給与範囲", "tax_dep_0": "扶養0", "tax_dep_1": "扶養1",
    "tax_dep_2": "扶養2", "tax_dep_3": "扶養3",
    "industry_code": "業種コード", "industry_name_ja": "業種名",
    "industry_name_en": "英名", "rate": "料率",
    "table_type": "表種別",
}

COL_HEADERS_ZH = {
    "rate_type": "种类", "prefecture": "都道府县", "employee_rate": "个人负担",
    "employer_rate": "公司负担", "applicable_from": "适用开始",
    "grade_number": "等级", "min_monthly_amount": "下限 (月额)",
    "max_monthly_amount": "上限 (月额)", "standard_monthly_amount": "标准月额",
    "min_salary": "薪资范围", "tax_dep_0": "扶养0", "tax_dep_1": "扶养1",
    "tax_dep_2": "扶养2", "tax_dep_3": "扶养3",
    "industry_code": "行业代码", "industry_name_ja": "行业名",
    "industry_name_en": "英文名", "rate": "费率",
    "table_type": "表类型",
}

COL_HEADERS_EN = {
    "rate_type": "Type", "prefecture": "Prefecture", "employee_rate": "Employee",
    "employer_rate": "Employer", "applicable_from": "Effective From",
    "grade_number": "Grade", "min_monthly_amount": "Min (Monthly)",
    "max_monthly_amount": "Max (Monthly)", "standard_monthly_amount": "Standard Monthly",
    "min_salary": "Salary Range", "tax_dep_0": "Dep.0", "tax_dep_1": "Dep.1",
    "tax_dep_2": "Dep.2", "tax_dep_3": "Dep.3",
    "industry_code": "Industry Code", "industry_name_ja": "Industry (JA)",
    "industry_name_en": "Industry (EN)", "rate": "Rate",
    "table_type": "Table Type",
}


def col_header(key: str, lang: str) -> str:
    if lang == "zh":
        return COL_HEADERS_ZH.get(key, key)
    elif lang == "en":
        return COL_HEADERS_EN.get(key, key)
    return COL_HEADERS_JA.get(key, key)


def fmt(v):
    if v is None: return "-"
    if isinstance(v, float):
        if v < 1: return f"{v*100:.2f}%"
        return f"{v:,.2f}"
    if isinstance(v, int) and v > 999:
        return f"{v:,}"
    return str(v)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    lang = get_lang(request)
    msgs = load_i18n(lang)

    parts = []

    # ── Header ──
    parts.append(f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{t(msgs,'dashboard.title')}</title>{STYLE}</head><body>
<div class="header"><div><h1>{t(msgs,'dashboard.title')} <span class="sub">{t(msgs,'dashboard.subtitle')}</span></h1></div><div style="display:flex;align-items:center;gap:12px">{lang_switcher(lang,'/')}<span style="font-size:0.9rem">{t(msgs,'dashboard.subtitle_year')}</span></div></div>
<div class="container">""")

    # ── Module Navigation Cards ──
    parts.append(f"""<div class="module-cards">
<a href="/salary-master?lang={lang}" class="module-card card-salary">
  <div class="icon">📋</div><div class="title">{t(msgs,'dashboard.card_salary_master')}</div><div class="desc">{t(msgs,'dashboard.card_salary_master_desc')}</div>
</a>
<a href="/api/monthly-sheets/page/list?lang={lang}" class="module-card card-sheet">
  <div class="icon">📅</div><div class="title">{t(msgs,'dashboard.card_monthly_sheets')}</div><div class="desc">{t(msgs,'dashboard.card_monthly_sheets_desc')}</div>
</a>
<a href="/api/monthly-sheets/page/list?lang={lang}" class="module-card card-sheet" style="border-left-color:#6a1b9a">
  <div class="icon">📤</div><div class="title">{t(msgs,'dashboard.card_release')}</div><div class="desc">{t(msgs,'dashboard.card_release_desc')}</div>
</a>
<a href="/docs" class="module-card card-api">
  <div class="icon">🔧</div><div class="title">{t(msgs,'dashboard.card_api')}</div><div class="desc">{t(msgs,'dashboard.card_api_desc')}</div>
</a>
</div>""")

    # ── Parameter Quick Nav ──
    parts.append(f"""<nav>
<a href="#social-insurance">{t(msgs,'dashboard.section_social_insurance')}</a>
<a href="#grades">{t(msgs,'dashboard.section_remuneration_grades')}</a>
<a href="#tax">{t(msgs,'dashboard.section_withholding_tax')}</a>
<a href="#accident">{t(msgs,'dashboard.section_accident_insurance')}</a>
</nav>""")

    # ── Social Insurance ──
    parts.append(f'<div class="section" id="social-insurance"><div class="section-title">{t(msgs,"dashboard.section_social_insurance")}</div><div class="card">')
    si = fetch_all("SELECT * FROM pay_jp_social_insurance_rates ORDER BY rate_type, prefecture NULLS FIRST")
    parts.append(f'<div class="card-header"><h3>{t(msgs,"general.records", count=str(len(si)))}</h3></div><div class="card-body"><table><tr>')
    for key in ["rate_type", "prefecture", "employee_rate", "employer_rate", "applicable_from"]:
        parts.append(f"<th>{col_header(key, lang)}</th>")
    parts.append("</tr>")
    for r in si:
        prefecture = r["prefecture"] or ({"zh": "全国", "ja": "全国", "en": "National"}.get(lang, "全国"))
        parts.append(f'<tr><td>{r["rate_type"]}</td><td>{prefecture}</td><td class="num">{fmt(r["employee_rate"])}</td><td class="num">{fmt(r["employer_rate"])}</td><td>{r["applicable_from"]}</td></tr>')
    parts.append(f'</table></div></div></div>')

    # ── Remuneration Grades ──
    parts.append(f'<div class="section" id="grades"><div class="section-title">{t(msgs,"dashboard.section_remuneration_grades")}</div>')
    grade_labels = {
        "health_insurance": t(msgs, "dashboard.health_insurance"),
        "pension_insurance": t(msgs, "dashboard.pension_insurance"),
    }
    for gt in [("health_insurance", grade_labels["health_insurance"]), ("pension_insurance", grade_labels["pension_insurance"])]:
        grades = fetch_all("SELECT * FROM pay_jp_standard_remuneration_grades WHERE grade_type=%s ORDER BY grade_number", (gt[0],))
        parts.append(f'<div class="card" style="margin-bottom:12px"><div class="card-header"><h3>{gt[1]}</h3><div class="count">{len(grades)} grades</div></div><div class="card-body"><table><tr>')
        for key in ["grade_number", "min_monthly_amount", "max_monthly_amount", "standard_monthly_amount"]:
            parts.append(f"<th>{col_header(key, lang)}</th>")
        parts.append("</tr>")
        for r in grades[:50]:
            parts.append(f'<tr><td>{r["grade_number"]}</td><td class="num">{fmt(r["min_monthly_amount"])}</td><td class="num">{fmt(r["max_monthly_amount"])}</td><td class="num"><strong>{fmt(r["standard_monthly_amount"])}</strong></td></tr>')
        parts.append('</table></div></div>')
    parts.append('</div>')

    # ── Tax Brackets ──
    parts.append(f'<div class="section" id="tax"><div class="section-title">{t(msgs,"dashboard.section_withholding_tax")}</div>')
    tax_labels = {"monthly": {"zh": "月额表", "ja": "月額表", "en": "Monthly Table"},
                  "daily": {"zh": "日额表", "ja": "日額表", "en": "Daily Table"}}
    for tt in [("monthly", tax_labels["monthly"].get(lang, tax_labels["monthly"]["ja"])),
               ("daily", tax_labels["daily"].get(lang, tax_labels["daily"]["ja"]))]:
        tb = fetch_all("SELECT * FROM pay_jp_withholding_tax_brackets WHERE table_type=%s ORDER BY min_salary", (tt[0],))
        parts.append(f'<div class="card" style="margin-bottom:12px"><div class="card-header"><h3>{tt[1]}</h3><div class="count">{len(tb)} brackets</div></div><div class="card-body"><table><tr>')
        parts.append(f"<th>{col_header('min_salary', lang)}</th>")
        for dk in ["tax_dep_0", "tax_dep_1", "tax_dep_2", "tax_dep_3"]:
            parts.append(f"<th>{col_header(dk, lang)}</th>")
        parts.append("</tr>")
        for r in tb[:30]:
            sal = f'{fmt(r["min_salary"])} - {fmt(r["max_salary"])}'
            parts.append(f'<tr><td>{sal}</td>')
            for dk in ["tax_dep_0", "tax_dep_1", "tax_dep_2", "tax_dep_3"]:
                parts.append(f'<td class="num">{fmt(r.get(dk))}</td>')
            parts.append("</tr>")
        parts.append('</table></div></div>')
    parts.append('</div>')

    # ── Accident Insurance ──
    parts.append(f'<div class="section" id="accident"><div class="section-title">{t(msgs,"dashboard.section_accident_insurance")}</div><div class="card">')
    ai = fetch_all("SELECT * FROM pay_jp_accident_insurance_rates ORDER BY industry_code")
    parts.append(f'<div class="card-header"><h3>{t(msgs,"dashboard.section_accident_insurance")}</h3><div class="count">{len(ai)} records</div></div><div class="card-body"><table><tr>')
    for key in ["industry_code", "industry_name_ja", "industry_name_en", "rate"]:
        parts.append(f"<th>{col_header(key, lang)}</th>")
    parts.append("</tr>")
    for r in ai:
        parts.append(f'<tr><td><span class="badge badge-active">{r["industry_code"]}</span></td><td>{r["industry_name_ja"]}</td><td>{r["industry_name_en"] or "-"}</td><td class="num">{fmt(r["rate"])}</td></tr>')
    parts.append(f'</table></div></div></div>')

    # ── Footer ──
    parts.append(f"""<div class="footer">{t(msgs,'dashboard.footer')} | <a href="/api/health">API Health</a> | <a href="/docs">API Docs</a></div>
</div></body></html>""")

    return HTMLResponse("\n".join(parts))
