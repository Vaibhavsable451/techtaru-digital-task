"""Streamlit frontend.  Run:  streamlit run streamlit_app.py"""
import html
import json
import time

import pandas as pd
import streamlit as st
from groq import Groq

from app import config
from app.extractor import ExtractionError, extract
from app.schemas import DocType

st.set_page_config(page_title="Data Extraction Bot", page_icon="🧾", layout="wide")

SAMPLES = {
    "resume": (
        "Priya Sharma\npriya.sharma@example.com | +91 98765 43210 | Pune, India\n"
        "Python developer with 3 years of experience building APIs.\n"
        "Skills: Python, FastAPI, SQL, Docker, Pydantic\n"
        "Experience:\nBackend Developer, Infosys (Jun 2022 - Present) - built REST services.\n"
        "Intern, TCS (Jan 2022 - May 2022) - data pipelines.\n"
        "Education: B.E. Computer Engineering, Savitribai Phule Pune University, 2022\n"
        "Certifications: AWS Cloud Practitioner"
    ),
    "invoice": (
        "INVOICE #INV-2026-044\nVendor: Sai Traders\nBill to: Acme Pvt Ltd\n"
        "Date: 2026-10-01   Due: 2026-10-15\n"
        "2 x Laptop stand @ 1500 = 3000\n1 x USB hub @ 800 = 800\n"
        "Subtotal: INR 3800\nGST 18%: 684\nTotal: INR 4484"
    ),
}

