import base64
import json
import os
import time
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

# ── Async State ───────────────────────────────────────────────────
def ensure_async_state():
    for panel_id in ["A", "B"]:
        st.session_state.setdefault(f"future_{panel_id}", None)
        st.session_state.setdefault(f"inp_reset_{panel_id}", 0)

# ── Backend Worker ────────────────────────────────────────────────
def backend_worker(panel_id, user_input, topic, history, session_id):
    try:
        if panel_id == "A":
            endpoint = MODEL_A_ENDPOINT
            payload = {
                "question": user_input,
                "method": "traffic_cop",
                "session_id": session_id,
            }
        else:
            endpoint = MODEL_B_ENDPOINT
            chat_history = [
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m["role"] in ("user", "assistant")
            ]
            payload = {
                "prompt": user_input,
                "topic": topic,
                "chat_history": chat_history,
                "pending_context": None,
            }

        if not endpoint:
            raise ValueError(f"No endpoint for panel {panel_id}")

        r = requests.post(endpoint, json=payload, timeout=(10, 60))
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

        return {
            "answer": answer.strip() or "No response returned.",
            "sources": sources if isinstance(sources, list) else [sources],
            "session_id": data.get("session_id", session_id),
            "is_error": False,
        }

    except Exception as e:
        return {
            "answer": f"Error: {e}",
            "sources": [],
            "session_id": session_id,
            "is_error": True,
        }

# ── Submit Request ────────────────────────────────────────────────
def submit_request(panel_id, user_input, topic):
    future_key = f"future_{panel_id}"
    msg_key = f"messages_{panel_id.lower()}"
    session_key = f"session_id_{panel_id.lower()}"

    future = st.session_state.get(future_key)

    if future and not future.done():
        st.warning(f"Model {panel_id} is still responding...")
        return

    history = list(st.session_state.get(msg_key, []))
    session_id = st.session_state.get(session_key)

    future = EXECUTOR.submit(
        backend_worker,
        panel_id,
        user_input,
        topic,
        history,
        session_id
    )

    st.session_state[future_key] = future

# ── Harvest Responses ─────────────────────────────────────────────
def harvest_responses():
    for panel_id in ["A", "B"]:
        future_key = f"future_{panel_id}"
        msg_key = f"messages_{panel_id.lower()}"
        session_key = f"session_id_{panel_id.lower()}"

        future = st.session_state.get(future_key)
        if not future or not future.done():
            continue

        result = future.result()

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
        st.session_state[future_key] = None

        st.session_state[f"inp_reset_{panel_id}"] += 1

# ── UI Helpers ────────────────────────────────────────────────────
def get_logo_b64():
    p = Path("assets/logo.jpg")
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

def bot_avatar(b64):
    return f'<img src="data:image/jpeg;base64,{b64}" class="av-img"/>' if b64 else "IIT"

def render_messages(messages, logo):
    out = ""
    for m in messages:
        text = m["content"].replace("\n", "<br>")
        if m["role"] == "assistant":
            out += f"<div>{bot_avatar(logo)} {text}</div>"
        else:
            out += f"<div><b>You:</b> {text}</div>"
    return out

# ── Panel ─────────────────────────────────────────────────────────
def render_panel(panel_id, logo):
    msg_key = f"messages_{panel_id.lower()}"
    topic = st.session_state.get("topic", "Academic Calendar")

    messages = st.session_state.get(msg_key, [])
    future = st.session_state.get(f"future_{panel_id}")
    is_pending = future and not future.done()

    st.markdown(render_messages(messages, logo), unsafe_allow_html=True)

    if is_pending:
        st.write("⏳ thinking...")

    reset = st.session_state.get(f"inp_reset_{panel_id}", 0)
    inp_key = f"inp_{panel_id}_{reset}"

    user_input = st.text_input("", key=inp_key)

    if st.button(f"Send {panel_id}"):
        if user_input.strip():
            messages.append({"role": "user", "content": user_input})
            st.session_state[msg_key] = messages

            submit_request(panel_id, user_input, topic)

            st.session_state[f"inp_reset_{panel_id}"] += 1
            st.rerun()

# ── Main Page ─────────────────────────────────────────────────────
def render_chat_page():
    ensure_async_state()
    harvest_responses()

    logo = get_logo_b64()

    # ── Header ────────────────────────────────────────────────────
    t1, t2, t3 = st.columns([1, 6, 1])

    with t1:
        if st.button("<"):
            st.session_state.page = "home"
            st.rerun()

    with t2:
        st.markdown("""
        <div>
            <p style="font-size:22px; font-weight:600; margin-bottom:0;">
                IIT Chatbot
            </p>
            <p style="font-size:12px; color:#666; margin-top:2px;">
                Get help with the Academic Calendar, Tuition, Directory, Policies, and the Student Handbook.
            </p>
        </div>
        """, unsafe_allow_html=True)

    with t3:
        theme = st.session_state.get("theme", "light")
        if st.button("Dark" if theme == "light" else "Light"):
            st.session_state.theme = "dark" if theme == "light" else "light"
            st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Panels ────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        render_panel("A", logo)

    with col2:
        render_panel("B", logo)

    # ── Polling loop ──────────────────────────────────────────────
    if any(
        st.session_state.get(f"future_{p}") and not st.session_state[f"future_{p}"].done()
        for p in ["A", "B"]
    ):
        time.sleep(0.5)
        st.rerun()
