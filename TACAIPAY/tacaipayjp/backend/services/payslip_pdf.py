"""Generate trilingual payslip PDF/HTML/Text using fpdf2 (zh/ja/en)."""
from fpdf import FPDF
from io import BytesIO
from pathlib import Path
import json

I18N_DIR = Path(__file__).resolve().parents[2] / "i18n"
DEFAULT_LANG = "ja"


def _load_payslip_i18n(lang: str) -> dict:
    """Load payslip i18n messages, falling back to ja then hardcoded defaults."""
    messages = {}
    loaded = False
    for candidate in (DEFAULT_LANG, lang):
        path = I18N_DIR / f"{candidate}.json"
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                messages.update({str(k): str(v) for k, v in data.items()})
                loaded = True
        except (json.JSONDecodeError, IOError):
            pass
    if not loaded:
        # Hardcoded fallback for Japanese
        messages = {
            "payslip.title": "給与明細書",
            "payslip.company": "TACAI株式会社",
            "payslip.employee_number": "社員番号",
            "payslip.name": "氏名",
            "payslip.payroll_month": "給与月",
            "payslip.department": "部署",
            "payslip.section_earnings": "【 支 給 】",
            "payslip.section_deductions": "【 控 除 】",
            "payslip.section_employer": "【 会 社 負 担 】",
            "payslip.item.basic_salary": "基本給",
            "payslip.item.overtime_pay": "時間外手当",
            "payslip.item.commute_allowance": "通勤手当",
            "payslip.item.housing_allowance": "住宅手当",
            "payslip.item.transport_allowance": "交通手当",
            "payslip.item.phone_allowance": "電話手当",
            "payslip.item.family_allowance": "家族手当",
            "payslip.item.position_allowance": "役職手当",
            "payslip.item.project_bonus": "プロジェクト賞与",
            "payslip.item.gross_pay": "総支給額",
            "payslip.item.health_insurance": "健康保険料",
            "payslip.item.pension": "厚生年金保険料",
            "payslip.item.employment_insurance": "雇用保険料",
            "payslip.item.care_insurance": "介護保険料",
            "payslip.item.income_tax": "源泉所得税",
            "payslip.item.resident_tax": "住民税",
            "payslip.item.other_deduction": "その他控除",
            "payslip.item.deduction_total": "控除合計",
            "payslip.item.net_pay": "差引支給額",
            "payslip.item.employer_cost": "会社負担総額",
            "payslip.issued_by": "発行: {company} | TACAI Pay JP",
            "payslip.email_footer": "本メールは自動送信です。ご不明な点はHRまでお問い合わせください。",
        }
    return messages


class JPayslipPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        try:
            self.add_font('CJK', '', '/Library/Fonts/Arial Unicode.ttf', uni=True)
            self.font_name = 'CJK'
        except:
            self.font_name = 'Helvetica'
        self.set_auto_page_break(auto=True, margin=15)
        self._title = '給与明細書'
        self._company = 'TACAI株式会社'

    def header(self):
        self.set_font(self.font_name, '', 14)
        self.cell(0, 8, self._title, new_x="LMARGIN", new_y="NEXT", align='C')
        self.set_font(self.font_name, '', 9)
        self.cell(0, 5, self._company, new_x="LMARGIN", new_y="NEXT", align='C')
        self.ln(4)


def _resolve_msgs(lang_or_msgs) -> dict:
    """Accept either a lang string or a pre-loaded msgs dict."""
    if isinstance(lang_or_msgs, dict):
        return lang_or_msgs
    return _load_payslip_i18n(lang_or_msgs)


def _lang_from_msgs(lang_or_msgs) -> str:
    """Extract a language code from msgs dict or return the string directly."""
    if isinstance(lang_or_msgs, dict):
        # Try to detect lang from msgs content
        return "ja"  # safe default
    return lang_or_msgs


