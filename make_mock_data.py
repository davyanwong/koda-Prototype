"""
Creates fake Koda data so the prototype works before Koda sends real files.

Run:  python make_mock_data.py
Makes:
  data/purchase_orders.csv, data/goods_received.csv       (for 6b)
  data/invoices/*.pdf + data/invoice_answer_key.csv        (for 6b, with planted errors)
  data/sales_orders.csv, inventory.csv, bom.csv,
  data/open_purchase_orders.csv, lead_times.csv            (for 6c)

Planning dates are set relative to the day you run this script.
"""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DATA = Path(__file__).parent / "data"
INV_DIR = DATA / "invoices"

# --------------------------------------------------------------------------
# 6b: purchase orders and goods received
# --------------------------------------------------------------------------
PO_LINES = [
    # po_no, supplier, currency, item_code, description, qty, unit_price
    ("PO-5001", "Alpha Steel Pte Ltd", "SGD", "RM-101", "Steel sheet 2mm", 100, 45.00),
    ("PO-5002", "Brightline Electronics", "SGD", "RM-105", "Control board", 50, 38.50),
    ("PO-5003", "Alpha Steel Pte Ltd", "SGD", "RM-101", "Steel sheet 2mm", 80, 45.00),
    ("PO-5003", "Alpha Steel Pte Ltd", "SGD", "RM-107", "Gasket set", 60, 12.00),
    ("PO-5004", "Cedar Plastics", "SGD", "RM-102", "Plastic housing", 100, 14.80),
    ("PO-5005", "Cedar Plastics", "SGD", "RM-102", "Plastic housing", 60, 14.80),
    ("PO-5005", "Cedar Plastics", "SGD", "RM-107", "Gasket set", 40, 12.00),
    ("PO-5006", "Delta Fasteners", "SGD", "RM-104", "Fastener kit", 200, 6.20),
    ("PO-5007", "Alpha Steel Pte Ltd", "SGD", "RM-101", "Steel sheet 2mm", 50, 45.00),
    ("PO-5008", "Evergreen Wiring", "SGD", "RM-103", "Copper wire (m)", 500, 2.40),
    ("PO-5009", "Evergreen Wiring", "SGD", "RM-103", "Copper wire (m)", 300, 2.40),
    ("PO-5010", "Brightline Electronics", "SGD", "RM-106", "Motor 24V", 40, 52.00),
]
PO_COLS = ["po_no", "supplier", "currency", "item_code", "description", "qty", "unit_price"]

GRN_ROWS = [
    # po_no, item_code, qty_received   (PO-5009 has no goods received on purpose)
    ("PO-5001", "RM-101", 100),
    ("PO-5002", "RM-105", 50),
    ("PO-5003", "RM-101", 80),
    ("PO-5003", "RM-107", 60),
    ("PO-5004", "RM-102", 100),
    ("PO-5005", "RM-102", 60),
    ("PO-5005", "RM-107", 40),
    ("PO-5006", "RM-104", 200),
    ("PO-5007", "RM-101", 50),
    ("PO-5008", "RM-103", 500),
    ("PO-5010", "RM-106", 40),
]

