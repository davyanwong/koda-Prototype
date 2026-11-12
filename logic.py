"""
Core logic for both modules. Plain code does the maths and the matching;
AI (see ai.py) only helps with reading messy invoices and explaining results.
"""
import io
import re
from datetime import date

import pandas as pd

# ==========================================================================
# 6b  INVOICE CHECKING
# ==========================================================================
LINE_RE = re.compile(r"^([A-Z]{2,3}-\d+)\s+(.+?)\s+(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$")


def pdf_text(file_bytes: bytes) -> str:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _first(patterns, text):
    for p in patterns:
        m = re.search(p, text, re.I | re.M)
        if m:
            return m.group(1).strip()
    return ""


def parse_invoice_text(text: str) -> dict:
    """Rule-based extraction. Works on the text-PDF layouts in the mock data.
    Real supplier layouts vary a lot: that is where the AI extractor helps."""
    lines_in = [l.strip() for l in text.splitlines() if l.strip()]
    inv = {
        "supplier": lines_in[0] if lines_in else "",
        "invoice_no": _first([r"Invoice\s*(?:No\.?|Number|#)\s*[:\-]?\s*(\S+)",
                              r"\bInv\s*#\s*[:\-]?\s*(\S+)"], text),
        "date": _first([r"(?:Invoice\s*)?Date\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})"], text),
        "po_no": _first([r"\b(?:PO|P\.O\.|Purchase Order)\s*(?:No\.?|Number|#)?\s*[:\-]?\s*(PO-\d+|[A-Z0-9\-]{4,})"], text),
        "currency": _first([r"(?:Currency\s*[:\-]?|amounts in)\s*([A-Z]{3})\b"], text),
        "total": 0.0,
        "lines": [],
    }
    totals = re.findall(r"(?:TOTAL DUE|Total Due|Grand Total|Amount Payable)\s*[:\-]?\s*([\d,]+\.\d{2})", text)
    if totals:
        inv["total"] = _num(totals[-1])
    for l in lines_in:
        m = LINE_RE.match(l)
        if m:
            inv["lines"].append({
                "item_code": m.group(1), "description": m.group(2),
                "qty": int(m.group(3)), "unit_price": _num(m.group(4)), "amount": _num(m.group(5)),
            })
    return inv


def check_invoice(inv: dict, po: pd.DataFrame, grn: pd.DataFrame, seen: set, tol_pct: float = 1.0):
    """Compare one extracted invoice against POs and goods received.
    Returns (issues, line_table, status)."""
    issues = []

    def add(sev, msg):
        issues.append({"Severity": sev, "Issue": msg})

    no = inv.get("invoice_no", "")
    key = (inv.get("supplier", "").lower(), no.lower())
    if no and key in seen:
        add("High", f"Duplicate: invoice {no} from {inv['supplier']} was already checked")

    po_no = inv.get("po_no", "")
    po_lines = po[po["po_no"] == po_no] if po_no else po.iloc[0:0]
    po_found = not po_lines.empty
    if not po_no:
        add("High", "No PO number found on the invoice")
    elif not po_found:
        add("High", f"{po_no} not found in Koda's records")
    else:
        po_supplier = po_lines.iloc[0]["supplier"]
        po_cur = po_lines.iloc[0]["currency"]
        if po_supplier.strip().lower() != inv.get("supplier", "").strip().lower():
            add("High", f"Supplier on invoice ({inv.get('supplier')}) differs from PO ({po_supplier})")
        if inv.get("currency") and inv["currency"] != po_cur:
            add("High", f"Currency {inv['currency']} on invoice, PO is in {po_cur}")

    lines = inv.get("lines", [])
    if not lines:
        add("High", "No line items could be read from the invoice")
    sum_lines = round(sum(l["amount"] for l in lines), 2)
    if lines and abs(sum_lines - inv.get("total", 0)) > 0.01:
        add("High", f"Invoice total {inv.get('total', 0):,.2f} does not match sum of lines {sum_lines:,.2f}")

    rows = []
    for l in lines:
        result = []
        if abs(l["qty"] * l["unit_price"] - l["amount"]) > 0.01:
            add("Medium", f"{l['item_code']}: qty x price does not equal the line amount")
            result.append("Line maths")
        row = {"Item": l["item_code"], "Inv qty": l["qty"], "PO qty": None, "Received": None,
               "Inv price": l["unit_price"], "PO price": None, "Price diff %": None}
        if po_found:
            match = po_lines[po_lines["item_code"] == l["item_code"]]
            if match.empty:
                add("High", f"{l['item_code']} is not on {po_no}")
                result.append("Not on PO")
            else:
                po_qty = int(match["qty"].sum())
                po_price = float(match.iloc[0]["unit_price"])
                got = grn[(grn["po_no"] == po_no) & (grn["item_code"] == l["item_code"])]["qty_received"].sum()
                diff = (l["unit_price"] - po_price) / po_price * 100
                row.update({"PO qty": po_qty, "Received": int(got), "PO price": po_price,
                            "Price diff %": round(diff, 1)})
                if abs(diff) > tol_pct:
                    add("High", f"{l['item_code']}: price {l['unit_price']:.2f} vs PO {po_price:.2f} ({diff:+.1f}%)")
                    result.append("Price")
                if l["qty"] > po_qty:
                    add("High", f"{l['item_code']}: billed {l['qty']}, only {po_qty} ordered")
                    result.append("Qty > PO")
                if got == 0:
                    add("High", f"{l['item_code']}: no goods received recorded for {po_no}")
                    result.append("Not received")
                elif l["qty"] > got:
                    add("High", f"{l['item_code']}: billed {l['qty']}, only {int(got)} received")
                    result.append("Qty > received")
        row["Result"] = ", ".join(result) if result else "OK"
        rows.append(row)

    if no:
        seen.add(key)
    status = "OK" if not issues else "Review"
    return issues, pd.DataFrame(rows), status


