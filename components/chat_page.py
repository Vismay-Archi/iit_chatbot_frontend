''' CHATBOT MESSAGES ARE STORED HERE '''
import base64
import html
import json
import os
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

TOPICS = ["Academic Calendar", "Tuition", "Directory", "Policies", "Handbook"]


DISLIKE_REASONS = [
    "Hallucination",
    "No clarification",
    "Not helpful",
    "Wrong answer",
    "Incomplete answer",
    "Other",
]

BASE_DIR = Path(__file__).resolve().parent.parent
FEEDBACK_FILE = BASE_DIR / "feedback_log.jsonl"
MODEL_A_ENDPOINT = os.getenv("MODEL_A_ENDPOINT", "").strip()
MODEL_B_ENDPOINT = os.getenv("MODEL_B_ENDPOINT", "").strip()

ENABLE_FEEDBACK = False

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
        "The Registrar's office can be reached at [registrar@iit.edu](mailto:registrar@iit.edu).",
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


def get_logo_b64() -> str:
    p = Path("assets/logo.jpg")
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    return ""


def bot_avatar(logo_b64: str) -> str:
    if logo_b64:
        return f'<img src="data:image/jpeg;base64,{logo_b64}" class="av-img" alt="IIT"/>'
    return '<div class="av-fallback">IIT</div>'


