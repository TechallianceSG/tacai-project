#!/usr/bin/env python3
"""Salary slip PDF generator for TAC-salary system."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
    )
    from reportlab.platypus.flowables import Image
except ImportError:
    print("Warning: reportlab not installed. PDF generation will not work.")
    print("Install with: pip install reportlab")
    raise


class PayslipPDFGenerator:
    """Generate salary slip PDF documents."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to register fonts, fallback to default
        try:
            # Register Chinese fonts if available
            if os.path.exists("/System/Library/Fonts/PingFang.ttc"):
                pdfmetrics.registerFont(TTFont("PingFang", "/System/Library/Fonts/PingFang.ttc"))
            elif os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
                pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        except Exception:
            pass  # Use default fonts
        
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom paragraph styles for payslip."""
        self.styles.add(ParagraphStyle(
            name='Title',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center
        ))
        
        self.styles.add(ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=20,
            spaceBefore=20
        ))
        
        self.styles.add(ParagraphStyle(
            name='Normal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=10
        ))
        
        self.styles.add(ParagraphStyle(
            name='Small',
            parent=self.styles['Normal'],
            fontSize=8,
            spaceAfter=6
        ))
    
    def generate_payslip_pdf(self, record: Dict[str, Any], batch: Dict[str, Any]) -> str:
        """Generate a single payslip PDF."""
        # Generate unique filename
        employee_id = record.get("employee_id", "unknown")
        payroll_month = record.get("payroll_month", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"payslip_{employee_id}_{payroll_month}_{timestamp}.pdf"
        filepath = self.output_dir / filename
        
        # Create PDF document
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=A4,
            rightMargin=50,
            leftMargin=50,
            topMargin=50,
            bottomMargin=30
        )
        
        # Build PDF content
        story = []
        self._add_header(story, record, batch)
        self._add_employee_info(story, record)
        self._add_earnings(story, record)
        self._add_deductions(story, record)
        self._add_summary(story, record)
        self._add_footer(story, record, batch)
        
        # Build PDF
        doc.build(story)
        
        return str(filepath)
    
    def _add_header(self, story: List, record: Dict[str, Any], batch: Dict[str, Any]):
        """Add payslip header."""
        # Company info
        entity = batch.get("entity_snapshot", {})
        company_name = entity.get("entity_name_local", entity.get("entity_name_en", "Tech Alliance"))
        
        title = Paragraph(f"薪资单 / Payslip", self.styles['Title'])
        story.append(title)
        story.append(Spacer(1, 10))
        
        # Company info
        company_info = f"""
        <b>{company_name}</b><br/>
        法人代码: {entity.get("entity_code", "")} | 
        发放月份: {record.get("payroll_month", "")} | 
        货币: {record.get("currency", "SGD")}
        """
        story.append(Paragraph(company_info, self.styles['Subtitle']))
        story.append(Spacer(1, 20))
    
    def _add_employee_info(self, story: List, record: Dict[str, Any]):
        """Add employee information table."""
        employee = record.get("employee_snapshot", {})
        
        # Employee info data
        employee_data = [
            ["员工编号 / Employee No:", employee.get("employee_no", "")],
            ["员工姓名 / Employee Name:", employee.get("employee_name", "")],
            ["部门 / Department:", employee.get("department", "")],
            ["职位 / Position:", employee.get("position", "")],
            ["雇佣类型 / Employment Type:", employee.get("employment_type", "")],
            ["银行账户 / Bank:", employee.get("bank_account_snapshot", {}).get("account_number", "")]
        ]
        
        # Create table
        employee_table = Table(employee_data, colWidths=[2.5*inch, 4*inch])
        employee_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(employee_table)
        story.append(Spacer(1, 20))
    
    def _add_earnings(self, story: List, record: Dict[str, Any]):
        """Add earnings section."""
        story.append(Paragraph("收入明细 / Earnings Details", self.styles['Subtitle']))
        
        earnings = record.get("earnings", {})
        earnings_data = [["项目 / Item", "金额 / Amount"]]
        
        # Add earnings items
        earnings_items = [
            ("基本工资 / Basic Salary", earnings.get("base_salary", 0)),
            ("岗位津贴 / Position Allowance", earnings.get("position_allowance", 0)),
            ("交通津贴 / Commute Allowance", earnings.get("commute_allowance", 0)),
            ("住房津贴 / Housing Allowance", earnings.get("housing_allowance", 0)),
            ("其他津贴 / Other Allowance", earnings.get("other_allowance", 0)),
            ("加班费 / Overtime Pay", earnings.get("overtime_pay", 0)),
            ("奖金 / Bonus", earnings.get("bonus", 0)),
            ("其他收入 / Other Earnings", earnings.get("other_earnings", 0))
        ]
        
        for item, amount in earnings_items:
            earnings_data.append([item, f"{amount:,.2f}"])
        
        # Add totals
        gross_pay = record.get("gross_pay", 0)
        earnings_data.append(["总收入 / Gross Pay", f"<b>{gross_pay:,.2f}</b>"])
        
        # Create table
        earnings_table = Table(earnings_data, colWidths=[3*inch, 2*inch])
        earnings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgreen),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(earnings_table)
        story.append(Spacer(1, 20))
    
    def _add_deductions(self, story: List, record: Dict[str, Any]):
        """Add deductions section."""
        story.append(Paragraph("扣款明细 / Deductions Details", self.styles['Subtitle']))
        
        deductions = record.get("deductions", {})
        deductions_data = [["项目 / Item", "金额 / Amount"]]
        
        # Add deduction items
        deduction_items = [
            ("社保 / Social Insurance", deductions.get("social_insurance_employee", 0)),
            ("公积金 / Housing Fund", deductions.get("housing_fund_employee", 0)),
            ("个人所得税 / Income Tax", deductions.get("individual_income_tax", 0)),
            ("CPF (员工)", deductions.get("cpf_employee", 0)),
            ("其他扣款 / Other Deductions", deductions.get("other_deduction", 0))
        ]
        
        for item, amount in deduction_items:
            deductions_data.append([item, f"{amount:,.2f}"])
        
        # Add totals
        deduction_total = record.get("deduction_total", 0)
        deductions_data.append(["总扣款 / Total Deductions", f"<b>{deduction_total:,.2f}</b>"])
        
        # Create table
        deductions_table = Table(deductions_data, colWidths=[3*inch, 2*inch])
        deductions_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightcoral),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightpink),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(deductions_table)
        story.append(Spacer(1, 20))
    
    def _add_summary(self, story: List, record: Dict[str, Any]):
        """Add payment summary."""
        story.append(Paragraph("付款摘要 / Payment Summary", self.styles['Subtitle']))
        
        summary_data = [
            ["项目 / Item", "金额 / Amount"],
            ["应发工资 / Gross Pay", f"{record.get('gross_pay', 0):,.2f}"],
            ["总扣款 / Total Deductions", f"{record.get('deduction_total', 0):,.2f}"],
            ["调整金额 / Adjustments", f"{record.get('manual_adjustments_total', 0):,.2f}"],
            ["实发工资 / Net Pay", f"<b>{record.get('net_pay', 0):,.2f}</b>"]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.darkgreen),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 20))
    
    def _add_footer(self, story: List, record: Dict[str, Any], batch: Dict[str, Any]):
        """Add footer information."""
        footer_text = f"""
        <font size="8">
        本薪资单由TAC薪资系统自动生成 | Generated by TAC Salary System<br/>
        生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Payroll Month: {record.get('payroll_month', '')}<br/>
        批次ID: {batch.get('batch_id', '')} | 记录ID: {record.get('payroll_record_id', '')}
        </font>
        """
        story.append(Paragraph(footer_text, self.styles['Small']))
        
        # Add page break if more records to process
        if len(story) > 20:  # Approximate page content limit
            story.append(PageBreak())


def generate_payslips_pdf(batch_id: str, records: List[Dict[str, Any]], batch: Dict[str, Any]) -> List[str]:
    """Generate PDF payslips for a batch of records."""
    output_dir = Path("payslips")
    generator = PayslipPDFGenerator(output_dir)
    
    generated_files = []
    for record in records:
        try:
            pdf_path = generator.generate_payslip_pdf(record, batch)
            generated_files.append(pdf_path)
        except Exception as e:
            print(f"Error generating payslip for {record.get('employee_id', 'unknown')}: {e}")
            continue
    
    return generated_files