"""
server.py — FastAPI backend for Multimodal Clinical AI Platform.
Replaces Streamlit with REST + WebSocket endpoints.
All ML engines, agents, and DB remain untouched.
"""

import os, sys, time, json, uuid, base64, asyncio, logging, re
import threading
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

import cv2
import numpy as np
import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, UploadFile, File, Form, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── App engine imports (unchanged) ────────────────────────────
from utils.db import (
    init_db, authenticate, create_user,
    save_report, get_reports_for_user,
    get_all_users, get_user_report_count, get_user_latest_report,
    update_report_integrated, update_report_psychiatrist, update_report_severity, get_latest_report_id,
)
from config import get_config

CFG = get_config()
init_db()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "clinical-ai-secret-key-change-me")
JWT_ALGORITHM = "HS256"

# ══════════════════════════════════════════════════════════════
# SERVER-LEVEL MODEL PRE-LOADING (runs once at startup)
# ══════════════════════════════════════════════════════════════

_preloaded = False
_cached_graph = None

def _preload_models():
    """Pre-load all heavy ML models at server startup so sessions start instantly."""
    global _preloaded, _cached_graph
    if _preloaded:
        return
    logger.info("⏳ Pre-loading ML models at server startup...")
    t0 = time.time()

    # 1. Emotion classifier (TensorFlow Keras model)
    try:
        from engines.facial.emotion_classifier import get_emotion_classifier
        get_emotion_classifier()
        logger.info("  ✅ Emotion classifier loaded")
    except Exception as e:
        logger.warning(f"  ⚠️ Emotion classifier pre-load failed: {e}")

    # 2. Whisper model (faster-whisper)
    try:
        from engines.speech.speech_engine import _get_cached_whisper_model
        _get_cached_whisper_model()
        logger.info("  ✅ Whisper model loaded")
    except Exception as e:
        logger.warning(f"  ⚠️ Whisper pre-load failed: {e}")

    # 3. Clinical agent graph (LangGraph compilation)
    try:
        from agents.graph import build_clinical_graph
        _cached_graph = build_clinical_graph()
        logger.info("  ✅ Clinical graph compiled")
    except Exception as e:
        logger.warning(f"  ⚠️ Graph pre-load failed: {e}")

    elapsed = time.time() - t0
    logger.info(f"🚀 All models pre-loaded in {elapsed:.1f}s — sessions will start fast!")
    _preloaded = True

# Run preload in a background thread so server starts serving immediately
threading.Thread(target=_preload_models, daemon=True).start()


# ══════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════