def render_messages(messages: list, logo_b64: str) -> str:
    html = ""
    for msg in messages:
        text = (
            msg["content"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

        if msg["role"] == "assistant":
            html += f"""
            <div class="msg-row">
            {bot_avatar(logo_b64)}
            <div class="bubble bot-bub">{text}</div>
            </div>"""
        else:
            html += f"""
            <div class="msg-row user-msg-row">
            <div class="bubble user-bub">{text}</div>
            </div>"""
    return html


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
        if "msg_id" not in msg:
            msg["msg_id"] = i
        if "show_reason_picker" not in msg:
            msg["show_reason_picker"] = False
        if "sources" not in msg:
            msg["sources"] = []

        if msg["role"] == "assistant":
            if "message_id" not in msg:
                msg["message_id"] = assistant_id

            if ENABLE_FEEDBACK:
                if "feedback" not in msg:
                    msg["feedback"] = None
                if "feedback_saved" not in msg:
                    msg["feedback_saved"] = False
                if "dislike_reason" not in msg:
                    msg["dislike_reason"] = None
                if "dislike_comment" not in msg:
                    msg["dislike_comment"] = ""

            assistant_id += 1


def append_feedback_to_file(record: dict):
    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_previous_user_message(messages: list, assistant_idx: int):
    for j in range(assistant_idx - 1, -1, -1):
        if messages[j]["role"] == "user":
            return messages[j]["content"]
    return ""

if ENABLE_FEEDBACK:
    def save_feedback(response, panel_id: str, message_id: int):
        st.session_state.page = "chat"

        msg_key = f"messages_{panel_id.lower()}"
        messages = st.session_state.get(msg_key, [])

        for idx, msg in enumerate(messages):
            if msg.get("message_id") == message_id:
                st.session_state[msg_key][idx]["feedback"] = response
                st.session_state[msg_key][idx]["feedback_saved"] = False
                break


    def save_final_feedback(panel_id: str, message_id: int, reason: str = None, comment: str = ""):
        print("=== SAVE FINAL FEEDBACK DEBUG ===")
        print(f"panel_id='{panel_id}', message_id={message_id}, reason='{reason}', comment='{comment}'")
        
        msg_key = f"messages_{panel_id.lower()}"
        print(f"Looking for msg_key='{msg_key}'")
        
        messages = st.session_state.get(msg_key, [])
        print(f"Found {len(messages)} messages")
        
        found_match = False
        for idx, msg in enumerate(messages):
            print(f"  msg[{idx}] message_id={msg.get('message_id')}")
            if msg.get("message_id") == message_id:
                found_match = True
                print(f"  --> MATCH at index {idx}")
                
                if msg.get("feedback_saved"):
                    print("Already saved, exiting")
                    return

                user_question = get_previous_user_message(messages, idx)
                feedback_obj = msg.get("feedback", {})
                score = feedback_obj.get("score") if isinstance(feedback_obj, dict) else "unknown"

                record = {
                    "panel_id": panel_id,
                    "message_id": message_id,
                    "question": user_question,
                    "answer": msg.get("content", ""),
                    "score": score,
                    "feedback_text": feedback_obj.get("text") if isinstance(feedback_obj, dict) else "",
                    "reason": reason,
                    "comment": comment,
                }

                print(f"Saving record: {record}")
                print(f"To file: {FEEDBACK_FILE.resolve()}")

                try:
                    append_feedback_to_file(record)
                    st.session_state[msg_key][idx]["dislike_reason"] = reason
                    st.session_state[msg_key][idx]["dislike_comment"] = comment
                    st.session_state[msg_key][idx]["feedback_saved"] = True
                    print("SUCCESS - all saved")
                except Exception as e:
                    print(f"ERROR saving: {e}")
                return
        
        print("ERROR - No message matched message_id")

def call_backend(endpoint: str, payload: dict):
    r = requests.post(endpoint, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()

def get_backend_reply(panel_id: str, user_input: str, topic: str):
    session_key = f"session_id_{panel_id.lower()}"
    session_id = st.session_state.get(session_key)

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
            history = st.session_state.get("messages_b", [])
            chat_history = [
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m.get("role") in ("user", "assistant")
            ]
            payload = {
                "prompt": user_input,
                "topic": topic or "",
                "chat_history": chat_history,
                "pending_context": st.session_state.get("pending_context_b"),
            }

        if not endpoint:
            raise ValueError(f"Missing endpoint for panel {panel_id}")

        data = call_backend(endpoint, payload)

        if panel_id == "A":
            answer = (
                data.get("answer")
                or data.get("response")
                or data.get("content")
                or data.get("text")
                or ""
            )
            # source_urls can be top-level or nested inside results.traffic_cop
            sources = (
                data.get("source_urls")
                or data.get("sources")
                or data.get("results", {}).get("traffic_cop", {}).get("source_urls")
                or []
            )
            if "session_id" in data:
                st.session_state[session_key] = data["session_id"]
        else:
            answer = (
                data.get("response")
                or data.get("answer")
                or data.get("content")
                or data.get("text")
                or ""
            )
            sources = data.get("source_urls") or data.get("sources") or []

            if data.get("is_clarification"):
                st.session_state["pending_context_b"] = data.get("pending_context")
            else:
                st.session_state["pending_context_b"] = None

        if isinstance(sources, str):
            sources = [sources]

        return (answer.strip() if answer else "No response returned."), sources

    except Exception as e:
        fallback = stub_reply(panel_id, topic)
        return f"{fallback}\n\n[Backend unavailable: {e}]", []


def render_sources_block(sources, panel_id: str, message_id: int):
    if not sources:
        return

    with st.expander("Sources", expanded=False):
        for i, src in enumerate(sources, start=1):
            if isinstance(src, dict):
                title = src.get("title") or src.get("label") or f"Source {i}"
                url = src.get("url") or src.get("href") or ""
            else:
                title = f"Source {i}"
                url = str(src).strip()

            if url:
                st.markdown(f"[{title}]({url})")
            else:
                st.markdown(f"{title}")


def render_panel(panel_id: str, logo_b64: str):
    msg_key = f"messages_{panel_id.lower()}"
    inp_key = f"inp_{panel_id}"
    form_key = f"form_{panel_id}"
    topic = st.session_state.get("topic", "Academic Calendar")

    messages = st.session_state.get(msg_key, [])
    ensure_message_ids(messages)
    st.session_state[msg_key] = messages

    msgs_html = render_messages(messages, logo_b64)

    st.markdown(f"""
<div class="panel-wrap">
  <div class="panel-head">Chatbot {panel_id} <span class="model-tag">Model {panel_id}</span></div>
  <div class="msgs-area">{msgs_html}</div>
</div>
""", unsafe_allow_html=True)

    # Show sources for the latest assistant message only
    latest_assistant = None
    latest_idx = None
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx]["role"] == "assistant":
            latest_assistant = messages[idx]
            latest_idx = idx
            break

    if latest_assistant is not None:
        render_sources_block(
            latest_assistant.get("sources", []),
            panel_id,
            latest_assistant["message_id"]
        )

    if ENABLE_FEEDBACK:
        if latest_assistant is not None:
            btn1, btn2, _ = st.columns([1, 1, 10])

            with btn1:
                if st.button("👍", key=f"like_{panel_id}_{latest_assistant['message_id']}"):
                    st.session_state[msg_key][latest_idx]["feedback"] = {"score": "👍", "text": ""}
                    st.session_state[msg_key][latest_idx]["show_reason_picker"] = False
                    st.rerun()

            with btn2:
                if st.button("👎", key=f"dislike_{panel_id}_{latest_assistant['message_id']}"):
                    st.session_state[msg_key][latest_idx]["feedback"] = "down"
                    st.session_state[msg_key][latest_idx]["show_reason_picker"] = True
                    st.rerun()

        if latest_idx is not None and st.session_state[msg_key][latest_idx].get("show_reason_picker", False):
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
                    placeholder="Type the issue here..."
                )

            if st.button("Save feedback", key=f"save_fb_{panel_id}_{latest_assistant['message_id']}"):
                final_comment = other_text.strip() if selected_reason == "Other" else ""
                st.session_state[msg_key][latest_idx]["feedback"] = {"score": "👎", "text": ""}
                st.session_state[msg_key][latest_idx]["dislike_reason"] = selected_reason
                st.session_state[msg_key][latest_idx]["dislike_comment"] = final_comment
                st.session_state[msg_key][latest_idx]["show_reason_picker"] = False

                save_final_feedback(
                    panel_id,
                    latest_assistant["message_id"],
                    reason=selected_reason,
                    comment=final_comment,
                )
                st.success("Feedback saved.")
                st.rerun()

    with st.form(key=form_key, clear_on_submit=True):
        user_input = st.text_input(
            label="msg",
            key=inp_key,
            placeholder="Ask me anything related to IIT...",
            label_visibility="collapsed",
        )

        send_col, _ = st.columns([1, 3])
        with send_col:
            clicked = st.form_submit_button(
                "Send ➤",
                key=f"send_{panel_id}",
                use_container_width=True,
            )

        st.markdown(
            '<p class="inp-hint">Press Enter or click Send</p>',
            unsafe_allow_html=True
        )

        if clicked and user_input.strip():
            assistant_count = sum(1 for m in messages if m["role"] == "assistant")
            clean_input = user_input.strip()

            messages.append({
                "role": "user",
                "content": clean_input
            })

            answer, sources = get_backend_reply(panel_id, clean_input, topic)

            assistant_msg = {
                "role": "assistant",
                "content": answer,
                "sources": sources,
                "message_id": assistant_count,
            }

            if ENABLE_FEEDBACK:
                assistant_msg.update({
                    "feedback": None,
                    "feedback_saved": False,
                    "dislike_reason": None,
                    "dislike_comment": "",
                    "show_reason_picker": False,
                })

            messages.append(assistant_msg)

            st.session_state[msg_key] = messages
            st.rerun()


def render_chat_page():
    st.session_state.page = "chat"
    if ENABLE_FEEDBACK:
        st.caption(f"Feedback file: {FEEDBACK_FILE.resolve()}")
    logo_b64 = get_logo_b64()

    t1, t2, t3 = st.columns([1, 7, 1])
    with t1:
        if st.button("←", key="home_btn"):
            st.session_state.page = "home"

    with t2:
        st.markdown('<p class="topbar-brand">IIT Chatbot</p>', unsafe_allow_html=True)

    with t3:
        if st.button("?", key="help_btn"):
            st.session_state.show_help = not st.session_state.get("show_help", False)

    st.markdown('<div class="topbar-line"></div>', unsafe_allow_html=True)

    if st.session_state.get("show_help", False):
        st.info(
            "This chatbot can help with Academic Calendar, Tuition, Directory, Policies, and the Student Handbook.",
            icon="ℹ️",
        )

    a_col, b_col = st.columns([1, 1])

    with a_col:
        render_panel("A", logo_b64)

    with b_col:
        render_panel("B", logo_b64)
