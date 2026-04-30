import streamlit as st
import os

st.set_page_config(page_title="Clinician Dashboard", page_icon="🚨", layout="wide")

css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=2000, key="clinician_refresh")
except ImportError:
    pass

st.title("🚨 Clinician Oversight Dashboard")

if "fusion_engine" not in st.session_state:
    st.warning("Main application is not running. Start `app.py` first.")
    st.stop()

from utils.safety_engine import safety_monitor

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">📊 Live Patient Telemetry</p>', unsafe_allow_html=True)

    live_state = st.session_state.fusion_engine.get_state()
    severity = live_state.get('severity_score', 0.0)

    st.metric("Global Severity Score", f"{severity:.2f} / 1.0")
    st.progress(min(severity, 1.0))

    f_data = live_state.get("facial", {})
    s_data = live_state.get("speech", {})

    st.markdown("#### Feature Breakdown")
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        emotion = f_data.get('dominant_emotion', 'N/A')
        st.metric("Emotion", emotion.title() if isinstance(emotion, str) else "N/A")
    with m2:
        st.metric("Facial Valence", f"{f_data.get('facial_valence', 0.0):.2f}")
    with m3:
        st.metric("Eye Contact", f"{f_data.get('eye_contact_ratio', 0.0):.0%}")
    with m4:
        st.metric("Head Velocity", f"{f_data.get('head_movement_velocity', 0.0):.1f}")

    # Microexpression events
    micro_events = f_data.get('recent_microexpressions', [])
    if micro_events:
        with st.expander(f"⚡ Microexpressions ({len(micro_events)} recent)", expanded=False):
            for evt in micro_events[-5:]:
                st.caption(f"• **{evt.get('type', 'unknown')}** — {evt.get('duration_ms', 0)}ms — {evt.get('clinical_note', '')}")

    st.markdown('</div>', unsafe_allow_html=True)

    # Transcript viewer
    if "speech_engine" in st.session_state:
        st.markdown('<div class="neu-card">', unsafe_allow_html=True)
        st.markdown('<p class="section-header">📝 Session Transcript</p>', unsafe_allow_html=True)
        transcripts = st.session_state.speech_engine.transcript_history[-10:]
        if transcripts:
            for t in transcripts:
                st.text(f"[{t.get('timestamp', 0):.0f}] {t.get('text', '')}")
        else:
            st.caption("No transcripts yet.")
        st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">🛡️ Safety Controls</p>', unsafe_allow_html=True)

    if safety_monitor.is_halted:
        st.markdown('<div class="crisis-banner">', unsafe_allow_html=True)
        st.error("🚨 SYSTEM IS HALTED")
        st.write(f"**Reason:** {safety_monitor.halt_reason}")
        st.markdown('</div>', unsafe_allow_html=True)
        if st.button("✅ Acknowledge & Reset System"):
            safety_monitor.reset()
            st.rerun()
    else:
        st.success("✅ System Operating Normally")
        if st.button("🛑 EMERGENCY STOP", type="primary"):
            safety_monitor.manual_override()
            if "tts_engine" in st.session_state:
                st.session_state.tts_engine.stop_current_speech()
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # Clinical summaries
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">📋 Engine Summaries</p>', unsafe_allow_html=True)
    if "facial_engine" in st.session_state:
        with st.expander("Facial Analysis", expanded=False):
            st.caption(st.session_state.facial_engine.get_clinical_summary())
    if "speech_engine" in st.session_state:
        with st.expander("Conversation Analysis", expanded=False):
            st.caption(st.session_state.speech_engine.get_clinical_summary())
    st.markdown('</div>', unsafe_allow_html=True)


