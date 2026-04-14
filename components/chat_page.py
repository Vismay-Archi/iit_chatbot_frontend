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
BASE_DIR         = Path(__file__).resolve().parent.parent
FEEDBACK_FILE    = BASE_DIR / "feedback_log.jsonl"
MODEL_A_ENDPOINT = os.getenv("MODEL_A_ENDPOINT", "").strip()
MODEL_B_ENDPOINT = os.getenv("MODEL_B_ENDPOINT", "").strip()
ENABLE_FEEDBACK  = False

EXECUTOR = ThreadPoolExecutor(max_workers=4)

DISLIKE_REASONS = [
    "Hallucination", "No clarification", "Not helpful",
    "Wrong answer", "Incomplete answer", "Other",
]

# ── Stub fallbacks ────────────────────────────────────────────────
STUBS_A = {
    "Academic Calendar": [
        "Spring 2025 classes begin January 13th and end May 2nd.",
        "Fall registration opens April 1st for continuing students.",
        "Spring Break is March 17–21, 2025.",
        "Final exams for Spring run May 5–9, 2025.",
    ],
    "Tuition": [
        "Graduate tuition for 2024–25 is approximately $1,890 per credit hour.",
        "Full-time undergraduate tuition is around $19,500 per semester.",
        "Payment plans are available through the Bursar's office.",
        "Tuition is due on the first day of each semester.",
    ],
    "Directory": [
        "You can search the IIT directory at web.iit.edu/directory.",
        "Faculty and staff contacts are listed by department on the IIT website.",
        "The Registrar's office can be reached at registrar@iit.edu.",
        "For IT support, contact the Help Desk at 312-567-3375.",
    ],
    "Policies": [
        "IIT's academic integrity policy prohibits plagiarism and unauthorized collaboration.",
        "Students may appeal grades within 30 days of the semester end.",
        "Attendance policies are set by individual instructors per department guidelines.",
        "The add/drop deadline is typically the end of the first week of classes.",
    ],
    "Handbook": [
        "The Student Handbook covers code of conduct, housing, and campus resources.",
        "Students are expected to maintain a GPA of 3.0 for graduate programs.",
        "Campus housing policies are detailed in the Residential Life section.",
        "Grievance procedures are outlined in Chapter 4 of the Student Handbook.",
    ],
}

STUBS_B = {
    "Academic Calendar": [
        "The Spring 2025 semester starts January 13 and finals end May 9.",
        "Summer sessions begin in May — check the Registrar for exact dates.",
        "MLK Day (Jan 20) and Spring Break (Mar 17–21) are university holidays.",
        "Commencement is scheduled for May 11, 2025.",
    ],
    "Tuition": [
        "Undergraduate tuition per credit hour is approximately $1,545 for 2024–25.",
        "International students pay the same tuition rate as domestic students.",
        "Scholarships and financial aid can significantly reduce your tuition bill.",
        "Late payment fees apply after the due date each semester.",
    ],
    "Directory": [
        "Department phone numbers are listed at iit.edu under Contacts.",
        "Academic advisors can be found via the Advising Center directory.",
        "The Dean of Students office is at 312-567-3081.",
        "Library contacts and hours are at library.iit.edu.",
    ],
    "Policies": [
        "Academic dishonesty can result in course failure or expulsion per IIT policy.",
        "Students needing accommodations should contact the Center for Disability Resources.",
        "Incomplete grades must be resolved within one year of the semester.",
        "Transfer credit requires official transcripts and department approval.",
    ],
    "Handbook": [
        "All students must adhere to the IIT Code of Ethics outlined in the Handbook.",
        "The Handbook is updated annually — always refer to the current year's version.",
        "Clubs must be registered with the Student Government Association.",
        "Mental health resources are available free through Counseling Services.",
    ],
}


# ── Helpers ───────────────────────────────────────────────────────
def get_logo_b64() -> str:
    candidates = [
        BASE_DIR / "assets" / "logo.jpg",
        BASE_DIR / "assets" / "logo.png",
    ]
    for p in candidates:
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode()
    return ""