# ------------------------------------------------------------------ styling
st.markdown(
    """
<style>
#MainMenu, footer, header {visibility:hidden;}
.block-container {padding-top:1.6rem; max-width:1200px;}
.hero {
  padding:28px 32px; border-radius:20px; margin-bottom:22px;
  background:radial-gradient(circle at 15% 20%, rgba(139,124,255,.35), transparent 55%),
             radial-gradient(circle at 90% 80%, rgba(45,212,191,.22), transparent 50%),
             #11142080;
  border:1px solid rgba(255,255,255,.08);
}
.hero h1 {margin:0; font-size:2.1rem; letter-spacing:-.02em;}
.hero p {margin:6px 0 0; color:#a7acc4;}
.pill {display:inline-block; padding:3px 11px; margin:0 6px 0 0; border-radius:999px; font-size:.75rem;
       border:1px solid rgba(255,255,255,.14); color:#c9cde0; background:rgba(255,255,255,.04);}
.pill.ok {border-color:#2dd4bf66; color:#5eead4;} .pill.bad {border-color:#fb718566; color:#fda4af;}
.card {padding:16px 18px; border-radius:16px; background:#141826; border:1px solid rgba(255,255,255,.07);}
.stat {text-align:left;}
.stat .label {font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; color:#8a90ab;}
.stat .value {font-size:1.55rem; font-weight:650; margin-top:2px;}
.chip {display:inline-block; padding:4px 12px; margin:3px 5px 3px 0; border-radius:999px; font-size:.82rem;
       background:rgba(139,124,255,.16); border:1px solid rgba(139,124,255,.4); color:#d6d1ff;}
.person {font-size:1.5rem; font-weight:650;} .muted {color:#8a90ab; font-size:.9rem;}
div.stButton > button {border-radius:12px; font-weight:600;}
div.stButton > button[kind="primary"] {background:linear-gradient(135deg,#8b7cff,#5b8cff); border:0;}
</style>
""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ helpers
def mask_key(key: str | None) -> str:
    """Never show a full secret: gsk_••••••••abcd"""
    if not key:
        return "not set"
    return f"{key[:4]}{'•' * 8}{key[-4:]}" if len(key) > 10 else "•" * len(key)


def stat(label: str, value) -> str:
    return (f'<div class="card stat"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{html.escape(str(value))}</div></div>')


def load_sample():
    st.session_state["text_input"] = SAMPLES[st.session_state["doc_type"]]


def render_resume(d: dict):
    contact = " · ".join(x for x in (d.get("email"), d.get("phone"), d.get("location")) if x)
    st.markdown(
        f'<div class="card"><div class="person">{html.escape(d.get("full_name") or "Unknown name")}</div>'
        f'<div class="muted">{html.escape(contact)}</div>'
        f'<div style="margin-top:8px">{html.escape(d.get("summary") or "")}</div></div>',
        unsafe_allow_html=True,
    )
    c = st.columns(3)
    c[0].markdown(stat("Skills", len(d["skills"])), unsafe_allow_html=True)
    c[1].markdown(stat("Jobs", len(d["experience"])), unsafe_allow_html=True)
    c[2].markdown(stat("Education", len(d["education"])), unsafe_allow_html=True)
    if d["skills"]:
        st.markdown("##### Skills")
        st.markdown("".join(f'<span class="chip">{html.escape(s)}</span>' for s in d["skills"]),
                    unsafe_allow_html=True)
    if d["experience"]:
        st.markdown("##### Experience")
        st.dataframe(pd.DataFrame(d["experience"]), width="stretch", hide_index=True)
    if d["education"]:
        st.markdown("##### Education")
        st.dataframe(pd.DataFrame(d["education"]), width="stretch", hide_index=True)
    if d["certifications"]:
        st.markdown("##### Certifications")
        st.markdown("".join(f'<span class="chip">{html.escape(s)}</span>' for s in d["certifications"]),
                    unsafe_allow_html=True)


def render_invoice(d: dict):
    c = st.columns(4)
    total = f'{d.get("currency") or ""} {d["total"]:,.2f}'.strip() if d.get("total") is not None else "n/a"
    c[0].markdown(stat("Total", total), unsafe_allow_html=True)
    c[1].markdown(stat("Invoice #", d.get("invoice_number") or "n/a"), unsafe_allow_html=True)
    c[2].markdown(stat("Issued", d.get("invoice_date") or "n/a"), unsafe_allow_html=True)
    c[3].markdown(stat("Due", d.get("due_date") or "n/a"), unsafe_allow_html=True)
    st.markdown(
        f'<div class="card" style="margin-top:12px"><span class="muted">From</span> '
        f'<b>{html.escape(d.get("vendor_name") or "n/a")}</b> &nbsp;→&nbsp; '
        f'<span class="muted">Bill to</span> <b>{html.escape(d.get("customer_name") or "n/a")}</b></div>',
        unsafe_allow_html=True,
    )
    if d["line_items"]:
        st.markdown("##### Line items")
        st.dataframe(pd.DataFrame(d["line_items"]), width="stretch", hide_index=True)
    c = st.columns(3)
    c[0].markdown(stat("Subtotal", d.get("subtotal", "n/a")), unsafe_allow_html=True)
    c[1].markdown(stat("Tax", d.get("tax", "n/a")), unsafe_allow_html=True)
    c[2].markdown(stat("Total", d.get("total", "n/a")), unsafe_allow_html=True)


# ------------------------------------------------------------------ sidebar: API key
with st.sidebar:
    st.markdown("### 🔑 Groq API key")
    pasted = st.text_input("Paste key (this session only)", type="password", placeholder="gsk_...",
                           help="Overrides GROQ_API_KEY from .env. Never stored on disk.")
    active_key = pasted.strip() or config.GROQ_API_KEY
    source = "pasted" if pasted.strip() else (".env" if config.GROQ_API_KEY else "none")
    st.markdown(
        f'<span class="pill {"ok" if active_key else "bad"}">{"● connected" if active_key else "● no key"}</span>'
        f'<span class="pill">source: {source}</span>',
        unsafe_allow_html=True,
    )
    st.caption(f"Key in use: `{mask_key(active_key)}`")
    if st.button("Test key", width="stretch", key="test_key"):
        if not active_key:
            st.error("No key. Get a free one at console.groq.com/keys")
        else:
            try:
                Groq(api_key=active_key).models.list()
                st.success("Key works ✅")
            except Exception as e:  # any failure = key/network problem
                st.error(f"Key check failed: {type(e).__name__}")
    st.divider()
    st.markdown("### 🤖 Model")
    st.code(config.GROQ_MODEL, language=None)
    st.caption("Set `GROQ_MODEL` in `.env`. Restart after editing.")
    st.markdown("[Get a free Groq key ↗](https://console.groq.com/keys)")

# ------------------------------------------------------------------ main
st.markdown(
    f"""<div class="hero"><h1>🧾 Data Extraction Bot</h1>
<p>Turn messy resumes and invoices into clean, validated JSON.</p>
<div style="margin-top:14px"><span class="pill">Groq</span><span class="pill">{html.escape(config.GROQ_MODEL)}</span>
<span class="pill">Pydantic validated</span><span class="pill">FastAPI backend</span></div></div>""",
    unsafe_allow_html=True,
)

left, right = st.columns([1, 1], gap="large")

with left:
    st.radio("Document type", [d.value for d in DocType], key="doc_type", horizontal=True,
             format_func=str.capitalize)
    upload = st.file_uploader("Or upload a .txt file", type=["txt"])
    if upload is not None and st.session_state.get("_last_upload") != upload.file_id:
        st.session_state["text_input"] = upload.getvalue().decode("utf-8", errors="ignore")
        st.session_state["_last_upload"] = upload.file_id
    st.text_area("Unstructured text", key="text_input", height=300,
                 placeholder="Paste a resume or invoice here...")
    b1, b2 = st.columns([2, 1])
    run = b1.button("✨ Extract", type="primary", width="stretch", key="extract_btn")
    b2.button("Load sample", on_click=load_sample, width="stretch", key="sample_btn")

with right:
    st.markdown("#### Result")
    if run:
        try:
            if not active_key:
                st.error("No Groq API key. Paste one in the sidebar or set GROQ_API_KEY in .env.")
            else:
                t0 = time.perf_counter()
                with st.spinner("Extracting..."):
                    data, warnings = extract(
                        st.session_state.get("text_input", ""),
                        DocType(st.session_state["doc_type"]),
                        client=Groq(api_key=active_key),
                    )
                st.session_state["result"] = {
                    "type": st.session_state["doc_type"], "data": data, "warnings": warnings,
                    "secs": time.perf_counter() - t0,
                }
        except ExtractionError as e:
            st.session_state.pop("result", None)
            st.error(str(e))

    res = st.session_state.get("result")
    if res:
        st.caption(f"✅ Done in {res['secs']:.1f}s · model `{config.GROQ_MODEL}`")
        for w in res["warnings"]:
            st.warning(w)
        tab_view, tab_json = st.tabs(["Formatted", "JSON"])
        with tab_view:
            (render_resume if res["type"] == "resume" else render_invoice)(res["data"])
        with tab_json:
            payload = json.dumps(res["data"], indent=2, ensure_ascii=False)
            st.code(payload, language="json")
            st.download_button("⬇ Download JSON", payload, file_name=f"{res['type']}.json",
                               mime="application/json", width="stretch")
    elif not run:
        st.markdown('<div class="card muted">Your structured result will appear here. '
                    'Try <b>Load sample</b> then <b>Extract</b>.</div>', unsafe_allow_html=True)
