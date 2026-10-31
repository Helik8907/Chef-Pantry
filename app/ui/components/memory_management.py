"""Memory Management component for browsing, filtering, and managing culinary memories."""

from datetime import datetime
from typing import Any, Optional
import streamlit as st

from app.domain.models import MemoryStatus, MemoryType
from app.services.container import Container

TYPE_ICONS: dict[str, str] = {
    "allergy": "🚨 Allergy",
    "preference": "⭐ Preference",
    "meal_outcome": "🍽️ Meal Outcome",
    "pantry_item": "🥫 Pantry Item",
    "temporary_context": "⏱️ Temporary Context",
}


def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to retrieve values from either a dictionary or a Pydantic model."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def render_memory_management(container: Container, user_id: str) -> None:
    """Render the dedicated memory management and auditing interface."""
    col_title, col_back = st.columns([4, 1])
    with col_title:
        st.markdown("### 🧠 Memory Management")
        st.caption("Browse, search, and manage your long-term culinary preferences, allergies, and pantry items.")
    with col_back:
        if st.button("← Back to Chat", use_container_width=True):
            st.session_state.active_view = "chat"
            st.rerun()

    # 1. Fetch memories
    try:
        raw_memories = container.repository.list_memories(user_id=user_id, limit=200)
    except Exception as exc:
        st.error(f"Failed to load memories: {exc}")
        raw_memories = []

    # 2. High-Level Summary Metrics
    active_mems = [m for m in raw_memories if str(_get_val(m, "status", "active")).lower() == "active"]
    allergies = [m for m in active_mems if str(_get_val(m, "type", "")).lower() in ("allergy", "memorytype.allergy")]
    preferences = [m for m in active_mems if str(_get_val(m, "type", "")).lower() in ("preference", "memorytype.preference")]
    pantry = [m for m in active_mems if str(_get_val(m, "type", "")).lower() in ("pantry_item", "pantry", "memorytype.pantry_item")]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Active Memories", len(active_mems))
    col2.metric("Protected Allergies", len(allergies))
    col3.metric("Taste Preferences", len(preferences))
    col4.metric("Pantry Items", len(pantry))

    st.divider()

    # 3. Filter Controls
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        search_query = st.text_input("🔎 Search memories", placeholder="Filter by keyword (e.g. peanut, spicy, vegan)...").strip().lower()
    with f_col2:
        type_options = ["All"] + list(TYPE_ICONS.keys())
        selected_type = st.selectbox(
            "Filter by Type",
            options=type_options,
            format_func=lambda t: "All Types" if t == "All" else TYPE_ICONS.get(t, t),
        )
    with f_col3:
        status_options = ["All", "active", "superseded", "deleted"]
        selected_status = st.selectbox("Filter by Status", options=status_options)

    # 4. Filter Application
    filtered = raw_memories
    if selected_type != "All":
        filtered = [
            m for m in filtered
            if str(_get_val(m, "type", "")).lower() in (selected_type, f"memorytype.{selected_type}")
        ]
    if selected_status != "All":
        filtered = [
            m for m in filtered
            if str(_get_val(m, "status", "")).lower() == selected_status.lower()
        ]
    if search_query:
        filtered = [
            m for m in filtered
            if search_query in str(_get_val(m, "text", "")).lower()
        ]

    # 5. Display Memory Cards
    st.markdown(f"##### Stored Memories ({len(filtered)})")

    if not filtered:
        st.info("No memories match your search and filter criteria.")
        return

    for idx, mem in enumerate(filtered):
        mem_id = str(_get_val(mem, "_id") or _get_val(mem, "id") or f"mem_{idx}")
        raw_type = str(_get_val(mem, "type", "memory")).lower().replace("memorytype.", "")
        raw_status = str(_get_val(mem, "status", "active")).lower()
        text = str(_get_val(mem, "text", ""))
        confidence = float(_get_val(mem, "confidence", 1.0) or 1.0)
        is_protected = bool(_get_val(mem, "protected", False))
        created_at = _get_val(mem, "created_at")
        expires_at = _get_val(mem, "expires_at")
        usage_count = int(_get_val(mem, "usage_count", 0) or 0)
        tags = _get_val(mem, "tags", []) or []

        icon_label = TYPE_ICONS.get(raw_type, raw_type.title())
        status_color = "green" if raw_status == "active" else "gray" if raw_status == "superseded" else "red"

        with st.container(border=True):
            h_col1, h_col2 = st.columns([4, 1])
            with h_col1:
                st.markdown(f"**{icon_label}** &nbsp; `:{status_color}[{raw_status.upper()}]`")
                st.markdown(f"#### \"{text}\"")
            with h_col2:
                if raw_status == "active":
                    if st.button("🗑️ Forget", key=f"forget_btn_{mem_id}_{idx}", help="Soft-delete this memory"):
                        try:
                            if container.lifecycle:
                                container.lifecycle.forget(user_id=user_id, memory_id=mem_id, hard=False)
                            else:
                                container.repository.soft_delete(user_id=user_id, memory_id=mem_id)
                            st.success("Memory forgotten!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to remove memory: {exc}")

            d_col1, d_col2, d_col3 = st.columns(3)
            with d_col1:
                st.caption(f"**Confidence:** `{confidence:.2f}`")
                st.caption(f"**Protected:** `{'Yes 🛡️' if is_protected else 'No'}`")
            with d_col2:
                created_str = created_at.strftime("%Y-%m-%d %H:%M UTC") if isinstance(created_at, datetime) else str(created_at or "Unknown")
                expires_str = expires_at.strftime("%Y-%m-%d %H:%M UTC") if isinstance(expires_at, datetime) else "Never (Permanent)"
                st.caption(f"**Created:** {created_str}")
                st.caption(f"**Expires:** {expires_str}")
            with d_col3:
                st.caption(f"**Recall Count:** `{usage_count}`")
                tags_str = ", ".join(tags) if tags else "None"
                st.caption(f"**Tags:** `{tags_str}`")

