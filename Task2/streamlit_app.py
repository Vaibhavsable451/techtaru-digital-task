"""
Streamlit frontend for the AI Agent with Tools.
Run:  streamlit run streamlit_app.py
"""
import os
import time

import streamlit as st

from app.agent import BOT_NAME, MODEL, run_agent_traced

st.set_page_config(page_title=BOT_NAME, page_icon="🤖", layout="wide")

TOOL_BADGES = {
    "get_weather": ("🌦️", "Weather tool", "#38BDF8"),
    "get_stock_price": ("📈", "Stock price tool", "#34D399"),
    "calculate_stock_value": ("🧮", "Stock calculator", "#FBBF24"),
}

EXAMPLES = [
    ("🌦️", "What is the weather in Pune?"),
    ("📈", "What is Apple's stock price?"),
    ("🧮", "How much are 10 Tesla shares worth?"),
    ("💬", "What is Generative AI?"),
    ("👋", "Hello!"),
]

# ----------------------------- Styling ------------------------------------ #
st.markdown(
    """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 2rem; max-width: 1000px;}

.hero {
    padding: 28px 32px; border-radius: 22px; margin-bottom: 18px;
    background: linear-gradient(135deg, #7C5CFF 0%, #4F8CFF 50%, #22D3EE 100%);
    box-shadow: 0 12px 40px rgba(124, 92, 255, .35);
}
.hero h1 {margin: 0; font-size: 2.1rem; color: #fff; font-weight: 800; letter-spacing: -.5px;}
.hero p  {margin: 6px 0 0; color: rgba(255,255,255,.9); font-size: 1.02rem;}

.pill {
    display: inline-block; padding: 4px 12px; margin: 8px 6px 0 0;
    border-radius: 999px; font-size: .78rem; font-weight: 600;
    background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
}
.stat {
    background: #131A2B; border: 1px solid #1F2940; border-radius: 16px;
    padding: 14px 16px; text-align: center;
}
.stat b {display: block; font-size: 1.5rem; color: #fff;}
.stat span {font-size: .78rem; color: #8B97B5; text-transform: uppercase; letter-spacing: .08em;}

[data-testid="stChatMessage"] {
    background: #131A2B; border: 1px solid #1F2940; border-radius: 16px; padding: 14px 16px;
}
section[data-testid="stSidebar"] {background: #0E1424; border-right: 1px solid #1F2940;}
.stButton > button {
    width: 100%; text-align: left; border-radius: 12px; border: 1px solid #26314D;
    background: #131A2B; transition: all .15s ease;
}
.stButton > button:hover {border-color: #7C5CFF; transform: translateX(3px); color: #fff;}
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------- State -------------------------------------- #
if "messages" not in st.session_state:
    st.session_state.messages = []
if "tool_calls" not in st.session_state:
    st.session_state.tool_calls = 0
if "pending" not in st.session_state:
    st.session_state.pending = None


def badge_html(tools):
    html = ""
    for t in tools:
        icon, label, color = TOOL_BADGES.get(t, ("🔧", t, "#A78BFA"))
        html += (f'<span class="pill" style="color:{color};border-color:{color}55;">'
                 f"{icon} {label}</span>")
    return html


# ----------------------------- Sidebar ------------------------------------ #
with st.sidebar:
    st.markdown(f"### 🤖 {BOT_NAME}")
    st.caption("The LLM decides. Python executes.")
    st.divider()

    st.markdown("**✨ Try an example**")
    for icon, text in EXAMPLES:
        if st.button(f"{icon}  {text}", key=f"ex_{text}"):
            st.session_state.pending = text

    st.divider()
    st.markdown("**🧰 Available tools**")
    for icon, label, _ in TOOL_BADGES.values():
        st.markdown(f"- {icon} {label}")

    st.divider()
    if os.getenv("GROQ_API_KEY"):
        st.success("Groq key detected", icon="🔑")
    else:
        st.error("Add GROQ_API_KEY to .env", icon="⚠️")
    st.caption(f"Model: `{MODEL}`")

    if st.button("🗑️  Clear chat"):
        st.session_state.messages = []
        st.session_state.tool_calls = 0
        st.rerun()

# ----------------------------- Header ------------------------------------- #
st.markdown(
    f"""
<div class="hero">
  <h1>🤖 {BOT_NAME}</h1>
  <p>Ask about the weather or stocks. The agent picks the right tool, runs it, and answers.</p>
</div>
""",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3)
user_turns = sum(1 for m in st.session_state.messages if m["role"] == "user")
c1.markdown(f'<div class="stat"><b>{user_turns}</b><span>Questions</span></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="stat"><b>{st.session_state.tool_calls}</b><span>Tools used</span></div>', unsafe_allow_html=True)
c3.markdown(f'<div class="stat"><b>{len(TOOL_BADGES)}</b><span>Tools available</span></div>', unsafe_allow_html=True)
st.write("")

# ----------------------------- Chat history ------------------------------- #
if not st.session_state.messages:
    st.info(f"👋 Hi, I'm {BOT_NAME}! Try an example from the sidebar, or type a question below.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])
        if msg.get("tools"):
            st.markdown(badge_html(msg["tools"]), unsafe_allow_html=True)

# ----------------------------- Input -------------------------------------- #
typed = st.chat_input(f"Ask {BOT_NAME} about weather, stock prices, or anything else...")
question = typed if typed is not None else st.session_state.pending
st.session_state.pending = None

if question is not None:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking and choosing a tool..."):
            start = time.time()
            answer, tools_used = run_agent_traced(question)
            elapsed = time.time() - start
        st.markdown(answer)
        if tools_used:
            st.markdown(badge_html(tools_used), unsafe_allow_html=True)
        st.caption(f"⏱️ {elapsed:.1f}s")

    st.session_state.tool_calls += len(tools_used)
    st.session_state.messages.append({"role": "assistant", "content": answer, "tools": tools_used})
    st.rerun()