class Session:
    """Holds per-user engine instances."""
    def __init__(self, user: dict):
        self.user = user
        self.session_start = time.time()
        self.patient_id = f"patient_{user['id']}"
        self.session_id = f"session_{int(time.time())}"
        self.initialized = False
        self.facial_engine = None
        self.speech_engine = None
        self.fusion_engine = None
        self.tts_engine = None
        self.agent_workflow = None
        self.clinical_state = None
        self._lock = threading.Lock()

    def initialize(self):
        """Heavy init — run in a thread. Uses pre-loaded models where possible."""
        global _cached_graph
        from concurrent.futures import ThreadPoolExecutor
        from engines.facial.facial_engine import FacialAnalysisEngine
        from engines.speech.speech_engine import SpeechAnalysisEngine
        from utils.feature_fusion import FeatureFusionEngine
        from engines.tts.tts_engine import TTSEngine
        from utils.safety_engine import safety_monitor

        pid, sid = self.patient_id, self.session_id

        # Engines still need per-session state, but models inside are now cached singletons
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(FacialAnalysisEngine, pid, sid)
            f2 = pool.submit(SpeechAnalysisEngine, pid, sid)
            self.facial_engine = f1.result()
            self.speech_engine = f2.result()

        # Reuse pre-compiled graph or build fresh
        if _cached_graph is not None:
            self.agent_workflow = _cached_graph
        else:
            from agents.graph import build_clinical_graph
            self.agent_workflow = build_clinical_graph()

        self.speech_engine.start_processing_thread()
        self.speech_engine.warmup()  # Near-instant since model is already cached
        self.fusion_engine = FeatureFusionEngine()
        self.tts_engine = TTSEngine()
        self.tts_engine.start()
        safety_monitor.reset()

        from langchain_core.messages import AIMessage
        greeting = "Hello. I'm the clinical AI assistant. How are you feeling today? Please tell me a bit about what's been on your mind."
        self.tts_engine.speak(greeting)

        from utils.db import get_reports_for_user as _gru
        reports = _gru(self.user["id"])
        prev_history = ""
        if reports:
            recent = sorted(reports, key=lambda r: r.get("id", 0), reverse=True)[:3]
            history_blocks = []
            for r in reversed(recent):
                date_str = r.get("timestamp", "").replace("T", " ")[:16]
                conclusion = r.get("psychologist_conclusion", "No session notes.")
                integration = r.get("integrated_summary", "No clinical summary.")
                history_blocks.append(f"### Session on {date_str}\n**Session Notes:** {conclusion}\n**Clinical Diagnosis:** {integration}")
            
            if history_blocks:
                prev_history = "\n\n".join(history_blocks)

        self.clinical_state = {
            "messages": [AIMessage(content=greeting)],
            "patient_id": pid,
            "session_id": sid,
            "current_severity": 0.0,
            "facial_features": {},
            "speech_features": {},
            "current_agent": "psychologist",
            "escalation_reason": "",
            "clinical_summary": "",
            "previous_history": prev_history,
        }
        self.initialized = True


sessions: dict[str, Session] = {}  # token -> Session



# ══════════════════════════════════════════════════════════════
# FASTAPI APP
# ══════════════════════════════════════════════════════════════

