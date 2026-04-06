
import uuid
import streamlit as st
from pathlib import Path
import os
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR / "assets" / "chatbot_icon.png"

page_icon = Image.open(ICON_PATH) if ICON_PATH.exists() else None

st.set_page_config(
    page_title="IIT FAQs Assistant",
    page_icon=page_icon,
    layout="wide",
)

# Session defaults

if "page" not in st.session_state:
    st.session_state.page = "home"
if "theme" not in st.session_state:
    st.session_state.theme = "light"
if "sidebar_open" not in st.session_state:
    # Start collapsed; user opens topics via the top "Topics" button.
    st.session_state.sidebar_open = False
if "topic" not in st.session_state:
    st.session_state.topic = "Academic Calendar"

if "session_id_a" not in st.session_state:
    st.session_state.session_id_a = str(uuid.uuid4())

if "session_id_b" not in st.session_state:
    st.session_state.session_id_b = str(uuid.uuid4())

if "messages_a" not in st.session_state:
    st.session_state.messages_a = [{
        "role": "assistant",
        "content": "Hi! I'm Chatbot A. Ask me anything about IIT — calendar, tuition, policies, and more.",
        "message_id": 0,
        "feedback": None,
        "feedback_saved": False,
        "dislike_reason": None,
        "dislike_comment": "",
    }]

if "messages_b" not in st.session_state:
    st.session_state.messages_b = [{
        "role": "assistant",
        "content": "Hi! I'm Chatbot B. Ask me anything about IIT — calendar, tuition, policies, and more.",
        "message_id": 0,
        "feedback": None,
        "feedback_saved": False,
        "dislike_reason": None,
        "dislike_comment": "",
    }]

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSS_PATH = BASE_DIR / "assets" / "styles.css"

css = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""

if css:
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
else:
    st.warning("assets/styles.css not found")
    
# Reliable server-side theme switch.
if st.session_state.theme == "dark":
    st.markdown(
        """
<style>
:root {
    --bg:           #13131f;
    --bg-card:      #1d1d2e;
    --bg-head:      #17172a;
    --bg-bot-bub:   #252540;
    --bg-user-bub:  #CC0000;
    --bg-chip:      #2a0808;
    --bg-topic-act: #280808;
    --bg-input:     #1d1d2e;
    --txt:          #e8e8f2;
    --txt-sub:      #aaaacc;
    --txt-muted:    #666688;
    --txt-chip:     #ff9090;
    --txt-topic:    #b0b0cc;
    --txt-topic-act:#ff7070;
    --txt-bot-bub:  #e8e8f2;
    --txt-user-bub: #ffffff;
    --border:       #2a2a44;
    --border-act:   #CC0000;
    --shadow-cta:   rgba(204,0,0,0.45);
}
</style>
""",
        unsafe_allow_html=True,
    )

st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
[data-testid="stToolbar"], .stDeployButton,
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none !important;}
div[data-testid="InputInstructions"],
small[data-testid="InputInstructions"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

from components.homepage import render_homepage
from components.chat_page import render_chat_page

if st.session_state.page == "home":
    render_homepage()
else:
    render_chat_page()
