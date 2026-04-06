import streamlit as st
import base64
from pathlib import Path


def get_logo_b64() -> str:
    logo_path = Path("assets/logo.jpg")
    if logo_path.exists():
        return base64.b64encode(logo_path.read_bytes()).decode()
    return ""


def inject_styles(theme: str = "light"):
    css_path = Path("assets/styles.css")
    css = css_path.read_text() if css_path.exists() else ""
    theme_class = "theme-light" if theme == "light" else "theme-dark"
    st.markdown(f"""
<style>
{css}
</style>
<script>
document.body.setAttribute('data-theme', '{theme}');
</script>
""", unsafe_allow_html=True)


def render_header(show_home: bool = False, show_sidebar_toggle: bool = False):
    logo_b64 = get_logo_b64()

    toggle_html = ""
    if show_sidebar_toggle:
        icon = "✕" if st.session_state.get("sidebar_open", True) else "☰"
        toggle_html = f"""
        <form method="get" style="display:inline">
        </form>
        """

    theme_label = "🌙 Dark" if st.session_state.theme == "light" else "☀ Light"

    st.markdown(f"""
<div class="iit-topbar">
    <div class="iit-topbar-left">
        {"<button class='iit-hamburger' id='sidebar-toggle-btn' onclick='void(0)'>☰</button>" if show_sidebar_toggle else ""}
        <span class="iit-topbar-title">🎓 IIT Chatbot</span>
    </div>
    <div class="iit-topbar-right">
    </div>
</div>
""", unsafe_allow_html=True)

    # Render actual Streamlit buttons in columns
    cols = st.columns([6, 1, 1] if show_home else [7, 1])

    with cols[-1 if not show_home else -2]:
        if st.button(theme_label, key="theme_btn", use_container_width=True):
            st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"
            st.rerun()

    if show_home:
        with cols[-1]:
            if st.button("🏠 Home", key="home_btn", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
