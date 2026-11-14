#!/usr/bin/env python3
"""Generate adversarial upload fixtures and drive the live API journey.

Usage:
  PYTHONPATH=src:. python scripts/stress_upload_live.py [--api http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import traceback
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "testdata" / "stress"
LOG = OUT / "logs" / f"stress_{int(time.time())}.jsonl"


def _write_csv(path: Path, rows: list[dict], encoding: str = "utf-8", sep: str = ",") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding=encoding, sep=sep)


def generate_fixtures() -> list[dict]:
    """Return list of {path, label, currency, date_format, selected_sheet?, mapping?, expect}."""
    OUT.mkdir(parents=True, exist_ok=True)
    specs: list[dict] = []

    # 1) Large POS CSV (~25k rows) with gaps, cancellations, alnum customers, dup invoices
    n = 25_000
    rows = []
    for i in range(n):
        inv = f"INV-{i // 3}"  # duplicate invoices across lines
        cid = f"C-{1000 + (i % 400)}" if i % 17 else ("" if i % 51 == 0 else f"CUST{i%90}")
        price = None if i % 41 == 0 else round(1.5 + (i % 40) * 0.25, 2)
        qty = -(i % 7 + 1) if i % 53 == 0 else (i % 5 + 1)
        desc = "" if i % 61 == 0 else f"Item {i % 200}"
        date = "" if i % 71 == 0 else f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"
        cur = ["EGP", "USD", "EUR"][i % 3]
        rows.append(
            {
                "Invoice": inv,
                "StockCode": f"SKU{i % 180}",
                "Description": desc,
                "Quantity": qty,
                "InvoiceDate": date,
                "Price": price if price is not None else "",
                "Customer ID": cid,
                "Country": "EG",
                "Currency": cur,
            }
        )
    p = OUT / "large_mixed_currency_gaps.csv"
    _write_csv(p, rows)
    specs.append(
        {
            "path": p,
            "label": "large_mixed_currency_gaps",
            "currency": "EGP",
            "date_format": "iso",
            "mapping": {
                "invoice": "Invoice",
                "stock_code": "StockCode",
                "description": "Description",
                "quantity": "Quantity",
                "invoice_date": "InvoiceDate",
                "unit_price": "Price",
                "customer_id": "Customer ID",
                "country": "Country",
                "row_currency": "Currency",
            },
            "analysis_currency_filter": "EGP",
            "expect": {"sales_ge": 0, "customers": True},
        }
    )

    # 2) Multi-sheet Excel: empty + summary + sales with missing prices; gap-fill must keep others
    book = OUT / "multisheet_empty_sales.xlsx"
    with pd.ExcelWriter(book, engine="openpyxl") as w:
        pd.DataFrame().to_excel(w, sheet_name="EmptyJunk", index=False)
        pd.DataFrame({"note": ["ignore"], "total": [999]}).to_excel(
            w, sheet_name="Summary", index=False
        )
        sales = []
        for i in range(800):
            sales.append(
                {
                    "Invoice": f"X{i}",
                    "StockCode": f"A{i % 40}",
                    "Description": "Widget" if i % 9 else "",
                    "Quantity": 2 if i % 11 else "",
                    "InvoiceDate": f"15/{(i % 12) + 1}/2023",
                    "Price": "" if i % 13 == 0 else 10.0 + (i % 5),
                    "Customer ID": f"EG-{i % 50}",
                    "Country": "Egypt",
                }
            )
            # seed peers for smart price fill
            if i < 40:
                for k in range(4):
                    sales.append(
                        {
                            "Invoice": f"SEED-{i}-{k}",
                            "StockCode": f"A{i}",
                            "Description": "Widget",
                            "Quantity": 1,
                            "InvoiceDate": "01/01/2023",
                            "Price": 12.0,
                            "Customer ID": "EG-SEED",
                            "Country": "Egypt",
                        }
                    )
        pd.DataFrame(sales).to_excel(w, sheet_name="SalesLines", index=False)
        pd.DataFrame({"meta": ["v1"]}).to_excel(w, sheet_name="Meta", index=False)
    specs.append(
        {
            "path": book,
            "label": "multisheet_empty_sales",
            "currency": "EGP",
            "date_format": "dayfirst",
            "selected_sheet": "SalesLines",
            "mapping": {
                "invoice": "Invoice",
                "stock_code": "StockCode",
                "description": "Description",
                "quantity": "Quantity",
                "invoice_date": "InvoiceDate",
                "unit_price": "Price",
                "customer_id": "Customer ID",
                "country": "Country",
            },
            "do_gap_fill_smart": True,
            "expect": {"preserve_sheets": ["EmptyJunk", "Summary", "SalesLines", "Meta"]},
        }
    )

    # 3) Line-amount only (no unit price) + messy headers
    line_rows = []
    for i in range(500):
        line_rows.append(
            {
                "Sale Date": f"2023-06-{(i % 28) + 1:02d}",
                "Item Name": f"Bread {i % 20}",
                "Qty": 1 + (i % 3),
                "LineTotal": round((1 + (i % 3)) * 4.5, 2),
                "Till": f"T{i % 4}",
            }
        )
    p = OUT / "line_amount_only_messy.csv"
    _write_csv(p, line_rows)
    specs.append(
        {
            "path": p,
            "label": "line_amount_only_messy",
            "currency": "EGP",
            "date_format": "iso",
            "mapping": {
                "invoice_date": "Sale Date",
                "description": "Item Name",
                "quantity": "Qty",
                "line_amount": "LineTotal",
            },
            "expect": {
                "sales": sum(r["LineTotal"] for r in line_rows),
                "no_missing_unit_price_issue": True,
            },
        }
    )

    # 4) Arabic headers + BOM + semicolon
    ar_rows = []
    for i in range(200):
        ar_rows.append(
            {
                "رقم الفاتورة": f"F{i}",
                "كود الصنف": f"S{i % 30}",
                "الوصف": f"منتج {i % 10}",
                "الكمية": 1 + (i % 4),
                "تاريخ الفاتورة": f"2024-02-{(i % 28) + 1:02d}",
                "سعر الوحدة": round(5 + (i % 7) * 0.5, 2),
                "رقم العميل": f"ع-{i % 40}",
                "البلد": "مصر",
            }
        )
    p = OUT / "arabic_semicolon_bom.csv"
    path_parent = p.parent
    path_parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    pd.DataFrame(ar_rows).to_csv(buf, index=False, sep=";")
    p.write_bytes("\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8"))
    specs.append(
        {
            "path": p,
            "label": "arabic_semicolon_bom",
            "currency": "EGP",
            "date_format": "iso",
            "expect": {"sales_ge": 0},
        }
    )

    # 5) Alphanumeric customers + cancelations + weird spaces in headers
    weird = []
    for i in range(300):
        weird.append(
            {
                " Invoice No ": f"N{i // 2}",
                "Product Code": f"P{i % 25}",
                " Name ": f"Thing {i % 25}",
                "Qty ": -(i % 3 + 1) if i % 19 == 0 else (i % 4 + 1),
                "Date": f"{(i % 28) + 1:02d}/07/2024",
                "Unit Price": 8.0,
                "CustId": f"AB-{i % 60:04d}",
                "Country": "SA",
            }
        )
    p = OUT / "alnum_cancel_spaced_headers.csv"
    _write_csv(p, weird)
    specs.append(
        {
            "path": p,
            "label": "alnum_cancel_spaced_headers",
            "currency": "SAR",
            "date_format": "dayfirst",
            "mapping": {
                "invoice": " Invoice No ",
                "stock_code": "Product Code",
                "description": " Name ",
                "quantity": "Qty ",
                "invoice_date": "Date",
                "unit_price": "Unit Price",
                "customer_id": "CustId",
                "country": "Country",
            },
            "expect": {"customers_include": ["AB-0001", "AB-0002"], "sales_ge": 0},
        }
    )

    # 6) Duplicate column names / ambiguous amount
    amb = []
    for i in range(150):
        amb.append(
            {
                "Date": f"2024-01-{(i % 28) + 1:02d}",
                "SKU": f"Z{i % 20}",
                "Desc": f"Z item {i % 20}",
                "Qty": 2,
                "Amount": 20.0,  # ambiguous: line vs unit
                "Amount2": 10.0,
                "Customer": f"U{i}",
            }
        )
    p = OUT / "ambiguous_amount.csv"
    _write_csv(p, amb)
    specs.append(
        {
            "path": p,
            "label": "ambiguous_amount",
            "currency": "USD",
            "date_format": "iso",
            "mapping": {
                "invoice_date": "Date",
                "stock_code": "SKU",
                "description": "Desc",
                "quantity": "Qty",
                "line_amount": "Amount",
                "customer_id": "Customer",
            },
            "expect": {"sales": 150 * 20.0},
        }
    )

    # 7) Tiny edge: only headers / almost empty
    p = OUT / "headers_only.csv"
    p.write_text("Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n", encoding="utf-8")
    specs.append(
        {
            "path": p,
            "label": "headers_only",
            "currency": "USD",
            "date_format": "iso",
            "expect": {"allow_fail_upload_or_empty": True},
        }
    )

    # 8) latin-1 flavored bytes with £ in description (saved as utf-8 still but with specials)
    lat = []
    for i in range(100):
        lat.append(
            {
                "Invoice": f"L{i}",
                "StockCode": f"L{i%10}",
                "Description": f"Café £ item {i}",
                "Quantity": 1,
                "InvoiceDate": "2024-03-01",
                "Price": 3.5,
                "Customer ID": 1000 + i,
                "Country": "UK",
            }
        )
    p = OUT / "special_chars.csv"
    _write_csv(p, lat)
    specs.append(
        {
            "path": p,
            "label": "special_chars",
            "currency": "GBP",
            "date_format": "iso",
            "expect": {"sales": 350.0},
        }
    )

    # 9) Medium multi-currency filter EUR only
    mc = []
    for i in range(1000):
        cur = ["USD", "EUR", "GBP"][i % 3]
        mc.append(
            {
                "Invoice": f"M{i}",
                "StockCode": "ONE",
                "Description": "Same",
                "Quantity": 1,
                "InvoiceDate": "2024-05-01",
                "Price": 10.0,
                "Customer ID": f"M{i}",
                "Country": "DE",
                "Currency": cur,
            }
        )
    p = OUT / "filter_eur_only.csv"
    _write_csv(p, mc)
    specs.append(
        {
            "path": p,
            "label": "filter_eur_only",
            "currency": "USD",
            "date_format": "iso",
            "analysis_currency_filter": "EUR",
            "mapping": {
                "invoice": "Invoice",
                "stock_code": "StockCode",
                "description": "Description",
                "quantity": "Quantity",
                "invoice_date": "InvoiceDate",
                "unit_price": "Price",
                "customer_id": "Customer ID",
                "country": "Country",
                "row_currency": "Currency",
            },
            "expect": {"sales": 10.0 * (1000 // 3 + (1 if 1000 % 3 > 1 else 0)), "currency_label": "EUR"},
        }
    )
    # EUR indices: 1,4,7,... → count = ceil((1000-1)/3) = 334? Actually i%3==1 → 334 for 0..999
    eur_count = sum(1 for i in range(1000) if i % 3 == 1)
    specs[-1]["expect"]["sales"] = 10.0 * eur_count

    return specs


def _log(event: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


def run_journey(api: str, spec: dict) -> dict:
    path: Path = spec["path"]
    label = spec["label"]
    result: dict = {"label": label, "path": str(path), "ok": False, "steps": []}
    mime = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if path.suffix.lower() == ".xlsx"
        else "text/csv"
    )
    try:
        with path.open("rb") as fh:
            up = requests.post(f"{api}/api/upload", files={"file": (path.name, fh, mime)}, timeout=120)
        result["steps"].append({"upload": up.status_code, "body": _clip(up)})
        if up.status_code != 200:
            if spec.get("expect", {}).get("allow_fail_upload_or_empty"):
                result["ok"] = True
                result["note"] = "empty/headers-only rejected or empty as expected"
                return result
            result["error"] = f"upload {up.status_code}"
            return result
        sid = up.json()["session_id"]
        result["session_id"] = sid
        upj = up.json()

        if upj.get("needs_sheet_selection") or spec.get("selected_sheet"):
            sheet = spec.get("selected_sheet") or "SalesLines"
            sel = requests.post(
                f"{api}/api/upload/settings",
                json={"session_id": sid, "selected_sheet": sheet},
                timeout=60,
            )
            result["steps"].append({"select_sheet": sel.status_code, "body": _clip(sel)})
            if sel.status_code != 200:
                result["error"] = "sheet select failed"
                return result

        settings_body = {
            "session_id": sid,
            "currency_code": spec.get("currency") or "USD",
            "date_format": spec.get("date_format") or "iso",
            "confirm_date_format": True,
        }
        if spec.get("analysis_currency_filter"):
            settings_body["analysis_currency_filter"] = spec["analysis_currency_filter"]
        st = requests.post(f"{api}/api/upload/settings", json=settings_body, timeout=60)
        result["steps"].append({"settings": st.status_code, "body": _clip(st)})
        if st.status_code != 200:
            result["error"] = "settings failed"
            return result

        mapping = spec.get("mapping")
        if not mapping:
            # pull suggestions from profile
            prof0 = requests.get(f"{api}/api/upload/{sid}/profile", timeout=60)
            result["steps"].append({"profile0": prof0.status_code})
            if prof0.status_code == 200:
                mapping = (prof0.json().get("mapping") or {}).get("effective_mapping") or {}

        if mapping:
            mp = requests.post(
                f"{api}/api/upload/mapping",
                json={"session_id": sid, "mapping": mapping, "confirm": True},
                timeout=60,
            )
            result["steps"].append({"mapping": mp.status_code, "body": _clip(mp)})
            if mp.status_code != 200:
                # headers-only may fail capability check
                if spec.get("expect", {}).get("allow_fail_upload_or_empty"):
                    result["ok"] = True
                    result["note"] = "mapping rejected for empty file"
                    return result
                result["error"] = "mapping failed"
                return result

        conf = requests.post(
            f"{api}/api/upload/confirm-profile",
            json={"session_id": sid, "confirmed": True},
            timeout=30,
        )
        result["steps"].append({"confirm_profile": conf.status_code})

        props = requests.post(
            f"{api}/api/upload/cleaning-proposals?session_id={sid}", timeout=180
        )
        result["steps"].append({"proposals": props.status_code, "body": _clip(props, 800)})
        if props.status_code != 200:
            result["error"] = "proposals failed"
            return result
        pj = props.json()

        expect = spec.get("expect") or {}
        if expect.get("no_missing_unit_price_issue"):
            for row in pj.get("unresolved_preview") or []:
                issues = row.get("issues") or []
                if "unit_price" in issues or "missing_unit_price" in issues:
                    result["error"] = f"line_amount flagged unit_price issues: {issues}"
                    return result
            drop = next(
                (p for p in pj.get("proposals") or [] if p.get("id") == "drop_non_finite_qty_price"),
                None,
            )
            # should not wipe most rows
            if drop and drop.get("rows_affected", 0) > (pj.get("baseline") or {}).get("rows", 0) * 0.5:
                result["error"] = f"drop_non_finite wiped too many: {drop}"
                return result

        if spec.get("do_gap_fill_smart"):
            pref = requests.post(
                f"{api}/api/upload/gap-fill-preference",
                json={"session_id": sid, "preference": "smart"},
                timeout=30,
            )
            result["steps"].append({"gap_pref": pref.status_code})
            gf = requests.post(
                f"{api}/api/upload/gap-fill",
                json={"session_id": sid, "patches": [], "apply_all_smart": True},
                timeout=180,
            )
            result["steps"].append({"gap_fill": gf.status_code, "body": _clip(gf, 600)})
            # apply_all_smart with no suggestions may 400 — that's OK if no patches
            if gf.status_code not in (200, 400):
                result["error"] = f"gap_fill unexpected {gf.status_code}"
                return result
            if expect.get("preserve_sheets") and path.suffix.lower() == ".xlsx":
                # re-download not available; check via reading session file through overview OK
                # Verify sheets by opening the session path from API meta? Use profile ok + local rewrite check via second overview
                pass

        accepted = [p["id"] for p in (pj.get("proposals") or []) if p.get("id")][:5]
        acc = requests.post(
            f"{api}/api/upload/accept-cleaning",
            json={"session_id": sid, "accepted_ids": accepted},
            timeout=30,
        )
        result["steps"].append({"accept": acc.status_code})

        ov = requests.get(f"{api}/api/upload/{sid}/overview", timeout=180)
        result["steps"].append({"overview": ov.status_code, "body": _clip(ov, 600)})
        if ov.status_code != 200:
            result["error"] = "overview failed"
            return result
        ovj = ov.json()
        sales = float((ovj.get("metrics") or {}).get("sales") or 0)
        result["sales"] = sales
        result["currency_code"] = ovj.get("currency_code")
        result["currency_label"] = ovj.get("currency_label")

        if "sales" in expect and abs(sales - float(expect["sales"])) > 0.05:
            result["error"] = f"sales mismatch got={sales} want={expect['sales']}"
            return result
        if "sales_ge" in expect and sales < float(expect["sales_ge"]):
            result["error"] = f"sales {sales} < {expect['sales_ge']}"
            return result
        if expect.get("currency_label") and ovj.get("currency_label") != expect["currency_label"]:
            result["error"] = (
                f"currency_label got={ovj.get('currency_label')} want={expect['currency_label']}"
            )
            return result

        if expect.get("customers") or expect.get("customers_include"):
            cust = requests.get(f"{api}/api/upload/{sid}/customers", timeout=120)
            result["steps"].append({"customers": cust.status_code})
            if cust.status_code != 200:
                result["error"] = "customers failed"
                return result
            ids = {str(c.get("customer_id")) for c in cust.json().get("customers") or []}
            result["customer_sample"] = list(sorted(ids))[:10]
            for want in expect.get("customers_include") or []:
                if want not in ids:
                    result["error"] = f"missing customer_id {want} in {result['customer_sample']}"
                    return result

        # products / segments smoke
        for ep in ("products", "segments"):
            r = requests.get(f"{api}/api/upload/{sid}/{ep}", timeout=120)
            result["steps"].append({ep: r.status_code})
            if r.status_code not in (200, 400):
                result["error"] = f"{ep} {r.status_code}"
                return result

        # sheet preservation check for xlsx gap-fill
        if expect.get("preserve_sheets") and path.suffix.lower() == ".xlsx":
            # Find session file: API stores under data/uploads/tmp/<sid>/
            tmp = ROOT / "data" / "uploads" / "tmp"
            session_dirs = list(tmp.glob(f"*{sid}*")) if tmp.exists() else []
            # also try exact sid folder
            cand = tmp / sid if tmp.exists() else None
            files = []
            if cand and cand.exists():
                files = list(cand.glob("*"))
            for d in session_dirs:
                files.extend(d.glob("*"))
            xlsx_files = [f for f in files if f.suffix.lower() == ".xlsx"]
            if xlsx_files:
                sheets = pd.ExcelFile(xlsx_files[0]).sheet_names
                result["session_sheets"] = sheets
                for name in expect["preserve_sheets"]:
                    if name not in sheets:
                        result["error"] = f"lost sheet {name}; have {sheets}"
                        return result

        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _clip(resp: requests.Response, n: int = 400) -> str:
    try:
        text = resp.text
    except Exception:  # noqa: BLE001
        return ""
    return text[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--generate-only", action="store_true")
    args = ap.parse_args()

    print(f"Generating fixtures under {OUT} …", flush=True)
    specs = generate_fixtures()
    print(f"Generated {len(specs)} fixtures", flush=True)
    if args.generate_only:
        for s in specs:
            print(s["label"], s["path"], s["path"].stat().st_size)
        return 0

    health = requests.get(f"{args.api}/api/health", timeout=10)
    assert health.status_code == 200, health.text

    failures = []
    for spec in specs:
        print(f"\n=== {spec['label']} ({spec['path'].name}) ===", flush=True)
        t0 = time.time()
        res = run_journey(args.api, spec)
        res["elapsed_s"] = round(time.time() - t0, 2)
        _log(res)
        status = "PASS" if res.get("ok") else "FAIL"
        print(f"{status} in {res['elapsed_s']}s — {res.get('error') or res.get('note') or 'ok'} sales={res.get('sales')}", flush=True)
        if not res.get("ok"):
            failures.append(res)

    summary = {
        "total": len(specs),
        "failed": len(failures),
        "log": str(LOG),
        "failures": [{"label": f["label"], "error": f.get("error"), "steps": f.get("steps")} for f in failures],
    }
    summary_path = OUT / "logs" / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("\nSUMMARY", json.dumps(summary, indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
