"""Chat panel component managing conversation flow, new chat prompts, and memory attribution."""

from datetime import datetime
from typing import Any, Optional
import streamlit as st

from app.domain.models import ChatRequest, Message, MessageRole, utc_now
from app.services.container import Container

TYPE_ICONS: dict[str, str] = {
    "allergy": "🚨",
    "preference": "⭐",
    "meal_outcome": "🍽️",
    "pantry_item": "🥫",
    "temporary_context": "⏱️",
}


def _render_memory_attribution(memories_used: list[Any]) -> None:
    """Render a compact memory recall expander underneath an assistant response."""
    if not memories_used:
        return

    count = len(memories_used)
    with st.expander(f"🧠 {count} Memory Record{'s' if count > 1 else ''} Recalled & Applied", expanded=False):
        for mem in memories_used:
            mem_type = getattr(mem, "type", "memory")
            type_val = mem_type.value if hasattr(mem_type, "value") else str(mem_type)
            icon = TYPE_ICONS.get(type_val, "📌")
            text = getattr(mem, "text", "")
            reason = getattr(mem, "reason", "")

            st.markdown(f"**{icon} {type_val.replace('_', ' ').title()}:** *\"{text}\"*")
            if reason:
                st.caption(f"↳ {reason}")


def render_chat_panel(container: Container, user_id: str, session_id: str) -> None:
    """Render the primary chatbot interface with clean new-chat state and message loading."""
    # 1. Load session message history if not already cached in state
    if "messages" not in st.session_state or not st.session_state.messages:
        try:
            stored_msgs = container.orchestrator.get_history(user_id=user_id, session_id=session_id)
            st.session_state.messages = [
                {
                    "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                    "content": m.content,
                    "memories_used": m.memories_used or [],
                    "created_at": m.created_at,
                }
                for m in stored_msgs
            ]
        except Exception:
            st.session_state.messages = []

    # 2. Default "New Chat" View (when no conversation turns exist yet)
    selected_prompt: Optional[str] = None
    if not st.session_state.messages:
        st.markdown(
            """
            <div style="text-align: center; margin-top: 2rem; margin-bottom: 2.5rem;">
                <h1 style="font-size: 2.5rem; margin-bottom: 0.5rem;">🍳 Chef</h1>
                <p style="color: #6c757d; font-size: 1.1rem;">
                    Your conversational culinary AI assistant with memory of your diet, allergies, ingredients, and tastes.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("##### 💡 Try one of these prompts to get started:")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🍽️ What should I cook for dinner tonight?", use_container_width=True):
                selected_prompt = "What should I cook for dinner tonight?"
            if st.button("🥗 Suggest a quick healthy lunch", use_container_width=True):
                selected_prompt = "Suggest a quick healthy lunch"
        with c2:
            if st.button("🍳 I have eggs, spinach and paneer. What can I make?", use_container_width=True):
                selected_prompt = "I have eggs, spinach and paneer. What can I make?"
            if st.button("🥔 Give me an easy snack idea", use_container_width=True):
                selected_prompt = "Give me an easy snack idea"

        st.markdown("<br>", unsafe_allow_html=True)

    # 3. Render Existing Conversation Messages
    for msg in st.session_state.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        memories = msg.get("memories_used", [])

        with st.chat_message(role):
            st.markdown(content)
            if role == "assistant" and memories:
                _render_memory_attribution(memories)

    # 4. Handle Pending Confirmations (e.g. Allergy updates)
    last_resp = getattr(st.session_state, "last_response", None)
    if last_resp and getattr(last_resp, "pending_confirmations", None):
        for conf in list(last_resp.pending_confirmations):
            change_id = conf.get("change_id") or conf.get("id", "")
            proposed_text = conf.get("proposed_text") or conf.get("text", "")
            reason = conf.get("reason", "Protected memory update requires confirmation.")

            with st.status(f"⚠️ Confirmation Required: {reason}", state="error", expanded=True):
                st.write(f"Proposed Update: **{proposed_text}**")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ Approve Update", key=f"conf_yes_{change_id}"):
                        container.orchestrator.confirm_change(user_id=user_id, change_id=change_id, approved=True)
                        st.success("Memory update confirmed and saved!")
                        last_resp.pending_confirmations.remove(conf)
                        st.rerun()
                with col_no:
                    if st.button("❌ Reject", key=f"conf_no_{change_id}"):
                        container.orchestrator.confirm_change(user_id=user_id, change_id=change_id, approved=False)
                        st.info("Memory update cancelled.")
                        last_resp.pending_confirmations.remove(conf)
                        st.rerun()

    # 5. User Input Dispatch
    user_prompt = st.chat_input("Message Memory Chef...") or selected_prompt

    if user_prompt:
        trimmed = user_prompt.strip()
        if trimmed:
            # Append user turn to local state
            st.session_state.messages.append({
                "role": "user",
                "content": trimmed,
                "memories_used": [],
                "created_at": utc_now(),
            })
            with st.chat_message("user"):
                st.markdown(trimmed)

            # Invoke Orchestrator for Assistant turn
            with st.chat_message("assistant"):
                with st.spinner("Memory Chef is recalling memories and thinking..."):
                    req = ChatRequest(
                        user_id=user_id,
                        session_id=session_id,
                        message=trimmed,
                        client_timestamp=utc_now(),
                    )
                    response = container.orchestrator.handle_message(req)
                    st.markdown(response.answer)
                    if response.memories_used:
                        _render_memory_attribution(response.memories_used)

            # Persist response in session state
            st.session_state.last_response = response
            st.session_state.messages.append({
                "role": "assistant",
                "content": response.answer,
                "memories_used": response.memories_used or [],
                "created_at": utc_now(),
            })

            st.rerun()
