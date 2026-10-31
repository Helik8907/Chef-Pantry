"""Main Streamlit application entrypoint for Chef."""

from pathlib import Path
import sys
import uuid

# Ensure project root is in sys.path for direct `streamlit run` execution
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from app.services.container import Container, build_container
from app.ui.components.auth_view import render_auth_view
from app.ui.components.chat_panel import render_chat_panel
from app.ui.components.memory_management import render_memory_management
from app.ui.components.sidebar import render_sidebar


# 1. Page Configuration
st.set_page_config(
    page_title="Chef",
    page_icon="🍳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# 2. Cached Application Container
@st.cache_resource(show_spinner="Connecting to Chef Services...")
def get_app_container() -> Container:
    """Initialize and cache the dependency injection container."""
    return build_container()


def main() -> None:
    """Primary application controller."""
    container = get_app_container()

    # 3. Check Authentication State
    if not st.session_state.get("authenticated") or not st.session_state.get("current_user_id"):
        print("[PAGE VISIT] 🔑 Auth View (Sign In / Register)", flush=True)
        render_auth_view(container)
        return

    # 4. Render ChatGPT/Claude-style Sidebar
    ctx = render_sidebar(container)
    user_id = ctx["user_id"]
    session_id = ctx["session_id"]
    active_view = ctx.get("active_view", "chat")

    # 5. Route to Active View
    if active_view == "memory_management":
        print(f"[PAGE VISIT] 🧠 Memory Management | User: {user_id}", flush=True)
        render_memory_management(container, user_id=user_id)
    else:
        print(f"[PAGE VISIT] 💬 Culinary Chat | User: {user_id} | Session: {session_id}", flush=True)
        render_chat_panel(container, user_id=user_id, session_id=session_id)



if __name__ == "__main__":
    main()
