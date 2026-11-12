"""
Koda AI assistant prototype (works alongside the ERP, never writes to it).

Run:  streamlit run app.py
Flow: Data in -> extract / calculate -> compare with Koda records -> flag -> human approves -> export
"""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import ai
import logic
import make_mock_data

DATA = Path(__file__).parent / "data"

st.set_page_config(page_title="Koda AI Assistant (prototype)", layout="wide")


# ---------------------------------------------------------------- data loading
def ensure_data(force=False):
    if force or not (DATA / "purchase_orders.csv").exists():
        make_mock_data.main()


@st.cache_data
def load_csv(name, stamp):
    return pd.read_csv(DATA / name)


def stamp():
    f = DATA / "purchase_orders.csv"
    return f.stat().st_mtime if f.exists() else 0


ensure_data()

# ---------------------------------------------------------------- sidebar
st.sidebar.title("Koda prototype")
st.sidebar.caption("AI assistant alongside Koda's ERP. The ERP stays the source of truth. "
                   "Nothing here writes back to it.")

st.sidebar.subheader("Settings")
tol = st.sidebar.slider(
    "Price tolerance (%)", 0.0, 5.0, 1.0, 0.5,
    help="Price differences smaller than this are not flagged. Lower = more flags (fewer missed errors, "
         "more false alarms). Ties to Koda Q10.")

ai_ok = ai.ai_available()
use_ai = st.sidebar.toggle(
    "Use cloud AI to read invoices", value=False, disabled=not ai_ok,
    help="Needs ANTHROPIC_API_KEY. Only use with fake or anonymised data until Koda confirms cloud AI is allowed (Q9).")
if not ai_ok:
    st.sidebar.caption("AI is off: no API key found. The app uses rule-based reading, which is fine for the mock invoices.")
elif use_ai:
    st.sidebar.warning("Invoice text will be sent to a cloud AI service. Use fake data only.")

st.sidebar.subheader("Data")
st.sidebar.caption("Using mock data in the data/ folder. Planning dates are relative to the day the mock data was made.")
if st.sidebar.button("Regenerate mock data (reset dates to today)"):
    make_mock_data.main()
    load_csv.clear()
    for k in ("results", "decisions", "plan_approved"):
        st.session_state.pop(k, None)
    st.rerun()

po_df = load_csv("purchase_orders.csv", stamp())
grn_df = load_csv("goods_received.csv", stamp())

st.title("Koda AI Assistant: prototype")
tab0, tab_b, tab_c = st.tabs(["How it works", "6b  Invoice checker", "6c  Production planner"])

# ---------------------------------------------------------------- how it works
with tab0:
    st.markdown(
        """
**One flow for both tools**

`Data in` → `Read / calculate` → `Compare with Koda's records` → `Flag` → `A person approves` → `Export`

- **Code does the maths and matching.** AI only helps read messy invoices and explain results in plain words.
- **A person approves everything.** The tool exports a file. It never changes the ERP.
- **Mock data for now.** Koda's real exports (CSV/Excel) can replace the files in `data/` later, and the same
  code reads them. The API can come later without changing the screens.

**Try it:** open *6b*, press **Check the 12 sample invoices**, then look at the flagged ones. 
Then open *6c* to see which customer orders are ready and which are at risk.
        """
    )

