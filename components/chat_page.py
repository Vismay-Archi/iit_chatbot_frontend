import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# ── Constants ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
FEEDBACK_FILE = BASE_DIR / "feedback_log.jsonl"
MODEL_A_ENDPOINT = os.getenv("MODEL_A_ENDPOINT", "").strip()
MODEL_B_ENDPOINT = os.getenv("MODEL_B_ENDPOINT", "").strip()
ENABLE_FEEDBACK = False

EXECUTOR = ThreadPoolExecutor(max_workers=4)

# ── Helpers ───────────────────────────────────────────────────────
def get_logo_b64():
    for p in [BASE_DIR / "assets" / "logo.jpg", BASE_DIR / "assets" / "logo.png"]:
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode()
    return ""


def bot_avatar(logo_b64):
    if logo_b64:
        return f'<img src="data:image/jpeg;base64,{logo_b64}" class="av-img" alt="IIT"/>'
    return '<div class="av-fallback">IIT</div>'


def render_messages(messages, logo_b64):
    out = ""
    for msg in messages:
        text = (
            msg["content"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        extra = (
            ' style="border-left:3px solid #CC0000;background:#fff5f5;"'
            if msg.get("is_error") else ""
        )

        if msg["role"] == "assistant":
            html_block = f"""
<div class="msg-row">
  {bot_avatar(logo_b64)}
  <div class="bubble bot-bub"{extra}>{text}</div>
</div>
"""
        else:
            html_block = f"""
<div class="msg-row user-msg-row">
  <div class="bubble user-bub">{text}</div>
  <div class="av-user">You</div>
</div>
"""
        out += html_block
    return out


def ensure_message_ids(messages):
    assistant_id = 0
    for i, msg in enumerate(messages):
        msg.setdefault("msg_id", i)
        msg.setdefault("sources", [])
        if msg["role"] == "assistant":
            msg.setdefault("message_id", assistant_id)
            assistant_id += 1


def ensure_async_state():
    for p in ["A", "B"]:
        st.session_state.setdefault(f"future_{p}", None)
        st.session_state.setdefault(f"inp_reset_{p}", 0)
        st.session_state.setdefault(f"response_ready_{p}", False)


# ── Backend worker ────────────────────────────────────────────────
def backend_worker(panel_id, user_input, topic, session_id, history):
    try:
        if panel_id == "A":
            payload = {
                "question": user_input,
                "method": "traffic_cop",
                "session_id": session_id,
            }
            endpoint = MODEL_A_ENDPOINT
        else:
            chat_history = [
                {"role": m["role"], "content": m["content"]}
                for m in history if m.get("role") in ("user", "assistant")
            ]
            payload = {
                "prompt": user_input,
                "topic": topic or "",
                "chat_history": chat_history,
                "pending_context": None,
            }
            endpoint = MODEL_B_ENDPOINT

        r = requests.post(endpoint, json=payload, timeout=(10, 120))
        r.raise_for_status()
        data = r.json()

        answer = (
            data.get("answer")
            or data.get("response")
            or data.get("content")
            or data.get("text")
            or ""
        )

        sources = data.get("source_urls") or data.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]

        return {
            "answer": answer.strip() or "No response returned.",
            "sources": sources,
            "session_id": data.get("session_id", session_id),
            "is_error": False,
        }

    except Exception as e:
        return {
            "answer": f"Backend unavailable: {e}",
            "sources": [],
            "session_id": session_id,
            "is_error": True,
        }


# ── Submit ────────────────────────────────────────────────────────
def submit_request(panel_id, user_input, topic):
    future_key = f"future_{panel_id}"
    msg_key = f"messages_{panel_id.lower()}"
    session_key = f"session_id_{panel_id.lower()}"

    current = st.session_state.get(future_key)
    if current and not current.done():
        return

    history = list(st.session_state.get(msg_key, []))
    session_id = st.session_state.get(session_key, "")

    future = EXECUTOR.submit(
        backend_worker, panel_id, user_input, topic, session_id, history
    )

    st.session_state[future_key] = future


# ── Harvest ───────────────────────────────────────────────────────
def harvest_completed_responses():
    for p in ["A", "B"]:
        future = st.session_state.get(f"future_{p}")
        if future is None or not future.done():
            continue

        result = future.result()

        msg_key = f"messages_{p.lower()}"
        session_key = f"session_id_{p.lower()}"

        messages = st.session_state.get(msg_key, [])
        assistant_count = sum(1 for m in messages if m["role"] == "assistant")

        messages.append({
            "role": "assistant",
            "content": result["answer"],
            "sources": result["sources"],
            "message_id": assistant_count,
            "is_error": result["is_error"],
        })

        st.session_state[msg_key] = messages
        st.session_state[session_key] = result["session_id"]
        st.session_state[f"future_{p}"] = None
        st.session_state[f"inp_reset_{p}"] += 1

        st.session_state[f"response_ready_{p}"] = True


# ── Panel ─────────────────────────────────────────────────────────
def render_panel(panel_id, logo_b64):
    msg_key = f"messages_{panel_id.lower()}"
    topic = st.session_state.get("topic", "Academic Calendar")

    messages = st.session_state.get(msg_key, [])
    future = st.session_state.get(f"future_{panel_id}")
    is_pending = future is not None and not future.done()

    ensure_message_ids(messages)
    st.session_state[msg_key] = messages

    thinking_html = ""
    if is_pending:
        thinking_html = f"""
<div class="msg-row">
  {bot_avatar(logo_b64)}
  <div class="bubble bot-bub thinking-bub">
    <span class="dot-pulse"></span>
    <span class="dot-pulse" style="animation-delay:.2s"></span>
    <span class="dot-pulse" style="animation-delay:.4s"></span>
  </div>
</div>
"""

    msgs_html = render_messages(messages, logo_b64)
    thinking_tag = "<span class='thinking-tag'>thinking...</span>" if is_pending else ""

    html = f"""
<div class="panel-wrap">
  <div class="panel-head">
    Chatbot {panel_id}
    <span class="model-tag">Model {panel_id}</span>
    {thinking_tag}
  </div>
  <div class="msgs-area" id="msgs-{panel_id}">
    {msgs_html}
    {thinking_html}
  </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

    reset = st.session_state.get(f"inp_reset_{panel_id}", 0)
    key = f"inp_{panel_id}_{reset}"

    user_input = st.text_input(
        label="msg",
        key=key,
        placeholder="Ask me anything related to IIT...",
        label_visibility="collapsed",
        disabled=is_pending,
    )

    col, _ = st.columns([1, 3])
    with col:
        send_clicked = st.button("Send >", key=f"send_{panel_id}", disabled=is_pending)

    if send_clicked and user_input.strip() and not is_pending:
        messages.append({"role": "user", "content": user_input.strip()})
        st.session_state[msg_key] = messages

        submit_request(panel_id, user_input.strip(), topic)

        st.session_state[f"inp_reset_{panel_id}"] += 1
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────
def render_chat_page():
    ensure_async_state()
    harvest_completed_responses()

    logo = get_logo_b64()

    col1, col2 = st.columns(2)
    with col1:
        render_panel("A", logo)
    with col2:
        render_panel("B", logo)

    rerun_needed = False
    for p in ["A", "B"]:
        if st.session_state.get(f"response_ready_{p}"):
            st.session_state[f"response_ready_{p}"] = False
            rerun_needed = True

    if rerun_needed:
        st.rerun()
