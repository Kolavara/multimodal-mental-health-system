import streamlit as st
import traceback
import logging
import time

logger = logging.getLogger(__name__)


def render_chat_panel(agent_workflow, state, tts_engine=None):
    """Renders the clinical chat interface with LangGraph agent interactions."""
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)

    current_agent = state.get("current_agent", "psychologist")
    agent_icon = "🧠" if current_agent == "psychologist" else "⚕️"
    agent_color = "#6366f1" if current_agent == "psychologist" else "#f43f5e"

    st.markdown(
        f'<p class="section-header">{agent_icon} Clinical Interaction — '
        f'<span style="color:{agent_color}">{current_agent.title()}</span> Active</p>',
        unsafe_allow_html=True
    )

    # ── Chat History Display ──────────────────────────────────
    chat_container = st.container(height=420)
    with chat_container:
        for msg in state.get("messages", []):
            role = "user" if msg.type == "human" else "assistant"
            with st.chat_message(role):
                st.write(msg.content)

        escalation = state.get("escalation_reason", "")
        if escalation and current_agent == "psychiatrist":
            st.info(f"⚕️ **Escalation:** {escalation}")

    # ── Input Methods ─────────────────────────────────────────
    user_input = st.chat_input("Type your response...")
    final_input = None

    # ── Handle Text Input ─────────────────────────────────────
    if user_input:
        final_input = user_input
        if hasattr(st.session_state, 'speech_engine'):
            # Manually trigger text classification for text input so metrics update
            st.session_state.speech_engine._classify_text_async(final_input)

    # ── Process Input → Agent → TTS ───────────────────────────
    if final_input:
        from langchain_core.messages import HumanMessage

        # Inject latest speech features into state for agent context
        if hasattr(st.session_state, 'speech_engine'):
            state["speech_features"] = st.session_state.speech_engine.latest_speech_data

        # Record a severity snapshot for this interaction (updates average distress)
        if hasattr(st.session_state, 'fusion_engine'):
            st.session_state.fusion_engine.record_chat_snapshot()

        state["messages"].append(HumanMessage(content=final_input))

        # Show user message immediately
        with chat_container:
            with st.chat_message("user"):
                st.write(final_input)

        # Block auto-refresh during agent call
        st.session_state["_audio_processing"] = True

        # Call the agent
        with st.spinner(f"💭 {current_agent.title()} is thinking..."):
            try:
                # Stop any current TTS before agent responds
                if tts_engine:
                    tts_engine.stop_current_speech()

                new_state = agent_workflow.invoke(state)

                # Merge new state back
                for k, v in new_state.items():
                    state[k] = v

                # Get the latest AI response and speak it
                latest_msg = state["messages"][-1]
                if latest_msg.type == "ai" and tts_engine:
                    tts_engine.speak(latest_msg.content)

                st.session_state["_audio_processing"] = False
                st.rerun()

            except Exception as e:
                st.session_state["_audio_processing"] = False
                logger.error(f"Agent pipeline error: {e}", exc_info=True)
                error_detail = traceback.format_exc()
                with open("error_log.txt", "w") as f:
                    f.write(error_detail)

                error_str = str(e).lower()
                if "timeout" in error_str or "timed out" in error_str:
                    st.error("⚠️ The AI service timed out. Please check your internet connection and try again.")
                elif "api" in error_str or "key" in error_str:
                    st.error("⚠️ API authentication error. Please verify your GROQ_API_KEY in the .env file.")
                else:
                    st.error(f"⚠️ Agent Error: {e}")

    st.markdown('</div>', unsafe_allow_html=True)
    return state