# ---------------------------------------------------------------- 6b
with tab_b:
    st.subheader("Invoice checker")
    st.caption("Reads invoice PDFs, compares them with the purchase order and goods received, "
               "and highlights differences for a person to approve or reject.")

    c1, c2 = st.columns([2, 1])
    uploads = c1.file_uploader("Upload invoice PDFs (text PDFs)", type="pdf", accept_multiple_files=True)
    run_up = c1.button("Check uploaded invoices", disabled=not uploads)
    run_sample = c2.button("Check the 12 sample invoices", type="primary")

    def process(files):
        """files: list of (name, bytes)"""
        seen, results = set(), []
        for name, data in files:
            text = logic.pdf_text(data)
            inv = None
            if use_ai and ai_ok:
                inv = ai.extract_invoice_with_ai(text)
            if not inv or not inv.get("lines"):
                inv = logic.parse_invoice_text(text)
            issues, table, status = logic.check_invoice(inv, po_df, grn_df, seen, tol)
            results.append({"file": name, "inv": inv, "issues": issues, "table": table,
                            "status": status, "text": text})
        st.session_state["results"] = results
        st.session_state["decisions"] = {}
        st.session_state["from_sample"] = False

    if run_sample:
        files = [(p.name, p.read_bytes()) for p in sorted((DATA / "invoices").glob("*.pdf"))]
        process(files)
        st.session_state["from_sample"] = True
    if run_up:
        process([(u.name, u.getvalue()) for u in uploads])

    results = st.session_state.get("results")
    if not results:
        st.info("Press a button above to start.")
    else:
        decisions = st.session_state.setdefault("decisions", {})
        summary = pd.DataFrame([{
            "File": r["file"], "Invoice": r["inv"].get("invoice_no", ""), "Supplier": r["inv"].get("supplier", ""),
            "Total": r["inv"].get("total", 0), "Status": r["status"], "Flags": len(r["issues"]),
            "Decision": decisions.get(r["file"], {}).get("decision", "Pending"),
        } for r in results])

        m1, m2, m3 = st.columns(3)
        m1.metric("Invoices checked", len(results))
        m2.metric("Passed all checks", int((summary["Status"] == "OK").sum()))
        m3.metric("Need review", int((summary["Status"] == "Review").sum()))

        st.dataframe(
            summary.style.apply(
                lambda r: ["background-color:#ffe0e0" if r["Status"] == "Review" else "" for _ in r], axis=1),
            width="stretch", hide_index=True)

        st.markdown("#### Review one invoice")
        pick = st.selectbox("Invoice", [r["file"] for r in results],
                            format_func=lambda f: f"{f}  ({next(x for x in results if x['file']==f)['status']})")
        r = next(x for x in results if x["file"] == pick)
        left, right = st.columns(2)
        with left:
            st.markdown("**Read from the invoice**")
            st.write({k: v for k, v in r["inv"].items() if k != "lines"})
            with st.expander("Raw text from the PDF"):
                st.text(r["text"])
        with right:
            st.markdown("**Matching Koda records**")
            po_no = r["inv"].get("po_no", "")
            st.dataframe(po_df[po_df["po_no"] == po_no] if po_no else po_df.iloc[0:0],
                         width="stretch", hide_index=True)
            st.dataframe(grn_df[grn_df["po_no"] == po_no] if po_no else grn_df.iloc[0:0],
                         width="stretch", hide_index=True)

        st.markdown("**Line by line**")
        if not r["table"].empty:
            st.dataframe(
                r["table"].style.apply(
                    lambda row: ["background-color:#ffe0e0" if row["Result"] != "OK" else "" for _ in row], axis=1),
                width="stretch", hide_index=True)
        if r["issues"]:
            st.error(f"{len(r['issues'])} thing(s) to check")
            st.dataframe(pd.DataFrame(r["issues"]), width="stretch", hide_index=True)
        else:
            st.success("No differences found.")

        note = st.text_input("Note (optional)", key=f"note_{pick}")
        a, b, _ = st.columns([1, 1, 4])
        if a.button("Approve", key=f"ap_{pick}"):
            decisions[pick] = {"decision": "Approved", "note": note}
            st.rerun()
        if b.button("Reject", key=f"rj_{pick}"):
            decisions[pick] = {"decision": "Rejected", "note": note}
            st.rerun()

        export = summary.copy()
        export["Note"] = [decisions.get(f, {}).get("note", "") for f in export["File"]]
        export["Issues"] = ["; ".join(i["Issue"] for i in x["issues"]) for x in results]
        st.download_button("Download decisions (CSV)", export.to_csv(index=False),
                           "invoice_decisions.csv", "text/csv")

        # ---- scorecard against the planted errors in the mock data
        key_file = DATA / "invoice_answer_key.csv"
        if st.session_state.get("from_sample") and key_file.exists():
            st.markdown("#### Scorecard (mock data only)")
            key = pd.read_csv(key_file).merge(summary[["File", "Status"]], left_on="file", right_on="File")
            bad = key[key["expected"] == "Error"]
            good = key[key["expected"] == "OK"]
            caught = int((bad["Status"] == "Review").sum())
            false_alarms = int((good["Status"] == "Review").sum())
            s1, s2, s3 = st.columns(3)
            s1.metric("Planted errors caught", f"{caught} of {len(bad)}")
            s2.metric("False alarms", f"{false_alarms} of {len(good)} clean invoices")
            s3.metric("Price tolerance", f"{tol}%")
            st.caption("Try moving the tolerance slider to 0 and re-checking: the clean invoice with a 0.5% "
                       "price difference becomes a false alarm. That is the missed-error vs false-alarm trade-off (Q10).")
            key["Result"] = key.apply(
                lambda x: "Correct" if (x["expected"] == "Error") == (x["Status"] == "Review") else "Wrong", axis=1)
            st.dataframe(key[["file", "planted_issue", "Status", "Result"]],
                         width="stretch", hide_index=True)

