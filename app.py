import streamlit as st
import os
import time

st.set_page_config(
    page_title="Multimodal Clinical AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

import threading
from engines.facial.facial_engine import FacialAnalysisEngine
from engines.speech.speech_engine import SpeechAnalysisEngine
from utils.feature_fusion import FeatureFusionEngine
from engines.tts.tts_engine import TTSEngine
from agents.graph import build_clinical_graph
from dashboard.video_call import render_video_call
from dashboard.chat_panel import render_chat_panel

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# Load custom CSS
css_path = os.path.join(os.path.dirname(__file__), "dashboard", "assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Initialize Session State ──────────────────────────────────
if "initialized" not in st.session_state:
    try:
        st.session_state.patient_id = "demo_patient_001"
        st.session_state.session_id = "session_001"
        st.session_state.session_start = time.time()

        st.session_state.facial_engine = FacialAnalysisEngine(
            st.session_state.patient_id, st.session_state.session_id
        )
        st.session_state.speech_engine = SpeechAnalysisEngine(
            st.session_state.patient_id, st.session_state.session_id
        )
        st.session_state.speech_engine.start_processing_thread()
        st.session_state.fusion_engine = FeatureFusionEngine()
        st.session_state.tts_engine = TTSEngine()
        st.session_state.tts_engine.start()
        st.session_state.agent_workflow = build_clinical_graph()

        from utils.safety_engine import safety_monitor
        safety_monitor.reset()

        from langchain_core.messages import AIMessage
        initial_greeting = "Hello. I'm the clinical AI assistant. How are you feeling today? Please tell me a bit about what's been on your mind."
        st.session_state.tts_engine.speak(initial_greeting)

        st.session_state.clinical_state = {
            "messages": [AIMessage(content=initial_greeting)],
            "patient_id": st.session_state.patient_id,
            "session_id": st.session_state.session_id,
            "current_severity": 0.0,
            "facial_features": {},
            "speech_features": {},
            "current_agent": "psychologist",
            "escalation_reason": "",
            "clinical_summary": ""
        }

        # Mark initialized LAST so a failure retries on next rerun
        st.session_state.initialized = True
    except Exception as init_error:
        st.error(f"⚠️ Initialization failed: {init_error}")
        st.caption("Please check that all model files and API keys are configured, then refresh.")
        st.stop()


# ── Helper Functions ──────────────────────────────────────────
def get_severity_class(severity):
    if severity < 0.3:
        return "metric-safe"
    elif severity < 0.7:
        return "metric-warn"
    return "metric-danger"

def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# ── Main Title ────────────────────────────────────────────────
st.title("🧠 Multimodal Clinical AI Platform")

# ── Layout: Two Columns ──────────────────────────────────────
col1, col2 = st.columns([1, 1], gap="medium")

with col1:
    # Video Feed
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">📹 Patient Observation</p>', unsafe_allow_html=True)
    webrtc_ctx = render_video_call(
        st.session_state.facial_engine,
        st.session_state.fusion_engine,
        st.session_state.speech_engine
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Live Telemetry
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">📊 Live Telemetry</p>', unsafe_allow_html=True)

    # Update feature fusion with latest speech data
    st.session_state.fusion_engine.update_speech(st.session_state.speech_engine.latest_speech_data)

    live_state = st.session_state.fusion_engine.get_state()
    severity = live_state.get('severity_score', 0.0)
    avg_severity = live_state.get('average_severity_score', severity)
    disorder = live_state.get('likely_disorder', 'Unknown')
    facial = live_state.get("facial", {})

    st.session_state.clinical_state["current_severity"] = severity
    st.session_state.clinical_state["average_severity_score"] = avg_severity
    st.session_state.clinical_state["likely_disorder"] = disorder
    st.session_state.clinical_state["facial_features"] = facial
    st.session_state.clinical_state["speech_features"] = st.session_state.speech_engine.latest_speech_data

    # Safety Check
    from utils.safety_engine import safety_monitor
    if safety_monitor.evaluate_state(live_state):
        st.markdown('<div class="crisis-banner">', unsafe_allow_html=True)
        st.error(f"🚨 SYSTEM HALTED: {safety_monitor.halt_reason}")
        st.markdown('</div>', unsafe_allow_html=True)

    # Severity bars
    st.progress(min(severity, 1.0), text=f"Current Distress: {severity:.2f}")
    st.progress(min(avg_severity, 1.0), text=f"Average Severe Disorder Risk: {avg_severity:.1%}")

    # Metrics row 1
    m1, m2, m3 = st.columns(3)
    emotion = facial.get('dominant_emotion', 'neutral')
    emotion_conf = facial.get('emotion_confidence', 0.0)

    sev_class = get_severity_class(severity)
    with m1:
        st.markdown(f'<div class="{sev_class}">', unsafe_allow_html=True)
        st.metric("Emotion", f"{emotion.title()}" if isinstance(emotion, str) else "N/A")
        st.markdown('</div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="{sev_class}">', unsafe_allow_html=True)
        st.metric("Valence", f"{facial.get('facial_valence', 0.0):+.2f}")
        st.markdown('</div>', unsafe_allow_html=True)
    with m3:
        st.empty()

    # Metrics row 2
    m4, m5, m6 = st.columns(3)
    with m4:
        st.metric("Predicted Disorder", disorder.title())
    with m5:
        st.metric("Head Velocity", f"{facial.get('head_movement_velocity', 0.0):.1f}")
    with m6:
        agent = st.session_state.clinical_state.get("current_agent", "psychologist")
        st.metric("Active Agent", agent.title())

    # Emotion probabilities expander
    emo_probs = facial.get('emotion_probabilities', {})
    if emo_probs:
        with st.expander("🎭 Emotion Distribution", expanded=False):
            for emo_name, prob in sorted(emo_probs.items(), key=lambda x: x[1], reverse=True):
                bar_html = (
                    f'<div style="display:flex;align-items:center;margin:2px 0;">'
                    f'<span style="width:70px;font-size:0.75rem;color:#94a3b8;">{emo_name.title()}</span>'
                    f'<div style="flex:1;height:8px;background:rgba(255,255,255,0.05);border-radius:4px;overflow:hidden;">'
                    f'<div style="width:{prob*100:.0f}%;height:100%;background:linear-gradient(90deg,#6366f1,#8b5cf6);border-radius:4px;"></div>'
                    f'</div>'
                    f'<span style="width:40px;text-align:right;font-size:0.7rem;color:#64748b;">{prob:.0%}</span>'
                    f'</div>'
                )
                st.markdown(bar_html, unsafe_allow_html=True)

    # Microexpressions
    micro_events = facial.get('recent_microexpressions', [])
    if micro_events:
        with st.expander(f"⚡ Microexpressions ({len(micro_events)})", expanded=False):
            for evt in micro_events[-3:]:
                st.caption(
                    f"• **{evt.get('type', '?')}** — "
                    f"{evt.get('duration_ms', 0)}ms — "
                    f"{evt.get('clinical_note', '')}"
                )

    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.session_state.clinical_state = render_chat_panel(
        st.session_state.agent_workflow,
        st.session_state.clinical_state,
        st.session_state.tts_engine
    )

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    # Session timer
    elapsed = time.time() - st.session_state.get("session_start", time.time())
    st.markdown(
        f'<div style="text-align:center;padding:0.5rem;margin-bottom:1rem;">'
        f'<span style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;">Session Duration</span><br>'
        f'<span style="font-size:1.5rem;font-weight:700;color:#f1f5f9;">{format_duration(elapsed)}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    st.divider()

    if st.button("🛑 Emergency Override (Kill Switch)", type="primary", use_container_width=True):
        st.session_state.tts_engine.stop_current_speech()
        safety_monitor.manual_override()
        st.error("SYSTEM HALTED BY CLINICIAN.")
        st.stop()

    st.divider()

    if st.button("📝 End Session & Evaluate", use_container_width=True):
        st.session_state.tts_engine.stop_current_speech()
        st.session_state["_audio_processing"] = True  # Block auto-refresh

        from langchain_core.messages import HumanMessage

        # Fetch the latest telemetry from fusion engine directly (most accurate)
        live = st.session_state.fusion_engine.get_state()
        avg_severity = live.get('average_severity_score', 0.0)
        disorder = live.get('likely_disorder', 'Unknown')

        eval_prompt = (
            f"SYSTEM: The session has ended. Based on the preceding conversation, provide a concise, "
            f"formal clinical statement about the patient's condition. "
            f"The system has predicted an average disorder risk of {avg_severity:.1%} with a likely disorder of {disorder}. "
            f"Include this in your final assessment."
        )
        st.session_state.clinical_state["messages"].append(HumanMessage(content=eval_prompt))

        with st.spinner("Generating final evaluation..."):
            final_state = st.session_state.agent_workflow.invoke(st.session_state.clinical_state)
            st.session_state.clinical_state = final_state

        # Store evaluation persistently in session state
        eval_conclusion = final_state["messages"][-1].content
        facial_summary = st.session_state.facial_engine.get_clinical_summary()
        conversation_summary = st.session_state.speech_engine.get_clinical_summary()

        st.session_state["evaluation_result"] = {
            "facial": facial_summary,
            "conversation": conversation_summary,
            "conclusion": eval_conclusion,
        }
        st.session_state["_audio_processing"] = False
        st.rerun()  # Rerun so the result renders properly

    # Show persisted evaluation result (survives reruns)
    if "evaluation_result" in st.session_state:
        eval_data = st.session_state["evaluation_result"]
        st.subheader("Final Clinical Evaluation")
        st.write(eval_data["facial"])
        st.write(eval_data["conversation"])
        st.markdown("### Agent Conclusion")
        st.write(eval_data["conclusion"])
        if st.button("🔄 Start New Session", use_container_width=True):
            del st.session_state["evaluation_result"]
            del st.session_state["initialized"]
            st.rerun()

    st.divider()
    st.markdown('<p class="section-header">System Status</p>', unsafe_allow_html=True)

    # Status indicators
    def status_dot(active, label):
        cls = "status-active" if active else "status-inactive"
        return f'<span class="status-dot {cls}"></span>{label}'

    webrtc_active = webrtc_ctx and webrtc_ctx.state.playing if webrtc_ctx else False

    st.markdown(status_dot(True, "LangGraph Agent Pipeline"), unsafe_allow_html=True)
    st.markdown(status_dot(True, "Groq LLM (Primary)"), unsafe_allow_html=True)
    st.markdown(status_dot(True, "TensorFlow Emotion Model"), unsafe_allow_html=True)
    st.markdown(status_dot(True, "MediaPipe Face Landmarker"), unsafe_allow_html=True)
    st.markdown(status_dot(webrtc_active, "WebRTC Video/Audio"), unsafe_allow_html=True)
    st.markdown(status_dot(True, "TTS Engine"), unsafe_allow_html=True)

    st.divider()
    st.caption("Patient: demo_patient_001")
    st.caption(f"Severity Threshold: 0.75 | Crisis: 0.90")

# ── Auto-refresh for live facial telemetry ─────────────────────
# Paused during agent calls and evaluation display
if (
    HAS_AUTOREFRESH
    and not st.session_state.get("_audio_processing", False)
    and "evaluation_result" not in st.session_state
):
    st_autorefresh(interval=2000, key="data_refresh")