app = FastAPI(title="Clinical AI Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# ── Auth helpers ──────────────────────────────────────────────

def create_token(user: dict) -> str:
    payload = {"user_id": user["id"], "username": user["username"], "role": user["role"],
               "display_name": user["display_name"], "exp": time.time() + 86400}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

def get_current_user(authorization: str = Header(default="")) -> dict:
    if not authorization:
        raise HTTPException(401, "Missing token")
    tok = authorization.replace("Bearer ", "")
    return decode_token(tok)


# ══════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user)
    # Create session
    sessions[token] = Session(user)
    return {"token": token, "user": {k: user[k] for k in ("id", "username", "display_name", "role")}}

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    if len(req.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    ok = create_user(req.username, req.password, req.display_name, "user")
    if not ok:
        raise HTTPException(409, f"Username '{req.username}' already exists")
    return {"message": f"Account created for {req.display_name}"}


# ══════════════════════════════════════════════════════════════
# REPORTS ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.get("/api/reports")
async def get_reports(user: dict = Depends(get_current_user)):
    return get_reports_for_user(user["user_id"])

@app.get("/api/admin/users")
async def admin_users(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    users = get_all_users(role="user")
    result = []
    for u in users:
        rc = get_user_report_count(u["id"])
        latest = get_user_latest_report(u["id"])
        result.append({**u, "report_count": rc, "latest_report": latest})
    return result

@app.get("/api/admin/user/{user_id}/reports")
async def admin_user_reports(user_id: int, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return get_reports_for_user(user_id)


# ══════════════════════════════════════════════════════════════
# PSYCHIATRIST ENDPOINTS
# ══════════════════════════════════════════════════════════════

NORMAL_RANGES = {
    "Cortisol_AM": (5.0, 25.0), "TSH": (0.4, 4.0), "PHQ-9": (0, 4),
    "GAD-7": (0, 4), "MADRS": (0, 6), "YMRS": (0, 12),
    "PANSS": (30, 60), "PCL-5": (0, 30), "CAGE-AID": (0, 0),
}
DISORDER_MAPPING = {
    "Cortisol_AM": "Stress-Stressor Related Disorders (PTSD, Acute Stress) or Severe Mood Disorders.",
    "TSH": "If abnormal, can mimic Mood Disorders (Depression/Bipolar) or Anxiety Disorders.",
    "PHQ-9": "Major Depressive Disorder (MDD), Persistent Depressive Disorder (Dysthymia), or Bipolar.",
    "GAD-7": "Generalized Anxiety Disorder (GAD), Panic Disorder, or Social Anxiety Disorder.",
    "MADRS": "Major Depressive Disorder (MDD).",
    "YMRS": "Bipolar I & II (Manic, Hypomanic, or Cyclothymic cycling).",
    "PANSS": "Schizophrenia, Schizoaffective Disorder, or Brief Psychotic Disorder.",
    "PCL-5": "PTSD or Complex PTSD (C-PTSD).",
    "CAGE-AID": "Alcohol/Drug Use Disorder.",
}
SOLUTIONS = {
    "Cortisol_AM": "Consult an endocrinologist. Implement stress-reduction techniques.",
    "TSH": "Consult a physician for a full thyroid panel (T3, T4).",
    "PHQ-9": "Consider psychotherapy (CBT) and psychiatric evaluation for SSRI/SNRI therapy.",
    "GAD-7": "Engage in exposure therapy, CBT, and consider anxiolytic medications.",
    "MADRS": "Intensive psychiatric evaluation for mood stabilizers or antidepressants.",
    "YMRS": "Immediate psychiatric consult; consider mood stabilizers (e.g., Lithium).",
    "PANSS": "Urgent psychiatric intervention. Antipsychotic medication recommended.",
    "PCL-5": "Trauma-focused therapy (EMDR, TF-CBT). Assess dissociative symptoms.",
    "CAGE-AID": "Referral to substance abuse counseling, detoxification programs.",
}

def analyze_params(patient_data: dict):
    abnormal, normal = [], []
    for param, value in patient_data.items():
        if param not in NORMAL_RANGES:
            continue
        min_v, max_v = NORMAL_RANGES[param]
        entry = {"param": param, "value": value, "min": min_v, "max": max_v,
                 "disorder": DISORDER_MAPPING.get(param, "Unknown"),
                 "solution": SOLUTIONS.get(param, "Consult a specialist.")}
        if value < min_v or value > max_v:
            abnormal.append(entry)
        else:
            normal.append(entry)
    return abnormal, normal

@app.post("/api/psychiatrist/analyze-pdf")
async def analyze_pdf(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    import PyPDF2, io
    content = await file.read()
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    text = ""
    for page in reader.pages:
        pt = page.extract_text()
        if pt:
            text += pt + "\n"
    extracted = {}
    for param in NORMAL_RANGES:
        match = re.search(rf"{param}\s*[:\-]?\s*(\d+(\.\d+)?)", text, re.IGNORECASE)
        if match:
            extracted[param] = float(match.group(1))
    if not extracted:
        return {"error": "No recognizable parameters found"}
    abnormal, normal = analyze_params(extracted)
    return {"params": extracted, "abnormal": abnormal, "normal": normal}

@app.post("/api/psychiatrist/analyze-manual")
async def analyze_manual(data: dict, user: dict = Depends(get_current_user)):
    abnormal, normal = analyze_params(data)
    return {"params": data, "abnormal": abnormal, "normal": normal}

@app.post("/api/psychiatrist/integrate")
async def integrate_diagnosis(data: dict, user: dict = Depends(get_current_user)):
    psychologist_text = data.get("psychologist_text", "No psychologist session data.")
    psychiatrist_text = data.get("psychiatrist_text", "No psychiatric lab data.")
    has_psych = data.get("has_psychological", False)
    has_psychiatric = data.get("has_psychiatric", False)

    from langchain_groq import ChatGroq
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatGroq(api_key=CFG.GROQ_API_KEY, model_name=CFG.GROQ_MODEL, temperature=0.2)

    if has_psych and has_psychiatric:
        sys = ("You are a senior clinical psychiatrist reviewing two reports:\n"
               "1. PSYCHOLOGIST SESSION REPORT\n2. PSYCHIATRIST LAB/SCALE REPORT\n\n"
               "Cross-reference, identify diagnoses, explain corroboration, provide treatment plan.\n"
               "Structure: Integrated Diagnosis, Corroborating Evidence, Recommended Treatment Plan.")
    elif has_psych:
        sys = ("You are a senior clinical psychiatrist reviewing a PSYCHOLOGIST SESSION REPORT.\n"
               "Identify diagnoses, note red flags, provide next steps.\n"
               "Structure: Preliminary Diagnosis, Key Observations, Recommended Next Steps, Suggested Lab Tests.")
    else:
        sys = ("You are a senior clinical psychiatrist reviewing a PSYCHIATRIST LAB/SCALE REPORT.\n"
               "Identify diagnoses, provide treatment plan.\n"
               "Structure: Preliminary Diagnosis, Lab Findings Analysis, Recommended Treatment Plan.")

    prompt = f"=== PSYCHOLOGIST ===\n{psychologist_text}\n\n=== PSYCHIATRIST ===\n{psychiatrist_text}\n\nProvide diagnosis."
    response = await asyncio.to_thread(llm.invoke, [SystemMessage(content=sys), HumanMessage(content=prompt)])

    # Save to DB
    abnormal = data.get("abnormal", [])
    normal_list = data.get("normal", [])
    params_dict = data.get("params", {})
    report_id = data.get("report_id")
    psych_severity = data.get("psych_severity", 0.0)

    total = len(abnormal) + len(normal_list)
    psych_sev = len(abnormal) / total if total > 0 else 0.0
    if has_psych and has_psychiatric:
        blended = (psych_severity * 0.5) + (psych_sev * 0.5)
    elif has_psych:
        blended = psych_severity
    else:
        blended = psych_sev
    blended = min(1.0, max(0.0, blended))

    try:
        if report_id:
            if has_psychiatric:
                update_report_psychiatrist(report_id, params_dict,
                    [{"param": e["param"], "value": e["value"], "disorder": e["disorder"], "solution": e["solution"]} for e in abnormal])
            update_report_integrated(report_id, response.content)
            update_report_severity(report_id, blended)
        else:
            eval_data = data.get("evaluation", {})
            report_id = save_report(
                user_id=user["user_id"],
                psychologist_facial=eval_data.get("facial", ""),
                psychologist_speech=eval_data.get("speech", ""),
                psychologist_conversation=eval_data.get("conversation", ""),
                psychologist_conclusion=eval_data.get("conclusion", ""),
                psychiatrist_params=params_dict,
                psychiatrist_abnormalities=[{"param": e["param"], "value": e["value"], "disorder": e["disorder"], "solution": e["solution"]} for e in abnormal],
                integrated_summary=response.content,
                avg_severity=blended,
            )
    except Exception as e:
        logger.warning(f"DB save: {e}")

    return {"summary": response.content, "report_id": report_id, "blended_severity": blended}


# ══════════════════════════════════════════════════════════════
# WEBSOCKET — SESSION (video + chat + telemetry)
# ══════════════════════════════════════════════════════════════

@app.websocket("/ws/session")
async def ws_session(ws: WebSocket, token: str = ""):
    await ws.accept()

    try:
        payload = decode_token(token)
    except Exception:
        await ws.send_json({"type": "error", "message": "Invalid token"})
        await ws.close()
        return

    session = sessions.get(token)
    if not session:
        session = Session({"id": payload["user_id"], "username": payload["username"],
                           "display_name": payload["display_name"], "role": payload["role"]})
        sessions[token] = session

    # Init engines in background
    if not session.initialized:
        await ws.send_json({"type": "status", "message": "Initializing engines..."})
        try:
            await asyncio.to_thread(session.initialize)
            await ws.send_json({"type": "init_complete"})

            # Send initial greeting
            greeting = session.clinical_state["messages"][0].content
            await ws.send_json({"type": "chat_response", "message": greeting, "agent": "psychologist"})
        except Exception as e:
            await ws.send_json({"type": "error", "message": f"Init failed: {e}"})
            await ws.close()
            return
    else:
        # Session already initialized (reconnection) — resend greeting + TTS
        await ws.send_json({"type": "init_complete"})
        greeting = session.clinical_state["messages"][0].content
        await ws.send_json({"type": "chat_response", "message": greeting, "agent": "psychologist"})
        if session.tts_engine:
            session.tts_engine.speak(greeting)

    # Telemetry push task
    async def push_telemetry():
        while True:
            try:
                await asyncio.sleep(0.5)
                if not session.initialized or not session.fusion_engine:
                    continue
                session.fusion_engine.update_speech(session.speech_engine.latest_speech_data)
                state = session.fusion_engine.get_state()
                severity = state.get("severity_score", 0.0)
                avg_sev = state.get("average_severity_score", 0.0)
                disorder = state.get("likely_disorder", "Unknown")
                facial = state.get("facial", {})

                from utils.safety_engine import safety_monitor
                halted = safety_monitor.evaluate_state(state)

                await ws.send_json({
                    "type": "telemetry",
                    "severity": severity, "avg_severity": avg_sev,
                    "disorder": disorder, "facial": facial,
                    "agent": session.clinical_state.get("current_agent", "psychologist"),
                    "elapsed": time.time() - session.session_start,
                    "halted": halted,
                    "halt_reason": safety_monitor.halt_reason if halted else "",
                })
            except (WebSocketDisconnect, RuntimeError):
                break
            except Exception as e:
                logger.debug(f"Telemetry error: {e}")

    telemetry_task = asyncio.create_task(push_telemetry())

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "frame":
                # Decode and process video frame
                try:
                    img_bytes = base64.b64decode(msg["data"])
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None and session.facial_engine:
                        result = await asyncio.to_thread(session.facial_engine.process_frame_sync, frame)
                        session.fusion_engine.update_facial(result)
                        await ws.send_json({"type": "facial", **result})
                except Exception as e:
                    logger.debug(f"Frame error: {e}")

            elif msg_type == "chat":
                # Process chat message through agent
                try:
                    from langchain_core.messages import HumanMessage
                    user_msg = msg["message"]

                    if hasattr(session, "speech_engine") and session.speech_engine:
                        session.speech_engine._classify_text_async(user_msg)

                    if session.fusion_engine:
                        session.fusion_engine.record_chat_snapshot()

                    state = session.clinical_state
                    state["speech_features"] = session.speech_engine.latest_speech_data if session.speech_engine else {}
                    live = session.fusion_engine.get_state() if session.fusion_engine else {}
                    state["current_severity"] = live.get("severity_score", 0.0)
                    state["average_severity_score"] = live.get("average_severity_score", 0.0)
                    state["likely_disorder"] = live.get("likely_disorder", "Unknown")

                    state["messages"].append(HumanMessage(content=user_msg))

                    if session.tts_engine:
                        session.tts_engine.stop_current_speech()

                    new_state = await asyncio.to_thread(session.agent_workflow.invoke, state)
                    for k, v in new_state.items():
                        state[k] = v

                    ai_msg = state["messages"][-1]
                    if ai_msg.type == "ai":
                        if session.tts_engine:
                            session.tts_engine.speak(ai_msg.content)
                        await ws.send_json({
                            "type": "chat_response",
                            "message": ai_msg.content,
                            "agent": state.get("current_agent", "psychologist"),
                        })
                except Exception as e:
                    logger.error(f"Chat error: {e}", exc_info=True)
                    await ws.send_json({"type": "error", "message": f"Agent error: {e}"})

            elif msg_type == "voice":
                # Process voice recording: decode → prosody analysis → transcribe → AI agent
                try:
                    from langchain_core.messages import HumanMessage
                    audio_b64 = msg.get("data", "")
                    audio_bytes = base64.b64decode(audio_b64)
                    logger.info(f"[VOICE] Received {len(audio_bytes)} bytes of audio")

                    # Run prosody extraction + Whisper transcription in thread
                    voice_result = await asyncio.to_thread(
                        session.speech_engine.process_browser_audio, audio_bytes
                    )

                    transcript = voice_result.get("transcript", "").strip()
                    prosody = voice_result.get("prosody", {})
                    speech_distress = voice_result.get("speech_distress", 0.0)

                    if not transcript:
                        await ws.send_json({
                            "type": "voice_result",
                            "transcript": "",
                            "prosody": prosody,
                            "speech_distress": speech_distress,
                            "error": "Could not transcribe audio. Please try again."
                        })
                        continue

                    # Send transcription result back to client immediately
                    await ws.send_json({
                        "type": "voice_result",
                        "transcript": transcript,
                        "prosody": prosody,
                        "speech_distress": speech_distress,
                    })

                    # Update fusion engine with speech data (has_prosody=True triggers tri-modal)
                    if session.fusion_engine:
                        session.fusion_engine.update_speech(session.speech_engine.latest_speech_data)
                        session.fusion_engine.record_chat_snapshot()

                    # Forward transcript through the AI agent (same as chat)
                    state = session.clinical_state
                    state["speech_features"] = session.speech_engine.latest_speech_data
                    live = session.fusion_engine.get_state() if session.fusion_engine else {}
                    state["current_severity"] = live.get("severity_score", 0.0)
                    state["average_severity_score"] = live.get("average_severity_score", 0.0)
                    state["likely_disorder"] = live.get("likely_disorder", "Unknown")

                    state["messages"].append(HumanMessage(content=transcript))

                    if session.tts_engine:
                        session.tts_engine.stop_current_speech()

                    new_state = await asyncio.to_thread(session.agent_workflow.invoke, state)
                    for k, v in new_state.items():
                        state[k] = v

                    ai_msg = state["messages"][-1]
                    if ai_msg.type == "ai":
                        if session.tts_engine:
                            session.tts_engine.speak(ai_msg.content)
                        await ws.send_json({
                            "type": "chat_response",
                            "message": ai_msg.content,
                            "agent": state.get("current_agent", "psychologist"),
                        })
                except Exception as e:
                    logger.error(f"Voice error: {e}", exc_info=True)
                    await ws.send_json({"type": "error", "message": f"Voice processing error: {e}"})

            elif msg_type == "end_session":
                try:
                    from langchain_core.messages import HumanMessage
                    from langchain_groq import ChatGroq
                    from langchain_core.messages import SystemMessage as SysMsg

                    if session.tts_engine:
                        session.tts_engine.stop_current_speech()

                    live = session.fusion_engine.get_state() if session.fusion_engine else {}
                    avg_sev = live.get("average_severity_score", 0.0)
                    disorder = live.get("likely_disorder", "Unknown")

                    eval_prompt = (
                        f"SYSTEM: The session has ended. Provide a concise clinical statement. "
                        f"Average disorder risk: {avg_sev:.1%}, likely disorder: {disorder}."
                    )
                    session.clinical_state["messages"].append(HumanMessage(content=eval_prompt))
                    final = await asyncio.to_thread(session.agent_workflow.invoke, session.clinical_state)
                    session.clinical_state = final

                    conclusion = final["messages"][-1].content
                    facial_summary = session.facial_engine.get_clinical_summary() if session.facial_engine else ""
                    convo_summary = session.speech_engine.get_clinical_summary() if session.speech_engine else ""
                    speech_summary = session.speech_engine.get_prosody_summary() if session.speech_engine else ""

                    # ── Generate multimodal clinical analysis ──
                    session_summary = ""
                    try:
                        summary_llm = ChatGroq(api_key=CFG.GROQ_API_KEY, model_name=CFG.GROQ_MODEL, temperature=0.3)
                        summary_sys = (
                            "You are a senior clinical psychologist. You have just finished a patient session where "
                            "THREE independent analysis modalities were running simultaneously:\n"
                            "1. FACIAL analysis (emotion, microexpressions, eye contact, affect)\n"
                            "2. SPEECH/PROSODY analysis (pitch, jitter, pauses, vocal distress)\n"
                            "3. CONVERSATION analysis (content distress, linguistic markers)\n\n"
                            "Cross-reference all three modalities and produce a structured clinical analysis with these sections:\n\n"
                            "**Multimodal Diagnosis:** State the most likely disorder(s) based on converging evidence "
                            "from all three modalities. Explain which signals from each modality corroborate the diagnosis.\n\n"
                            "**Key Evidence:** Highlight the 2-3 most clinically significant findings across all modalities "
                            "(e.g., 'flat vocal affect combined with persistent sadness in conversation content and reduced eye contact').\n\n"
                            "**Risk Assessment:** State the severity level and any immediate safety concerns.\n\n"
                            "**Recommended Next Steps:** Provide 3-4 concrete, actionable recommendations "
                            "(e.g., referral type, suggested assessments, therapeutic approaches, safety planning if needed).\n\n"
                            "Write in professional clinical language. Use markdown bold (**text**) for section headers. "
                            "Keep the total response under 250 words."
                        )
                        summary_input = (
                            f"=== FACIAL ANALYSIS ===\n{facial_summary}\n\n"
                            f"=== SPEECH/PROSODY ANALYSIS ===\n{speech_summary}\n\n"
                            f"=== CONVERSATION ANALYSIS ===\n{convo_summary}\n\n"
                            f"=== AI AGENT SESSION NOTES ===\n{conclusion}\n\n"
                            f"=== COMPUTED METRICS ===\n"
                            f"Tri-modal severity score: {avg_sev:.1%}\n"
                            f"Predicted disorder (algorithmic): {disorder}"
                        )
                        summary_resp = await asyncio.to_thread(
                            summary_llm.invoke,
                            [SysMsg(content=summary_sys), HumanMessage(content=summary_input)]
                        )
                        session_summary = summary_resp.content
                    except Exception as e:
                        logger.warning(f"Session summary generation failed (non-critical): {e}")
                        session_summary = (
                            f"**Multimodal Diagnosis:** {disorder} (severity {avg_sev:.1%}).\n\n"
                            f"**Key Evidence:** Facial — {facial_summary[:80]}... "
                            f"Speech — {speech_summary[:80]}... "
                            f"Conversation — {convo_summary[:80]}...\n\n"
                            f"**Recommended Next Steps:** Further clinical evaluation recommended."
                        )

                    report_id = None
                    try:
                        from utils.db import save_report
                        report_id = save_report(
                            user_id=session.user["id"],
                            psychologist_facial=facial_summary,
                            psychologist_speech=speech_summary,
                            psychologist_conversation=convo_summary,
                            psychologist_conclusion=conclusion,
                            integrated_summary=session_summary,
                            avg_severity=avg_sev,
                            likely_disorder=disorder,
                        )
                    except Exception as e:
                        logger.warning(f"Report save: {e}")

                    await ws.send_json({
                        "type": "evaluation",
                        "facial": facial_summary,
                        "speech": speech_summary,
                        "conversation": convo_summary,
                        "conclusion": conclusion,
                        "session_summary": session_summary,
                        "report_id": report_id,
                        "avg_severity": avg_sev,
                        "disorder": disorder,
                    })
                except Exception as e:
                    await ws.send_json({"type": "error", "message": f"Evaluation error: {e}"})

            elif msg_type == "halt":
                from utils.safety_engine import safety_monitor
                if session.tts_engine:
                    session.tts_engine.stop_current_speech()
                safety_monitor.manual_override()
                await ws.send_json({"type": "halted", "reason": "Manual Clinician Override."})

            elif msg_type == "reset":
                from utils.safety_engine import safety_monitor
                safety_monitor.reset()

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: {payload.get('username')}")
    except Exception as e:
        logger.error(f"WS error: {e}")
    finally:
        telemetry_task.cancel()


# ══════════════════════════════════════════════════════════════
# STATIC FILES + CATCH-ALL
# ══════════════════════════════════════════════════════════════

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