# ---------------------------------------------------------------- 6c
with tab_c:
    st.subheader("Production and material planner")
    st.caption("Works out the materials each order needs (through the multi-level BOM), compares with stock and "
               "incoming purchase orders, and suggests a production priority. Code does the maths.")

    sales = load_csv("sales_orders.csv", stamp())
    inventory = load_csv("inventory.csv", stamp())
    bom = load_csv("bom.csv", stamp())
    open_pos = load_csv("open_purchase_orders.csv", stamp())
    lead = load_csv("lead_times.csv", stamp())

    with st.expander("Input data (mock exports)"):
        t1, t2, t3, t4, t5 = st.tabs(["Sales orders", "Inventory", "BOM", "Open POs", "Lead times"])
        t1.dataframe(sales, hide_index=True, width="stretch")
        t2.dataframe(inventory, hide_index=True, width="stretch")
        t3.dataframe(bom, hide_index=True, width="stretch")
        t4.dataframe(open_pos, hide_index=True, width="stretch")
        t5.dataframe(lead, hide_index=True, width="stretch")

    orders, mats = logic.build_plan(sales, inventory, bom, open_pos, lead, date.today())
    ready = int((orders["Status"] == "Ready").sum())
    risk = int((orders["Status"] == "At risk").sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Orders", len(orders))
    m2.metric("Ready", ready)
    m3.metric("At risk", risk)

    st.markdown("#### Suggested production priority")
    st.dataframe(
        orders.drop(columns=["Why", "Suggested action"]).style.apply(
            lambda r: ["background-color:#ffe0e0" if r["Status"] == "At risk" else "" for _ in r], axis=1),
        width="stretch", hide_index=True)

    st.markdown("#### Why, and what to do")
    for _, o in orders.iterrows():
        icon = "🟢" if o["Status"] == "Ready" else "🔴"
        with st.expander(f"{icon} {o['Priority']}. {o['Order']}: {o['Customer']} ({o['Product']} x {o['Qty']})",
                         expanded=(o["Status"] == "At risk" and o["Priority"] == ready + 1)):
            st.write(o["Why"])
            st.write("**Suggested action:** " + o["Suggested action"])

    st.markdown("#### Materials across all orders")
    st.dataframe(
        mats.style.apply(lambda r: ["background-color:#fff3cd" if r["Gap"] > 0 else "" for _ in r], axis=1),
        width="stretch", hide_index=True)
    st.caption("A material can look fine in total but still be short on a given due date, because a purchase order "
               "arrives too late. Totals here include at-risk orders, so gaps can look bigger than the order list. "
               "The priority list checks each order against its own due date.")

    st.markdown("#### Plain-language summary")
    if st.button("Explain this plan"):
        text = orders.drop(columns=["Suggested action"]).to_string(index=False)
        out = ai.explain_plan_with_ai(text) if (use_ai and ai_ok) else None
        if out:
            st.write(out)
        else:
            first = orders[orders["Status"] == "Ready"]["Order"].tolist()
            late = orders[orders["Status"] == "At risk"]
            st.write(f"Start with {', '.join(first) if first else 'no order yet'}: materials are available. "
                     f"{len(late)} order(s) are at risk: {', '.join(late['Order'])}. "
                     "The reasons and the suggested fix for each are listed above.")

    approved = st.session_state.get("plan_approved", False)
    if st.button("Planner approves this priority list"):
        st.session_state["plan_approved"] = True
        st.rerun()
    if approved:
        st.success("Approved by planner. Download it below.")
    exp = orders.copy()
    exp["Planner approval"] = "Approved" if approved else "Pending"
    st.download_button("Download plan (CSV)", exp.to_csv(index=False), "production_plan.csv", "text/csv")
