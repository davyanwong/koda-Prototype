"""
Optional AI layer. The prototype works without it.

Set ANTHROPIC_API_KEY (environment variable or .streamlit/secrets.toml) to switch it on.
Only use it with FAKE or ANONYMISED data until Koda confirms cloud AI is allowed (Q9).
"""
import json
import os

MODEL = os.environ.get("KODA_MODEL", "claude-sonnet-5-5")


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            key = None
    if not key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=key)


def ai_available() -> bool:
    return _client() is not None


def extract_invoice_with_ai(text: str):
    """Ask Claude to read messy invoice text and return the same fields the rule-based parser gives.
    Returns a dict, or None if AI is unavailable or the answer cannot be read."""
    client = _client()
    if client is None:
        return None
    prompt = (
        "Extract these fields from the invoice text. Reply with JSON only, no other words.\n"
        '{"supplier": str, "invoice_no": str, "date": "YYYY-MM-DD", "po_no": str, "currency": "3-letter code", '
        '"total": number, "lines": [{"item_code": str, "description": str, "qty": number, '
        '"unit_price": number, "amount": number}]}\n'
        "Copy numbers exactly as printed. Use an empty string if a field is missing. Do not guess.\n\n"
        f"INVOICE TEXT:\n{text}"
    )
    try:
        msg = client.messages.create(model=MODEL, max_tokens=1500,
                                     messages=[{"role": "user", "content": prompt}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        data.setdefault("lines", [])
        return data
    except Exception:
        return None


def explain_plan_with_ai(orders_text: str):
    """Plain-language summary for planners. Numbers come from the code, the AI only explains them."""
    client = _client()
    if client is None:
        return None
    prompt = (
        "You help a production planner. Below is a plan already calculated by code. "
        "Do not change any numbers. In plain language (under 120 words), say which orders to "
        "start first, which are at risk and why, and the one action that matters most.\n\n" + orders_text
    )
    try:
        msg = client.messages.create(model=MODEL, max_tokens=500,
                                     messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception:
        return None
