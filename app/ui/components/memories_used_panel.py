"""Panel component rendering real-time memory attribution, rankings, and safety warnings."""

from typing import Optional
import streamlit as st

from app.domain.models import ChatResponse, MemoryType


TYPE_ICONS: dict[str, str] = {
    "allergy": "🚨",
    "preference": "⭐",
    "meal_outcome": "🍽️",
    "pantry_item": "🥫",
    "temporary_context": "⏱️",
}


def render_memories_used_panel(response: Optional[ChatResponse]) -> None:
    """Render memory attribution and trace diagnostics for the latest response."""
    st.subheader("🧠 Memory Attribution")

    if not response:
        st.info("No memories recalled yet. Ask a question or share food preferences to see memory attribution!")
        return

    # 1. Safety Alerts
    if response.safety_warnings:
        for warning in response.safety_warnings:
            st.error(f"🛡️ **Safety Guardrail**: {warning}")

    # 2. General System Warnings
    if response.warnings:
        for warn in response.warnings:
            st.warning(f"⚠️ {warn}")

    # 3. Recalled & Used Memories
    memories_used = response.memories_used or []
    if memories_used:
        st.markdown(f"**{len(memories_used)} Memories Recalled & Applied:**")
        for idx, mem in enumerate(memories_used, start=1):
            mem_type = mem.type.value if hasattr(mem.type, "value") else str(mem.type)
            icon = TYPE_ICONS.get(mem_type, "📌")
            type_label = mem_type.replace("_", " ").title()

            with st.container(border=True):
                st.markdown(f"**{icon} {type_label}** — *\"{mem.text}\"*")
                if mem.reason:
                    st.caption(f"**Attribution:** {mem.reason}")

                if mem.score_breakdown:
                    sb = mem.score_breakdown
                    with st.expander(f"📊 Ranking Score: {sb.final_score:.3f}", expanded=False):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.write(f"• **Similarity:** `{sb.similarity:.3f}`")
                            st.write(f"• **Recency Boost:** `{sb.recency_boost:.3f}`")
                            st.write(f"• **Rating Boost:** `{sb.rating_boost:.3f}`")
                        with c2:
                            st.write(f"• **Type Priority:** `{sb.type_priority_boost:.3f}`")
                            st.write(f"• **Usage Bonus:** `{sb.usage_bonus:.3f}`")
                            st.write(f"• **Final Composite:** `{sb.final_score:.3f}`")
    else:
        st.caption("No stored memories were relevant to this message.")

    st.divider()

    # 4. Ingestion & Lifecycle Events
    c_created = len(response.memories_created or [])
    c_superseded = len(response.memories_superseded or [])

    if c_created > 0 or c_superseded > 0:
        st.markdown("**🔄 Memory Store Updates:**")
        if c_created > 0:
            st.success(f"✨ Learned **{c_created}** new memory record(s).")
        if c_superseded > 0:
            st.info(f"🔄 Superseded **{c_superseded}** outdated memory record(s).")

    # 5. Performance & Trace Diagnostics
    if response.trace:
        trace = response.trace
        with st.expander("⚡ Execution Trace & Latency", expanded=False):
            if trace.timings:
                for step in trace.timings:
                    st.write(f"• `{step.step}`: **{step.ms} ms**")

            if trace.degraded_steps:
                st.warning(f"Degraded steps: {', '.join(trace.degraded_steps)}")
            if trace.skipped:
                st.caption(f"Skipped candidates: {len(trace.skipped)}")

