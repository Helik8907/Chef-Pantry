"""Sidebar component with modern chatbot navigation, session history, and user profile management."""

from datetime import datetime
from typing import Any, Optional
import uuid
import streamlit as st

from app.domain.models import User, UserSettings, utc_now
from app.services.container import Container


def render_sidebar(container: Container) -> dict[str, Any]:
    """Render the ChatGPT/Claude-style sidebar and return active session context.

    Returns:
        dict containing 'user_id', 'session_id', and 'user' instance.
    """
    # 1. Ensure user authentication state
    if not st.session_state.get("authenticated") or not st.session_state.get("current_user_id"):
        return {
            "user_id": None,
            "session_id": None,
            "user": None,
        }

    active_user_id = st.session_state.current_user_id

    # Load or create user record
    raw_user = container.repository.get_user(active_user_id)
    if isinstance(raw_user, dict):
        try:
            user = User.model_validate(raw_user)
        except Exception:
            user_settings = raw_user.get("settings", {})
            user = User(
                user_id=active_user_id,
                display_name=raw_user.get("display_name") or active_user_id.replace("_", " ").title(),
                settings=UserSettings(
                    units=user_settings.get("units", "metric") if isinstance(user_settings, dict) else "metric",
                    memory_enabled=user_settings.get("memory_enabled", True) if isinstance(user_settings, dict) else True,
                ),
                created_at=raw_user.get("created_at") or utc_now(),
                updated_at=raw_user.get("updated_at") or utc_now(),
            )
    elif isinstance(raw_user, User):
        user = raw_user
    else:
        user = User(
            user_id=active_user_id,
            display_name=active_user_id.replace("_", " ").title(),
            settings=UserSettings(units="metric", memory_enabled=True),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        try:
            container.repository.upsert_user(user)
        except Exception:
            pass

    # Ensure active session and view state exist
    if "active_view" not in st.session_state:
        st.session_state.active_view = "chat"

    if "current_session_id" not in st.session_state or not st.session_state.current_session_id:
        st.session_state.current_session_id = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.session_state.last_response = None

    # --- Top Sidebar: Primary Navigation ---
    st.sidebar.markdown("### 🍳 Chef")
    if st.sidebar.button("➕ New Chat", use_container_width=True, type="primary"):
        st.session_state.active_view = "chat"
        st.session_state.current_session_id = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.session_state.last_response = None
        print(f"[SESSION] ➕ New chat session created: {st.session_state.current_session_id} (User: {active_user_id})", flush=True)
        st.rerun()

    is_mem_view = (st.session_state.get("active_view") == "memory_management")
    if st.sidebar.button(
        "🧠 Memory Management",
        use_container_width=True,
        type="primary" if is_mem_view else "secondary",
        help="Open memory management page to inspect and manage saved culinary memories",
    ):
        st.session_state.active_view = "memory_management"
        print(f"[NAV] 🧠 Switched to Memory Management (User: {active_user_id})", flush=True)
        st.rerun()

    st.sidebar.markdown("---")

    # --- Middle Sidebar: Chat History List ---
    st.sidebar.markdown("##### 💬 Recent Chats")

    try:
        raw_sessions = container.orchestrator.list_sessions(user_id=active_user_id, limit=30)
    except Exception:
        raw_sessions = []

    if not raw_sessions:
        st.sidebar.caption("No previous conversations yet.")
    else:
        for s in raw_sessions:
            sid = s.get("session_id", "")
            if not sid:
                continue

            msg_count = s.get("message_count", 0)
            last_time = s.get("last_message_time")
            time_label = ""
            if isinstance(last_time, datetime):
                time_label = last_time.strftime("%b %d, %H:%M")
            elif isinstance(last_time, str):
                time_label = last_time[:16]

            # Format a friendly label for the chat button
            is_active = (sid == st.session_state.current_session_id)
            if time_label:
                title = f"{time_label} ({msg_count})" if msg_count else time_label
            else:
                title = f"Conversation ({msg_count})" if msg_count else "Conversation"

            col_btn, col_del = st.sidebar.columns([5, 1])

            with col_btn:
                btn_type = "primary" if is_active else "secondary"
                if st.button(
                    f"{'👉 ' if is_active else '🗨️ '}{title}",
                    key=f"sess_btn_{sid}",
                    use_container_width=True,
                    type=btn_type,
                ):
                    if not is_active:
                        st.session_state.active_view = "chat"
                        st.session_state.current_session_id = sid
                        # Invalidate in-memory messages to trigger fresh DB reload
                        st.session_state.messages = []
                        st.session_state.last_response = None
                        print(f"[SESSION] 🗨️ Switched to session: {sid} (User: {active_user_id})", flush=True)
                        st.rerun()
                    elif st.session_state.get("active_view") != "chat":
                        st.session_state.active_view = "chat"
                        st.rerun()

            with col_del:
                if st.button("🗑️", key=f"del_sess_{sid}", help="Delete this chat"):
                    try:
                        container.repository.delete_session(user_id=active_user_id, session_id=sid)
                        print(f"[SESSION] 🗑️ Deleted chat session: {sid} (User: {active_user_id})", flush=True)
                    except Exception:
                        pass
                    if is_active:
                        st.session_state.current_session_id = f"session_{uuid.uuid4().hex[:8]}"
                        st.session_state.messages = []
                        st.session_state.last_response = None
                    st.rerun()

    st.sidebar.markdown("---")

    # --- Bottom Sidebar: User Profile, Settings, Danger Zone & Logout ---
    with st.sidebar.expander(f"👤 {user.display_name or 'My Profile'}", expanded=False):
        if getattr(user, "email", None):
            st.caption(f"**Email:** `{user.email}`")

        # Memory & Unit Preferences
        memory_enabled = st.checkbox(
            "Enable Long-Term Memory",
            value=user.settings.memory_enabled,
            help="When disabled, past memories are not recalled during answering.",
        )
        units_choice = st.selectbox(
            "Measurement Units",
            options=["metric", "imperial"],
            index=0 if user.settings.units == "metric" else 1,
            help="Default units used in recipe ingredients.",
        )

        settings_changed = (
            memory_enabled != user.settings.memory_enabled
            or units_choice != user.settings.units
        )
        if settings_changed:
            updated_user = User(
                user_id=user.user_id,
                email=user.email,
                display_name=user.display_name,
                password_hash=user.password_hash,
                settings=UserSettings(
                    units=units_choice,  # type: ignore[arg-type]
                    memory_enabled=memory_enabled,
                ),
                created_at=user.created_at,
                updated_at=utc_now(),
            )
            try:
                container.repository.upsert_user(updated_user)
                user = updated_user
                st.success("Preferences saved!")
            except Exception as exc:
                st.error(f"Failed to update preferences: {exc}")

    # Danger Zone: Delete Account
    with st.sidebar.expander("⚠️ Danger Zone (Account)", expanded=False):
        st.caption("Permanently delete your account and all associated culinary memories and conversations.")
        confirm_del = st.checkbox("I understand this is permanent", key="confirm_delete_account_checkbox")
        if st.button("🗑️ Delete Account", type="primary", disabled=not confirm_del, use_container_width=True):
            user_repo = getattr(container.repository, "user_repo", container.repository)
            user_repo.delete_user(active_user_id, cascade=True)
            print(f"[AUTH] ⚠️ Account permanently deleted: {active_user_id}", flush=True)
            st.session_state.authenticated = False
            st.session_state.auth_user = None
            st.session_state.current_user_id = None
            st.session_state.current_session_id = None
            st.session_state.messages = []
            st.session_state.last_response = None
            st.success("Your account has been deleted.")
            st.rerun()

    # Logout Action
    if st.sidebar.button("🚪 Log Out", use_container_width=True):
        print(f"[AUTH] 🚪 User logged out: {active_user_id}", flush=True)
        st.session_state.authenticated = False
        st.session_state.auth_user = None
        st.session_state.current_user_id = None
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.session_state.last_response = None
        st.rerun()

    return {
        "user_id": active_user_id,
        "session_id": st.session_state.current_session_id,
        "user": user,
        "active_view": st.session_state.get("active_view", "chat"),
    }