# ==========================================================================
# 6c  PRODUCTION AND MATERIAL PLANNING
# ==========================================================================
def explode_bom(item: str, qty: float, bom: pd.DataFrame, out: dict):
    """Walk the multi-level BOM down to raw materials."""
    kids = bom[bom["parent"] == item]
    if kids.empty:
        out[item] = out.get(item, 0) + qty
        return
    for _, r in kids.iterrows():
        explode_bom(r["component"], qty * r["qty_per"], bom, out)


def build_plan(sales, inventory, bom, open_pos, lead_times, today: date = None):
    """Allocate materials to orders (earliest due date first, key customers first on ties).
    An order only reserves materials if ALL of its materials can arrive by its due date.
    Returns (orders_df, materials_df)."""
    today = today or date.today()
    sales = sales.copy()
    sales["due_date"] = pd.to_datetime(sales["due_date"]).dt.date
    po = open_pos.copy()
    po["eta"] = pd.to_datetime(po["eta"]).dt.date
    po["left"] = po["qty"].astype(float)
    stock = dict(zip(inventory["item_code"], inventory["on_hand"].astype(float)))
    lead = dict(zip(lead_times["item_code"], lead_times["lead_time_days"]))

    sales["_key"] = (sales["customer_type"].str.lower() != "key").astype(int)
    sales = sales.sort_values(["due_date", "_key"]).reset_index(drop=True)

    results, total_need, short_for = [], {}, {}
    for _, o in sales.iterrows():
        needs = {}
        explode_bom(o["product"], o["qty"], bom, needs)
        for k, v in needs.items():
            total_need[k] = total_need.get(k, 0) + v

        shortages = {}
        for item, need in needs.items():
            incoming = po[(po["item_code"] == item) & (po["eta"] <= o["due_date"])]["left"].sum()
            short = need - stock.get(item, 0) - incoming
            if short > 1e-9:
                shortages[item] = short

        days_left = (o["due_date"] - today).days
        if not shortages:
            for item, need in needs.items():          # reserve stock first, then POs
                take = min(need, stock.get(item, 0))
                stock[item] = stock.get(item, 0) - take
                need -= take
                for idx in po[(po["item_code"] == item) & (po["eta"] <= o["due_date"])].sort_values("eta").index:
                    if need <= 1e-9:
                        break
                    t = min(need, po.at[idx, "left"])
                    po.at[idx, "left"] -= t
                    need -= t
            status = "Ready"
            why = f"{o['customer_type']} customer, due in {days_left} days, all materials available."
            action = "Schedule production."
            short_txt = ""
        else:
            status = "At risk"
            parts, acts = [], []
            for item, s in shortages.items():
                later = po[(po["item_code"] == item) & (po["eta"] > o["due_date"]) & (po["left"] > 0)].sort_values("eta")
                if not later.empty:
                    late_days = (later.iloc[0]["eta"] - o["due_date"]).days
                    parts.append(f"{s:g} x {item} short; next PO arrives {late_days} day{'s' if late_days != 1 else ''} after the due date")
                    acts.append(f"Ask supplier to bring {later.iloc[0]['po_no']} ({item}) forward by {late_days}+ day{'s' if late_days != 1 else ''}")
                else:
                    parts.append(f"{s:g} x {item} short; no PO placed (lead time {lead.get(item, '?')} days)")
                    acts.append(f"Place a PO for {item} now (lead time {lead.get(item, '?')} days)")
            why = f"{o['customer_type']} customer, due in {days_left} days. " + "; ".join(parts) + "."
            action = " | ".join(acts) + ". Or tell the customer / split the delivery."
            short_txt = ", ".join(f"{k}: {v:g}" for k, v in shortages.items())
            for k, v in shortages.items():
                short_for.setdefault(k, []).append(f"{o['order_id']} ({v:g} short)")

        results.append({
            "Order": o["order_id"], "Customer": o["customer"], "Type": o["customer_type"],
            "Product": o["product"], "Qty": int(o["qty"]), "Due date": o["due_date"],
            "Status": status, "Short": short_txt, "Why": why, "Suggested action": action,
        })

    orders = pd.DataFrame(results)
    # Suggested production priority: ready orders first (earliest due), then at-risk ones
    orders["_s"] = (orders["Status"] != "Ready").astype(int)
    orders = orders.sort_values(["_s", "Due date"], kind="stable").drop(columns="_s").reset_index(drop=True)
    orders.insert(0, "Priority", range(1, len(orders) + 1))

    mats = []
    for item, need in sorted(total_need.items()):
        oh = float(inventory.loc[inventory["item_code"] == item, "on_hand"].sum())
        inc = float(open_pos.loc[open_pos["item_code"] == item, "qty"].sum())
        mats.append({"Material": item, "Needed (all orders)": need, "On hand": oh,
                     "Incoming POs": inc, "Causing at-risk order": ", ".join(short_for.get(item, []))})
    return orders, pd.DataFrame(mats)
