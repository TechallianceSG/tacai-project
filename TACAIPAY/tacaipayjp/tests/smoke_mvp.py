#!/usr/bin/env python3
"""Smoke test for TACAIPAY JP MVP using temporary local data."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "backend" / "app.py"


def load_app(tmp: Path):
    os.environ["TACAIPAYJP_DATA_DIR"] = str(tmp / "database")
    os.environ["TACAIPAYJP_PAYSLIP_DIR"] = str(tmp / "payslips")
    spec = importlib.util.spec_from_file_location("tacaipayjp_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def read(module, name):
    return module.read_json(name)


def write(module, name, records):
    module.write_json(name, records)


def api(base_url: str, method: str, path: str, payload=None, expect_json=True, ok=(200, 201)):
    body = None
    headers = {"X-TACAI-User": "smoke-http"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            data = res.read()
            assert res.status in ok, (path, res.status, data[:200])
            if expect_json:
                return json.loads(data.decode("utf-8")) if data else {}
            return data
    except urllib.error.HTTPError as exc:
        data = exc.read()
        if exc.code in ok:
            return json.loads(data.decode("utf-8")) if expect_json and data else data
        raise AssertionError(f"{method} {path} failed: {exc.code} {data[:300]!r}") from exc


def expect_error(base_url: str, method: str, path: str, payload=None, status=400):
    try:
        api(base_url, method, path, payload=payload)
    except AssertionError as exc:
        assert str(status) in str(exc), exc
        return
    raise AssertionError(f"expected HTTP {status} for {method} {path}")


def run_function_smoke(app) -> int:
    profiles = [
        app.salary_profile_from_employee({"employee_id": "E001", "employee_number": "JP-001", "display_name": "Monthly Taro", "email": "taro@example.test", "entity_id": "default", "salary_type": "monthly", "base_salary": 320000, "transportation_allowance": 15000}),
        app.salary_profile_from_employee({"employee_id": "E002", "employee_number": "JP-002", "display_name": "Hourly Hana", "email": "hana@example.test", "entity_id": "default", "salary_type": "hourly", "hourly_rate": 2200}),
        app.salary_profile_from_employee({"employee_id": "E003", "employee_number": "JP-003", "display_name": "Daily Ken", "entity_id": "default", "salary_type": "daily", "daily_rate": 18000}),
    ]
    write(app, "salary_master", profiles)

    batch = {
        "batch_id": "batch-smoke",
        "entity_id": "default",
        "payroll_month": "2026-06",
        "payroll_type": "monthly",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "payment_date": "2026-07-25",
        "status": "draft_created",
        "version_no": 1,
        "record_count": 0,
        "gross_total": 0,
        "deduction_total": 0,
        "net_total": 0,
        "employer_cost_total": 0,
        "company_total_cost": 0,
        "active_status": "active",
        "created_at": app.now_iso(),
        "created_by": "smoke",
        "updated_at": app.now_iso(),
    }
    write(app, "payroll_batches", [batch])

    records = [app.create_record_snapshot(batch, profile) for profile in profiles]
    records[0]["attendance"]["overtime_hours"] = 8
    records[0]["attendance"]["absence_days"] = 1
    records[0]["manual_income_tax"] = 8000
    records[0]["manual_resident_tax"] = 12000
    records[1]["attendance"]["regular_hours"] = 120
    records[1]["attendance"]["overtime_hours"] = 10
    records[2]["attendance"]["work_days"] = 18
    write(app, "payroll_records", records)

    params = app.active_parameters("default")
    calculated = []
    for record in read(app, "payroll_records"):
        result, messages = app.calculate_payroll_record(record, params)
        record.update(result)
        record["calculation_messages"] = messages
        record["status"] = "calculated"
        calculated.append(record)
    write(app, "payroll_records", calculated)
    updated_batch = app.recalculate_batch_totals("batch-smoke")

    assert updated_batch["record_count"] == 3
    assert updated_batch["gross_total"] > 0
    assert updated_batch["net_total"] > 0
    assert calculated[0]["net_pay"] > 0
    assert calculated[1]["gross_total"] >= 120 * 2200
    assert calculated[2]["gross_total"] >= 18 * 18000
    assert any("manual" in " ".join(r["calculation_messages"]).lower() or r.get("manual_income_tax") for r in calculated)

    html = app.render_payslip_html(calculated[0], updated_batch)
    payslip_path = Path(os.environ["TACAIPAYJP_PAYSLIP_DIR"]) / "smoke.html"
    payslip_path.write_text(html, encoding="utf-8")
    assert payslip_path.exists()
    assert "Payroll Payslip" in html
    assert "HTML payslip" in html

    csv_body = app.records_to_csv([
        {"employee_number": r["employee_number"], "net_pay": r["net_pay"], "danger": "=1+1"}
        for r in calculated
    ], ["employee_number", "net_pay", "danger"])
    assert csv_body.startswith(b"\xef\xbb\xbf")
    assert b"'=1+1" in csv_body

    app.append_audit("smoke_complete", "batch-smoke", "smoke", after={"ok": True})
    assert read(app, "audit_logs")
    return updated_batch["net_total"]


def run_http_smoke(app) -> dict:
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.TacaipayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        health = api(base_url, "GET", "/health")
        assert health["ok"] and health["default_port"] == 8017

        profiles = [
            {"employee_id": "A001", "employee_number": "API-001", "display_name": "API Monthly", "email": "api.monthly@example.test", "entity_id": "api", "salary_type": "monthly", "base_salary": 350000, "transportation_allowance": 12000},
            {"employee_id": "A002", "employee_number": "API-002", "display_name": "API Hourly", "email": "api.hourly@example.test", "entity_id": "api", "salary_type": "hourly", "hourly_rate": 2400},
            {"employee_id": "A003", "employee_number": "API-003", "display_name": "API Daily", "entity_id": "api", "salary_type": "daily", "daily_rate": 19000},
        ]
        for profile in profiles:
            api(base_url, "POST", "/api/v1/salary-master", profile, ok=(201,))
        expect_error(base_url, "POST", "/api/v1/salary-master", profiles[0], status=400)

        batch = api(base_url, "POST", "/api/v1/batches", {"payroll_month": "2026-07", "entity_id": "api", "payment_date": "2026-08-25"}, ok=(201,))["record"]
        batch_id = batch["batch_id"]
        loaded = api(base_url, "POST", f"/api/v1/batches/{batch_id}/load-master", {})
        assert loaded["loaded"] == 3

        records = api(base_url, "GET", f"/api/v1/records?batch_id={batch_id}")["records"]
        first = records[0]
        api(base_url, "PUT", f"/api/v1/records/{first['record_id']}", {
            "attendance": {"work_days": 20, "regular_hours": 160, "overtime_hours": 6, "late_night_hours": 2, "holiday_hours": 0, "absence_days": 1},
            "manual_income_tax": 9000,
            "manual_resident_tax": 11000,
        })
        calculated = api(base_url, "POST", f"/api/v1/batches/{batch_id}/calculate", {})
        assert calculated["calculated"] == 3
        assert calculated["batch"]["status"] == "calculated"
        assert calculated["batch"]["net_total"] > 0

        for action, expected_status in [
            ("hr-review", "hr_reviewed"),
            ("first-approve", "first_approved"),
        ]:
            result = api(base_url, "POST", f"/api/v1/batches/{batch_id}/{action}", {})
            assert result["record"]["status"] == expected_status

        generated = api(base_url, "POST", f"/api/v1/batches/{batch_id}/payslips/generate", {})
        assert generated["generated"] == 3
        assert generated["batch"]["status"] == "payslips_generated"
        assert generated["records"][0]["document_type"] == "html_payslip"
        expect_error(base_url, "POST", f"/api/v1/batches/{batch_id}/payslips/generate", {}, status=400)

        sent = api(base_url, "POST", f"/api/v1/batches/{batch_id}/payslips/send", {"dry_run": True})
        assert sent["deliveries"] == 3
        assert sent["missing_recipients"] == 1
        deliveries = api(base_url, "GET", "/api/v1/email-deliveries")["records"]
        assert any(d["recipient"] == "api.monthly@example.test" and d["status"] == "dry_run" for d in deliveries)
        assert any(d["status"] == "missing_recipient" for d in deliveries)

        for action, expected_status in [
            ("final-approve", "final_approved"),
            ("finalize", "finalized"),
        ]:
            result = api(base_url, "POST", f"/api/v1/batches/{batch_id}/{action}", {})
            assert result["record"]["status"] == expected_status
        finalized_records = api(base_url, "GET", f"/api/v1/records?batch_id={batch_id}")["records"]
        assert all(r["status"] == "finalized" for r in finalized_records)
        expect_error(base_url, "PUT", f"/api/v1/records/{first['record_id']}", {"manual_income_tax": 1}, status=400)

        prepared = api(base_url, "POST", f"/api/v1/batches/{batch_id}/payment/prepare", {})
        assert prepared["record"]["status"] == "payment_prepared"
        paid = api(base_url, "POST", f"/api/v1/batches/{batch_id}/payment/mark-paid", {})
        assert paid["record"]["status"] == "paid"

        summary = api(base_url, "GET", "/api/v1/reports/summary")
        assert summary["net_total"] > 0
        payslips = api(base_url, "GET", "/api/v1/payslips")["records"]
        html_body = api(base_url, "GET", f"/api/v1/payslips/{payslips[0]['payslip_id']}/download", expect_json=False)
        assert b"Payroll Payslip" in html_body
        finance_csv = api(base_url, "GET", f"/api/v1/batches/{batch_id}/finance-export.csv", expect_json=False)
        payment_csv = api(base_url, "GET", f"/api/v1/batches/{batch_id}/payment-export.csv", expect_json=False)
        assert finance_csv.startswith(b"\xef\xbb\xbf") and payment_csv.startswith(b"\xef\xbb\xbf")

        bad_docs = read(app, "payslip_documents")
        bad_docs.append({"payslip_id": "bad-path", "file_path": "/tmp/tacaipayjp_escape.html"})
        write(app, "payslip_documents", bad_docs)
        expect_error(base_url, "GET", "/api/v1/payslips/bad-path/download", status=400)

        audit = api(base_url, "GET", "/api/v1/audit-logs")["records"]
        actions = {item.get("action") for item in audit}
        for expected in {"batch_create", "batch_calculate", "payslips_generate", "payslips_send", "payment_mark_paid", "export_csv"}:
            assert expected in actions, expected
        return {"records": len(finalized_records), "net_total": summary["net_total"], "deliveries": sent["deliveries"], "missing_recipients": sent["missing_recipients"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app = load_app(tmp)
        app.ensure_database()
        function_net_total = run_function_smoke(app)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app = load_app(tmp)
        app.ensure_database()
        http_result = run_http_smoke(app)

    print(json.dumps({"ok": True, "function_net_total": function_net_total, **http_result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
