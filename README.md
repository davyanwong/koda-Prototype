# Koda AI Assistant: prototype

Two tools in one web app, built from the framework:
- **6b Invoice checker**: reads invoice PDFs, compares with PO and goods received, flags differences, a person approves or rejects.
- **6c Production planner**: explodes the multi-level BOM, checks stock and incoming POs per order due date, suggests a priority list with reasons.

Code does the maths and matching. AI is optional and only reads messy invoices or explains results.
The app never writes to the ERP; it exports CSV files.

## Run it
1. Install Python 3.10+.
2. In this folder:  `pip install -r requirements.txt`
3. Start:           `streamlit run app.py`
4. A browser tab opens. Go to **6b**, press "Check the 12 sample invoices". Then open **6c**.

Mock data is created automatically in `data/` on first run (or run `python make_mock_data.py`).

## Files
| File | What it does |
|---|---|
| app.py | The screens |
| logic.py | Invoice reading rules, matching rules, BOM and shortage calculation |
| ai.py | Optional Claude calls (invoice reading, plan summary) |
| make_mock_data.py | Makes fake POs, goods received, 12 invoice PDFs (8 with planted errors), planning CSVs |
| data/ | The CSVs and PDFs the app reads |

## Switching to Koda's real data
Replace the CSVs in `data/` with Koda's exports, keeping the same column names (see make_mock_data.py).
Change `load_csv` in app.py if Koda gives Excel files or an API.

## Optional AI
Set an `ANTHROPIC_API_KEY` environment variable, then turn on the sidebar switch.
Use fake or anonymised data only until Koda says cloud AI is allowed.

## Not in the prototype yet
- Scanned invoices (needs OCR or AI vision)
- Real supplier layouts (rule-based reading only knows the two mock layouts; AI reading handles more)
- Machine capacity and labour limits in planning