# --------------------------------------------------------------------------
# 6b: invoices (layout 1 or 2, some with planted errors)
# --------------------------------------------------------------------------
# file, layout, supplier, invoice_no, po_no, currency, lines[(code, desc, qty, price)],
# stated_total (None = correct), expected ("OK"/"Error"), planted issue
INVOICES = [
    ("inv_1001.pdf", 1, "Alpha Steel Pte Ltd", "INV-1001", "PO-5001", "SGD",
     [("RM-101", "Steel sheet 2mm", 100, 45.00)], None, "OK", "Clean"),
    ("inv_1002.pdf", 1, "Brightline Electronics", "INV-1002", "PO-5002", "SGD",
     [("RM-105", "Control board", 50, 38.50)], None, "OK", "Clean"),
    ("inv_1003.pdf", 1, "Alpha Steel Pte Ltd", "INV-1003", "PO-5003", "SGD",
     [("RM-101", "Steel sheet 2mm", 80, 48.60), ("RM-107", "Gasket set", 60, 12.00)],
     None, "Error", "Price 8% above PO"),
    ("inv_1004.pdf", 1, "Cedar Plastics", "INV-1004", "PO-5004", "SGD",
     [("RM-102", "Plastic housing", 120, 14.80)], None, "Error", "Billed 120, ordered and received 100"),
    ("inv_1005_resent.pdf", 1, "Brightline Electronics", "INV-1002", "PO-5002", "SGD",
     [("RM-105", "Control board", 50, 38.50)], None, "Error", "Duplicate of INV-1002"),
    ("inv_1006.pdf", 1, "Delta Fasteners", "INV-1006", "PO-9999", "SGD",
     [("RM-104", "Fastener kit", 50, 6.20)], None, "Error", "PO not in records"),
    ("inv_1007.pdf", 1, "Cedar Plastics", "INV-1007", "PO-5005", "SGD",
     [("RM-102", "Plastic housing", 60, 14.80), ("RM-107", "Gasket set", 40, 12.00)],
     1638.00, "Error", "Stated total does not match lines"),
    ("inv_1008.pdf", 1, "Delta Fasteners", "INV-1008", "PO-5006", "SGD",
     [("RM-104", "Fastener kit", 200, 6.23)], None, "OK", "Price 0.5% off: inside tolerance, should NOT be flagged"),
    ("inv_1009.pdf", 1, "Alpha Steel Pte Ltd", "INV-1009", "PO-5007", "SGD",
     [("RM-101", "Steel sheet 2mm", 50, 45.00), ("RM-103", "Copper wire (m)", 20, 2.40)],
     None, "Error", "Item not on the PO"),
    ("inv_1010.pdf", 2, "Evergreen Wiring", "INV-1010", "PO-5008", "USD",
     [("RM-103", "Copper wire (m)", 500, 2.40)], None, "Error", "Currency USD, PO is SGD"),
    ("inv_1011.pdf", 2, "Evergreen Wiring", "INV-1011", "PO-5009", "SGD",
     [("RM-103", "Copper wire (m)", 300, 2.40)], None, "Error", "Billed but no goods received"),
    ("inv_1012.pdf", 2, "Brightline Electronics", "INV-1012", "PO-5010", "SGD",
     [("RM-106", "Motor 24V", 40, 52.00)], None, "OK", "Clean (layout 2)"),
]


def money(x):
    return f"{x:,.2f}"


def draw_invoice(path, layout, supplier, inv_no, po_no, currency, lines, stated_total, inv_date):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, supplier)  # supplier is always the first line
    y -= 26
    c.setFont("Helvetica", 10)
    if layout == 1:
        header = [f"Invoice No: {inv_no}", f"Date: {inv_date}",
                  f"Purchase Order No: {po_no}", f"Currency: {currency}"]
    else:
        header = ["TAX INVOICE", f"Inv # {inv_no}", f"Invoice Date: {inv_date}",
                  f"Your ref: Purchase Order {po_no}", f"All amounts in {currency}"]
    for t in header:
        c.drawString(50, y, t)
        y -= 15
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    for x, t in zip([50, 130, 330, 400, 480], ["Item", "Description", "Qty", "Unit price", "Amount"]):
        c.drawString(x, y, t)
    y -= 16
    c.setFont("Helvetica", 10)
    total = 0.0
    for code, desc, qty, price in lines:
        amount = round(qty * price, 2)
        total += amount
        for x, t in zip([50, 130, 330, 400, 480], [code, desc, str(qty), money(price), money(amount)]):
            c.drawString(x, y, t)
        y -= 15
    y -= 10
    shown = stated_total if stated_total is not None else total
    c.setFont("Helvetica-Bold", 11)
    label = "TOTAL DUE" if layout == 1 else "Amount Payable"
    c.drawString(400, y, f"{label} {money(shown)}")
    c.save()