def generate_payslip_pdf(record: dict, lang_or_msgs="ja", entity_name: str = None) -> bytes:
    """Generate a trilingual payslip PDF for a single employee.

    lang_or_msgs: either a language code string ("ja"/"zh"/"en") or a pre-loaded i18n messages dict.
    """
    msgs = _resolve_msgs(lang_or_msgs)
    t = lambda k: msgs.get(k, k)

    company = entity_name or t("payslip.company")

    pdf = JPayslipPDF()
    pdf._title = t("payslip.title")
    pdf._company = company
    pdf.add_page()
    f = pdf.font_name

    def row(label, val, bold=False):
        pdf.set_font(f, '', 10)
        pdf.cell(70, 6, label)
        pdf.set_font(f, '', 10)
        pdf.cell(60, 6, f"{'¥'+format(int(val), ',') if val else '-'}", new_x="LMARGIN", new_y="NEXT", align='R')

    def money(v): return float(v or 0)

    # Employee info
    pdf.set_font(f, '', 10)
    pdf.cell(60, 6, f"{t('payslip.employee_number')}: {record.get('employee_number','')}", new_x="RIGHT")
    pdf.cell(60, 6, f"{t('payslip.name')}: {record.get('employee_name','')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(60, 6, f"{t('payslip.payroll_month')}: {record.get('payroll_month','')}", new_x="RIGHT")
    pdf.cell(60, 6, f"{t('payslip.department')}: {record.get('department_label','')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Earnings
    pdf.set_font(f, '', 12)
    pdf.cell(0, 8, t("payslip.section_earnings"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(0); pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x()+190, pdf.get_y()); pdf.ln(2)

    row(t("payslip.item.basic_salary"), money(record.get('basic_salary')))
    row(t("payslip.item.overtime_pay"), money(record.get('overtime_pay_calc')))
    row(t("payslip.item.commute_allowance"), money(record.get('commute_allowance')))
    row(t("payslip.item.housing_allowance"), money(record.get('housing_allowance')))
    row(t("payslip.item.transport_allowance"), money(record.get('transport_allowance')))
    row(t("payslip.item.phone_allowance"), money(record.get('phone_allowance')))
    row(t("payslip.item.family_allowance"), money(record.get('family_allowance')))
    row(t("payslip.item.position_allowance"), money(record.get('position_allowance')))
    row(t("payslip.item.project_bonus"), money(record.get('project_bonus')))
    gross = money(record.get('gross_pay'))
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x()+130, pdf.get_y()); pdf.ln(1)
    row(t("payslip.item.gross_pay"), gross, bold=True)
    pdf.ln(4)

    # Deductions
    pdf.set_font(f, '', 12)
    pdf.cell(0, 8, t("payslip.section_deductions"), new_x="LMARGIN", new_y="NEXT")
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x()+190, pdf.get_y()); pdf.ln(2)

    row(t("payslip.item.health_insurance"), money(record.get('health_insurance_employee')))
    row(t("payslip.item.pension"), money(record.get('pension_employee')))
    row(t("payslip.item.employment_insurance"), money(record.get('employment_insurance_employee')))
    row(t("payslip.item.care_insurance"), money(record.get('care_insurance_employee')))
    row(t("payslip.item.income_tax"), money(record.get('income_tax')))
    row(t("payslip.item.resident_tax"), money(record.get('monthly_resident_tax')))
    row(t("payslip.item.other_deduction"), money(record.get('recurring_deductions')))
    ded = money(record.get('deduction_total'))
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x()+130, pdf.get_y()); pdf.ln(1)
    row(t("payslip.item.deduction_total"), ded, bold=True)
    pdf.ln(4)

    # Net pay
    pdf.set_font(f, '', 14)
    net = money(record.get('net_pay'))
    pdf.cell(0, 10, '', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(80, 10, t("payslip.item.net_pay"), new_x="RIGHT")
    pdf.set_font(f, '', 14)
    pdf.cell(60, 10, f"¥{int(net):,}" if net else '-', new_x="LMARGIN", new_y="NEXT", align='R')
    pdf.ln(4)

    # Employer cost
    pdf.set_font(f, '', 10)
    pdf.cell(0, 7, t("payslip.section_employer"), new_x="LMARGIN", new_y="NEXT")
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x()+190, pdf.get_y()); pdf.ln(2)
    emp = money(record.get('employer_cost_total'))
    pdf.cell(80, 6, f"{t('payslip.item.employer_cost')}: ¥{int(emp):,}" if emp else '-', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Footer
    pdf.set_font(f, '', 8)
    issued = t("payslip.issued_by").replace("{company}", company)
    pdf.cell(0, 5, issued, new_x="LMARGIN", new_y="NEXT", align='C')

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def generate_payslip_html(record: dict, lang_or_msgs="ja") -> str:
    """Generate trilingual payslip as HTML.

    lang_or_msgs: either a language code string ("ja"/"zh"/"en") or a pre-loaded i18n messages dict.
    """
    msgs = _resolve_msgs(lang_or_msgs)
    lang = _lang_from_msgs(lang_or_msgs)
    t = lambda k: msgs.get(k, k)

    def money(v): return float(v or 0)
    def mf(v): return f"¥{int(v):,}" if v else "-"
    def row(l, v, b=False):
        bs = 'font-weight:700;font-size:15px' if b else ''
        return f'<tr><td style="padding:4px 8px;width:180px">{l}</td><td style="padding:4px 8px;text-align:right;{bs}">{mf(v)}</td></tr>'

    g = money(record.get('gross_pay')); d = money(record.get('deduction_total'))
    n = money(record.get('net_pay')); e = money(record.get('employer_cost_total'))

    return f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><title>{t('payslip.title')}</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:700px;margin:20px auto;padding:20px;background:#fff}}
.header{{text-align:center;margin-bottom:20px}}.header h1{{font-size:20px;margin:0}}.header p{{font-size:13px;color:#888}}
.info{{display:flex;justify-content:space-between;font-size:12px;margin-bottom:16px;padding:8px 12px;background:#f8f9fa;border-radius:6px}}
.section{{margin-bottom:20px}}.section h2{{font-size:16px;border-bottom:2px solid #333;padding-bottom:4px;margin-bottom:8px}}
table{{width:100%;border-collapse:collapse}}td{{border-bottom:1px solid #eee}}
.total{{background:#f0f0f0;font-weight:700}}
.net{{background:#e8f5e9;padding:12px;border-radius:8px;margin:12px 0;text-align:center}}
.net .amount{{font-size:28px;font-weight:700;color:#2e7d32}}
.footer{{text-align:center;color:#aaa;font-size:11px;margin-top:24px}}
@media print{{body{{margin:0;padding:10px}}.net{{background:#e8f5e9!important;-webkit-print-color-adjust:exact}}}}
</style></head><body>
<div class="header"><h1>{t('payslip.title')}</h1><p>{t('payslip.company')}</p></div>
<div class="info"><div>{t('payslip.employee_number')}: {record.get('employee_number','')}<br>{t('payslip.name')}: {record.get('employee_name','')}</div>
<div>{t('payslip.payroll_month')}: {record.get('payroll_month','')}<br>{t('payslip.department')}: {record.get('department_label','')}</div></div>
<div class="section"><h2>{t('payslip.section_earnings')}</h2><table>
{row(t('payslip.item.basic_salary'), money(record.get('basic_salary')))}
{row(t('payslip.item.overtime_pay'), money(record.get('overtime_pay_calc')))}
{row(t('payslip.item.commute_allowance'), money(record.get('commute_allowance')))}
{row(t('payslip.item.housing_allowance'), money(record.get('housing_allowance')))}
{row(t('payslip.item.family_allowance'), money(record.get('family_allowance')))}
{row(t('payslip.item.position_allowance'), money(record.get('position_allowance')))}
<tr class="total"><td>{t('payslip.item.gross_pay')}</td><td style="text-align:right">{mf(g)}</td></tr>
</table></div>
<div class="section"><h2>{t('payslip.section_deductions')}</h2><table>
{row(t('payslip.item.health_insurance'), money(record.get('health_insurance_employee')))}
{row(t('payslip.item.pension'), money(record.get('pension_employee')))}
{row(t('payslip.item.employment_insurance'), money(record.get('employment_insurance_employee')))}
{row(t('payslip.item.income_tax'), money(record.get('income_tax')))}
{row(t('payslip.item.resident_tax'), money(record.get('monthly_resident_tax')))}
<tr class="total"><td>{t('payslip.item.deduction_total')}</td><td style="text-align:right">{mf(d)}</td></tr>
</table></div>
<div class="net"><div style="font-size:13px">{t('payslip.item.net_pay')}</div><div class="amount">{mf(n)}</div></div>
<div class="section"><h2>{t('payslip.section_employer')}</h2><table>
<tr><td style="padding:4px 8px">{t('payslip.item.employer_cost')}</td><td style="padding:4px 8px;text-align:right">{mf(e)}</td></tr>
</table></div>
<div class="footer">{t('payslip.issued_by').replace('{company}', t('payslip.company'))}</div>
</body></html>"""


def generate_payslip_text(record: dict, lang_or_msgs="ja") -> str:
    """Generate plain text payslip for email body.

    lang_or_msgs: either a language code string ("ja"/"zh"/"en") or a pre-loaded i18n messages dict.
    """
    msgs = _resolve_msgs(lang_or_msgs)
    t = lambda k: msgs.get(k, k)

    def mf(v): return f"¥{int(v):,}" if v else "-"
    g = float(record.get('gross_pay') or 0)
    d = float(record.get('deduction_total') or 0)
    n = float(record.get('net_pay') or 0)
    emp_cost = float(record.get('employer_cost_total') or 0)

    return f"""
{t('payslip.company')} {t('payslip.title')} / Payslip
{'='*50}
{t('payslip.employee_number')} / Emp No.: {record.get('employee_number','')}
{t('payslip.name')} / Name: {record.get('employee_name','')}
{t('payslip.payroll_month')} / Payroll Month: {record.get('payroll_month','')}

{t('payslip.section_earnings')} / Earnings
  {t('payslip.item.gross_pay')} / Gross Pay: {mf(g)}

{t('payslip.section_deductions')} / Deductions
  {t('payslip.item.deduction_total')} / Total Deductions: {mf(d)}

{t('payslip.item.net_pay')} / Net Pay
  {mf(n)}

{t('payslip.item.employer_cost')} / Employer Cost: {mf(emp_cost)}

---
{t('payslip.email_footer')}
TACAI Pay JP
"""