def bot_avatar(logo_b64: str) -> str:
    if logo_b64:
        return f'<img src="data:image/jpeg;base64,{logo_b64}" class="av-img" alt="IIT"/>'
    return '<div class="av-fallback">IIT</div>'


def render_messages(messages: list, logo_b64: str) -> str:
    out = ""
    for msg in messages:
        text = (
            msg["content"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        extra = ' style="border-left:3px solid #CC0000;background:#fff5f5;"' \
            if msg.get("is_error") else ""
        if msg["role"] == "assistant":
            out += f"""
<div class="msg-row">
  {bot_avatar(logo_b64)}
  <div class="bubble bot-bub"{extra}>{text}</div>
</div>"""
        else:
            out += f"""
<div class="msg-row user-msg-row">
  <div class="bubble user-bub">{text}</div>
  <div class="av-user">You</div>
</div>"""
    return out


def stub_reply(panel: str, topic: str) -> str:
    stubs = STUBS_A if panel == "A" else STUBS_B
    replies = stubs.get(topic, ["Please check the IIT website for more details."])
    key = f"stub_idx_{panel}"
    idx = st.session_state.get(key, 0)
    st.session_state[key] = idx + 1
    return replies[idx % len(replies)]


def ensure_message_ids(messages: list):
    assistant_id = 0
    for i, msg in enumerate(messages):
        msg.setdefault("msg_id", i)
        msg.setdefault("show_reason_picker", False)
        msg.setdefault("sources", [])
        if msg["role"] == "assistant":
            msg.setdefault("message_id", assistant_id)
            assistant_id += 1


def append_feedback_to_file(record: dict):
    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_previous_user_message(messages: list, assistant_idx: int) -> str:
    for j in range(assistant_idx - 1, -1, -1):
        if messages[j]["role"] == "user":
            return messages[j]["content"]
    return ""


# ── Async state init ──────────────────────────────────────────────
def ensure_async_state():
    for panel_id in ["A", "B"]:
        st.session_state.setdefault(f"future_{panel_id}", None)
        st.session_state.setdefault(f"inp_reset_{panel_id}", 0)


# ── Backend worker (runs in thread) ──────────────────────────────
def backend_worker(panel_id: str, user_input: str, topic: str,
                   history: list, session_id: str) -> dict:
    try:
        if panel_id == "A":
            endpoint = MODEL_A_ENDPOINT
            payload = {
                "question":   user_input,
                "method":     "traffic_cop",
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
                "prompt":          user_input,
                "topic":           topic or "",
                "chat_history":    chat_history,
                "pending_context": None,
            }

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

        if panel_id == "A":
            sources = (
                data.get("source_urls")
                or data.get("sources")
                or data.get("results", {}).get("traffic_cop", {}).get("source_urls")
                or []
            )
        else:
            sources = data.get("source_urls") or data.get("sources") or []

        if isinstance(sources, str):
            sources = [sources]

        return {
            "answer":     answer.strip() if answer else "No response returned.",
            "sources":    sources,
            "session_id": data.get("session_id", session_id),
            "is_error":   False,
        }

    except Exception as e:
        return {
            "answer":     f"Backend unavailable: {e}",
            "sources":    [],
            "session_id": session_id,
            "is_error":   True,
        }


# ── Submit to thread pool ─────────────────────────────────────────
def submit_request(panel_id: str, user_input: str, topic: str):
    future_key  = f"future_{panel_id}"
    msg_key     = f"messages_{panel_id.lower()}"
    session_key = f"session_id_{panel_id.lower()}"

    future = st.session_state.get(future_key)
    if future and not future.done():
        return

    history    = list(st.session_state.get(msg_key, []))
    session_id = st.session_state.get(session_key)

    st.session_state[future_key] = EXECUTOR.submit(
        backend_worker, panel_id, user_input, topic, history, session_id
    )


# ── Collect completed futures (called once at top of page) ────────
def collect_completed_futures():
    """
    Called ONCE at the top of render_chat_page before any widgets.
    - If a future is done: collect result, save answer, clear future, rerun
    - If futures are still running: do nothing — page renders normally
      with thinking state visible. User interaction or the next natural
      rerun will trigger this again to collect the result.
    """
    collected = False

    for panel_id in ["A", "B"]:
        future = st.session_state.get(f"future_{panel_id}")
        if future is None:
            continue
        if not future.done():
            continue

        # Future is done — collect result
        result   = future.result()
        msg_key  = f"messages_{panel_id.lower()}"
        messages = st.session_state.get(msg_key, [])

        assistant_count = sum(1 for m in messages if m["role"] == "assistant")
        messages.append({
            "role":       "assistant",
            "content":    result["answer"],
            "sources":    result["sources"],
            "message_id": assistant_count,
            "is_error":   result["is_error"],
        })

        st.session_state[msg_key]                           = messages
        st.session_state[f"session_id_{panel_id.lower()}"]  = result["session_id"]
        st.session_state[f"future_{panel_id}"]              = None
        st.session_state[f"inp_reset_{panel_id}"]          += 1
        collected = True

    if collected:
        st.rerun()


# ── Sources block ─────────────────────────────────────────────────
def render_sources_block(sources: list, panel_id: str, message_id: int):
    if not sources:
        return
    with st.expander("Sources", expanded=False):
        for i, src in enumerate(sources, start=1):
            if isinstance(src, dict):
                url   = src.get("url") or src.get("href") or ""
                title = src.get("title") or src.get("label") or url or f"Source {i}"
            else:
                url   = str(src).strip()
                title = url
            st.markdown(f"- [{title}]({url})" if url else f"- Source {i}")


# ── Feedback helpers ──────────────────────────────────────────────
if ENABLE_FEEDBACK:
    def save_final_feedback(panel_id: str, message_id: int,
                            reason: str = None, comment: str = ""):
        msg_key  = f"messages_{panel_id.lower()}"
        messages = st.session_state.get(msg_key, [])
        for idx, msg in enumerate(messages):
            if msg.get("message_id") == message_id:
                if msg.get("feedback_saved"):
                    return
                record = {
                    "panel_id":      panel_id,
                    "message_id":    message_id,
                    "question":      get_previous_user_message(messages, idx),
                    "answer":        msg.get("content", ""),
                    "score":         (msg.get("feedback") or {}).get("score", "unknown"),
                    "feedback_text": (msg.get("feedback") or {}).get("text", ""),
                    "reason":        reason,
                    "comment":       comment,
                }
                try:
                    append_feedback_to_file(record)
                    st.session_state[msg_key][idx].update({
                        "dislike_reason":  reason,
                        "dislike_comment": comment,
                        "feedback_saved":  True,
                    })
                except Exception as e:
                    st.error(f"Could not save feedback: {e}")
                return


# ── Single panel renderer ─────────────────────────────────────────
def render_panel(panel_id: str, logo_b64: str):
    msg_key  = f"messages_{panel_id.lower()}"
    topic    = st.session_state.get("topic", "Academic Calendar")
    messages = st.session_state.get(msg_key, [])

    future     = st.session_state.get(f"future_{panel_id}")
    is_pending = future is not None and not future.done()

    ensure_message_ids(messages)
    st.session_state[msg_key] = messages

    # ── Render chat bubbles ───────────────────────────────────────
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
</div>"""

    msgs_html    = render_messages(messages, logo_b64)
    thinking_tag = "<span class='thinking-tag'>thinking...</span>" if is_pending else ""

    st.markdown(f"""
<div class="panel-wrap">
  <div class="panel-head">
    Chatbot {panel_id}
    <span class="model-tag">Model {panel_id}</span>
    {thinking_tag}
  </div>
  <div class="msgs-area" id="msgs-{panel_id}">{msgs_html}{thinking_html}</div>
</div>
""", unsafe_allow_html=True)

    # ── Sources for latest assistant message ──────────────────────
    latest_assistant = None
    latest_idx       = None
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx]["role"] == "assistant":
            latest_assistant = messages[idx]
            latest_idx       = idx
            break

    if latest_assistant:
        render_sources_block(
            latest_assistant.get("sources", []),
            panel_id,
            latest_assistant["message_id"],
        )

    # ── Feedback ──────────────────────────────────────────────────
    if ENABLE_FEEDBACK and latest_assistant is not None:
        b1, b2, _ = st.columns([1, 1, 10])
        with b1:
            if st.button("👍", key=f"like_{panel_id}_{latest_assistant['message_id']}"):
                st.session_state[msg_key][latest_idx]["feedback"] = {"score": "👍", "text": ""}
                st.session_state[msg_key][latest_idx]["show_reason_picker"] = False
                st.rerun()
        with b2:
            if st.button("👎", key=f"dislike_{panel_id}_{latest_assistant['message_id']}"):
                st.session_state[msg_key][latest_idx]["feedback"] = "down"
                st.session_state[msg_key][latest_idx]["show_reason_picker"] = True
                st.rerun()

        if st.session_state[msg_key][latest_idx].get("show_reason_picker", False):
            selected_reason = st.radio(
                "What went wrong?",
                DISLIKE_REASONS,
                key=f"reason_{panel_id}_{latest_assistant['message_id']}",
                horizontal=True,
            )
            other_text = ""
            if selected_reason == "Other":
                other_text = st.text_input(
                    "Tell us more",
                    key=f"other_{panel_id}_{latest_assistant['message_id']}",
                    placeholder="Type the issue here...",
                )
            if st.button("Save feedback", key=f"save_fb_{panel_id}_{latest_assistant['message_id']}"):
                final_comment = other_text.strip() if selected_reason == "Other" else ""
                st.session_state[msg_key][latest_idx].update({
                    "feedback":           {"score": "👎", "text": ""},
                    "dislike_reason":     selected_reason,
                    "dislike_comment":    final_comment,
                    "show_reason_picker": False,
                })
                save_final_feedback(panel_id, latest_assistant["message_id"],
                                    reason=selected_reason, comment=final_comment)
                st.success("Feedback saved.")
                st.rerun()

    # ── Input form ────────────────────────────────────────────────
    reset_count = st.session_state.get(f"inp_reset_{panel_id}", 0)
    inp_key     = f"inp_{panel_id}_{reset_count}"

    with st.form(key=f"form_{panel_id}_{reset_count}", clear_on_submit=True):
        user_input = st.text_input(
            label="msg",
            key=inp_key,
            placeholder="Ask me anything related to IIT...",
            label_visibility="collapsed",
            disabled=is_pending,
        )
        send_col, _ = st.columns([1, 3])
        with send_col:
            submitted = st.form_submit_button(
                "Send >",
                use_container_width=True,
                disabled=is_pending,
            )

    st.markdown('<p class="inp-hint">Press Enter or click Send</p>', unsafe_allow_html=True)

    if submitted and user_input.strip() and not is_pending:
        clean_input = user_input.strip()

        # Append user message immediately
        messages.append({"role": "user", "content": clean_input, "sources": []})
        st.session_state[msg_key] = messages

        # Submit to thread — returns immediately
        submit_request(panel_id, clean_input, topic)

        st.session_state[f"inp_reset_{panel_id}"] += 1
        st.rerun()


# ── Chat page entry point ─────────────────────────────────────────
def render_chat_page():
    ensure_async_state()

    # Collect any completed futures FIRST — no polling, no sleep
    collect_completed_futures()

    st.session_state.page = "chat"

    logo_b64    = get_logo_b64()
    theme       = st.session_state.get("theme", "light")
    theme_label = "Dark" if theme == "light" else "Light"

    t1, t2, t3 = st.columns([1, 6, 1])
    with t1:
        if st.button("<", key="back_btn"):
            st.session_state.page = "home"
            st.rerun()
    with t2:
        st.markdown(
            '<p class="topbar-brand">IIT Chatbot</p>'
            '<p class="topbar-sub">Helps with Academic Calendar, Tuition, Directory, Policies and the Student Handbook</p>',
            unsafe_allow_html=True,
        )
    with t3:
        if st.button(theme_label, key="chat_theme_btn"):
            st.session_state.theme = "dark" if theme == "light" else "light"
            st.rerun()

    st.markdown('<div class="topbar-line"></div>', unsafe_allow_html=True)

    a_col, b_col = st.columns(2)
    with a_col:
        render_panel("A", logo_b64)
    with b_col:
        render_panel("B", logo_b64)