def build_invoices():
    INV_DIR.mkdir(parents=True, exist_ok=True)
    for old in INV_DIR.glob("*.pdf"):
        old.unlink()
    key = []
    base = date.today() - timedelta(days=20)
    for i, (fname, layout, sup, no, po, cur, lines, stated, expected, note) in enumerate(INVOICES):
        draw_invoice(INV_DIR / fname, layout, sup, no, po, cur, lines, stated,
                     (base + timedelta(days=i)).isoformat())
        key.append({"file": fname, "expected": expected, "planted_issue": note})
    pd.DataFrame(key).to_csv(DATA / "invoice_answer_key.csv", index=False)


# --------------------------------------------------------------------------
# 6c: planning data
# --------------------------------------------------------------------------
def build_planning():
    today = date.today()
    d = lambda n: (today + timedelta(days=n)).isoformat()

    pd.DataFrame([
        ("FG-100", "Control Box"), ("FG-200", "Pump Unit"),
        ("SA-10", "Wiring Assembly"), ("SA-20", "Motor Assembly"),
        ("RM-101", "Steel sheet 2mm"), ("RM-102", "Plastic housing"),
        ("RM-103", "Copper wire (m)"), ("RM-104", "Fastener kit"),
        ("RM-105", "Control board"), ("RM-106", "Motor 24V"), ("RM-107", "Gasket set"),
    ], columns=["item_code", "description"]).to_csv(DATA / "items.csv", index=False)

    # Multi-level BOM: finished good -> sub-assembly -> raw material
    pd.DataFrame([
        ("FG-100", "SA-10", 1), ("FG-100", "RM-102", 1), ("FG-100", "RM-104", 1),
        ("FG-200", "SA-20", 1), ("FG-200", "RM-101", 2), ("FG-200", "RM-107", 1), ("FG-200", "RM-104", 2),
        ("SA-10", "RM-103", 3), ("SA-10", "RM-105", 1),
        ("SA-20", "RM-106", 1), ("SA-20", "RM-101", 1), ("SA-20", "RM-103", 2),
    ], columns=["parent", "component", "qty_per"]).to_csv(DATA / "bom.csv", index=False)

    pd.DataFrame([
        ("RM-101", 60), ("RM-102", 80), ("RM-103", 300), ("RM-104", 200),
        ("RM-105", 40), ("RM-106", 30), ("RM-107", 50),
    ], columns=["item_code", "on_hand"]).to_csv(DATA / "inventory.csv", index=False)

    pd.DataFrame([
        ("SO-2001", "Apex Water", "Key", "FG-200", 20, d(7)),
        ("SO-2002", "Nova Controls", "Key", "FG-100", 30, d(10)),
        ("SO-2003", "Harbor Utilities", "Standard", "FG-200", 25, d(12)),
        ("SO-2004", "Zenith Mfg", "Standard", "FG-100", 40, d(14)),
        ("SO-2005", "Apex Water", "Key", "FG-100", 20, d(18)),
        ("SO-2006", "Kestrel Systems", "Standard", "FG-200", 15, d(21)),
    ], columns=["order_id", "customer", "customer_type", "product", "qty", "due_date"]
    ).to_csv(DATA / "sales_orders.csv", index=False)

    pd.DataFrame([
        ("PO-6001", "RM-101", 100, d(9)),
        ("PO-6002", "RM-106", 40, d(16)),
        ("PO-6003", "RM-105", 50, d(15)),
    ], columns=["po_no", "item_code", "qty", "eta"]).to_csv(DATA / "open_purchase_orders.csv", index=False)

    pd.DataFrame([
        ("RM-101", 14), ("RM-102", 10), ("RM-103", 7), ("RM-104", 5),
        ("RM-105", 21), ("RM-106", 18), ("RM-107", 7),
    ], columns=["item_code", "lead_time_days"]).to_csv(DATA / "lead_times.csv", index=False)


def main():
    DATA.mkdir(exist_ok=True)
    pd.DataFrame(PO_LINES, columns=PO_COLS).to_csv(DATA / "purchase_orders.csv", index=False)
    pd.DataFrame(GRN_ROWS, columns=["po_no", "item_code", "qty_received"]).to_csv(
        DATA / "goods_received.csv", index=False)
    build_invoices()
    build_planning()
    print("Mock data written to", DATA)


if __name__ == "__main__":
    main()
