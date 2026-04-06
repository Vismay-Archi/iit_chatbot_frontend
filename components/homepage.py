import streamlit as st
import base64
from pathlib import Path


def get_logo_b64() -> str:
    p = Path("assets/logo.jpg")
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    return ""


def render_homepage():
    theme = st.session_state.get("theme", "light")
    logo_b64 = get_logo_b64()

    # ── Top bar row ───────────────────────────────────────────────
    left, spacer, right = st.columns([1, 5, 1])
    with left:
        st.markdown('<p class="topbar-brand">IIT Chatbot</p>', unsafe_allow_html=True)
    with right:
        # Theme toggle removed from homepage (theme switcher is in IIT Chatbot header).
        pass

    st.markdown('<div class="topbar-line"></div>', unsafe_allow_html=True)

    # ── Logo ──────────────────────────────────────────────────────
    if logo_b64:
        logo_html = f'<img src="data:image/jpeg;base64,{logo_b64}" class="home-logo-img" alt="IIT Logo"/>'
    else:
        logo_html = '<div class="home-logo-fallback">IIT</div>'

    # ── Main content ──────────────────────────────────────────────
    st.markdown(f"""
<div class="home-wrapper">
  <div class="home-card">
    {logo_html}
    <h1 class="home-title">IIT Chatbot</h1>
    <p class="home-desc">Your AI-powered assistant for Illinois Institute of Technology.<br>Get instant answers about:</p>
    <div class="home-chips">
      <span class="chip">Academic Calendar</span>
      <span class="chip">Tuition</span>
      <span class="chip">Directory</span>
      <span class="chip">Policies</span>
      <span class="chip">Handbook</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── CTA Button ────────────────────────────────────────────────
    with st.container(key="home_cta_wrap"):
        _, mid, _ = st.columns([3, 2, 3])
        with mid:
            if st.button("Let's get started", key="cta_btn", use_container_width=True):
                st.session_state.page = "chat"
                st.rerun()
