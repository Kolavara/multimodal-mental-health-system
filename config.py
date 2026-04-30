"""
config.py — Central configuration for the Multimodal Clinical AI Platform.

Loads environment variables via python-dotenv, defines all tunables as a
dataclass, and provides validation logic for Ollama, Redpanda, and VRAM.

This is a structural prototype. No real medical data is used.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class Config:
    # ── Groq (Primary LLM — Cloud) ──────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # ── Ollama (Vision Model Only — Local GPU) ─────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_VISION_MODEL: str = "llava:7b"
    OLLAMA_TIMEOUT: int = 120
    OLLAMA_KEEP_ALIVE: str = "5m"

    # ── Session ────────────────────────────────────────────────
    SESSION_ID: str = "session_001"
    PATIENT_ID: str = "patient_001"

    # ── Redpanda / Kafka ───────────────────────────────────────
    KAFKA_BROKER: str = "localhost:19092"
    TOPIC_FACIAL: str = "clinical.facial"
    TOPIC_SPEECH: str = "clinical.speech"
    TOPIC_AGENT: str = "clinical.agent"
    TOPIC_SEVERITY: str = "clinical.severity"
    KAFKA_GROUP_ID: str = "clinical-ai-consumer"

    # ── Severity & Routing Thresholds ──────────────────────────
    SEVERITY_ESCALATION_THRESHOLD: float = 0.75   # triggers Psychiatrist
    CRISIS_THRESHOLD: float = 0.90                 # triggers kill switch
    SEVERITY_WEIGHTS: dict = field(default_factory=lambda: {
        "facial_valence": 0.25,
        "vocal_valence": 0.25,
        "content_sentiment": 0.25,
        "behavioral_flags": 0.25,
    })

    # ── Video / Audio Capture ──────────────────────────────────
    VIDEO_FPS: int = 30
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHUNK_SIZE: int = 1024
    WEBRTC_STUN_SERVER: str = "stun:stun.l.google.com:19302"

    # ── Speech Engine (faster-whisper) ─────────────────────────
    WHISPER_MODEL_SIZE: str = "tiny.en"              # tiny/base/small
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # ── Facial Engine (MediaPipe) ──────────────────────────────
    FACE_DETECTION_CONFIDENCE: float = 0.7
    FACE_TRACKING_CONFIDENCE: float = 0.7
    TF_EMOTION_EVERY_N_FRAMES: int = 3             # run TF emotion classifier every Nth frame

    # ── TTS (edge-tts) ─────────────────────────────────────────
    TTS_VOICE: str = "en-US-AriaNeural"
    TTS_RATE: str = "+0%"
    TTS_VOLUME: str = "+0%"

    # ── EEG (mock / MNE-Python) ────────────────────────────────
    EEG_CHANNELS: int = 64
    EEG_SAMPLE_RATE: int = 256

    # ── Feature Fusion ─────────────────────────────────────────
    AFFECT_WINDOW_SECONDS: int = 30
    FEATURE_FUSION_DIM: int = 256
    SYNTHESIS_INTERVAL_SECONDS: int = 60

    # ── Safety ─────────────────────────────────────────────────
    CRISIS_CHECK_ENABLED: bool = True

    # ── Logging ────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


def get_config() -> Config:
    """Load configuration from environment variables with dataclass defaults."""
    load_dotenv()

    config = Config(
        # Groq (Primary)
        GROQ_API_KEY=os.getenv("GROQ_API_KEY", Config.GROQ_API_KEY),
        GROQ_MODEL=os.getenv("GROQ_MODEL", Config.GROQ_MODEL),
        # Ollama (Vision only)
        OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL", Config.OLLAMA_BASE_URL),
        OLLAMA_VISION_MODEL=os.getenv("OLLAMA_VISION_MODEL", Config.OLLAMA_VISION_MODEL),
        OLLAMA_TIMEOUT=int(os.getenv("OLLAMA_TIMEOUT", Config.OLLAMA_TIMEOUT)),
        OLLAMA_KEEP_ALIVE=os.getenv("OLLAMA_KEEP_ALIVE", Config.OLLAMA_KEEP_ALIVE),
        # Session
        SESSION_ID=os.getenv("SESSION_ID", Config.SESSION_ID),
        PATIENT_ID=os.getenv("PATIENT_ID", Config.PATIENT_ID),
        # Redpanda
        KAFKA_BROKER=os.getenv("KAFKA_BROKER", Config.KAFKA_BROKER),
        TOPIC_FACIAL=os.getenv("TOPIC_FACIAL", Config.TOPIC_FACIAL),
        TOPIC_SPEECH=os.getenv("TOPIC_SPEECH", Config.TOPIC_SPEECH),
        TOPIC_AGENT=os.getenv("TOPIC_AGENT", Config.TOPIC_AGENT),
        TOPIC_SEVERITY=os.getenv("TOPIC_SEVERITY", Config.TOPIC_SEVERITY),
        KAFKA_GROUP_ID=os.getenv("KAFKA_GROUP_ID", Config.KAFKA_GROUP_ID),
        # Thresholds
        SEVERITY_ESCALATION_THRESHOLD=float(os.getenv("SEVERITY_ESCALATION_THRESHOLD", Config.SEVERITY_ESCALATION_THRESHOLD)),
        CRISIS_THRESHOLD=float(os.getenv("CRISIS_THRESHOLD", Config.CRISIS_THRESHOLD)),
        # Video/Audio
        VIDEO_FPS=int(os.getenv("VIDEO_FPS", Config.VIDEO_FPS)),
        AUDIO_SAMPLE_RATE=int(os.getenv("AUDIO_SAMPLE_RATE", Config.AUDIO_SAMPLE_RATE)),
        AUDIO_CHUNK_SIZE=int(os.getenv("AUDIO_CHUNK_SIZE", Config.AUDIO_CHUNK_SIZE)),
        WEBRTC_STUN_SERVER=os.getenv("WEBRTC_STUN_SERVER", Config.WEBRTC_STUN_SERVER),
        # Whisper
        WHISPER_MODEL_SIZE=os.getenv("WHISPER_MODEL_SIZE", Config.WHISPER_MODEL_SIZE),
        WHISPER_DEVICE=os.getenv("WHISPER_DEVICE", Config.WHISPER_DEVICE),
        WHISPER_COMPUTE_TYPE=os.getenv("WHISPER_COMPUTE_TYPE", Config.WHISPER_COMPUTE_TYPE),
        # Facial
        FACE_DETECTION_CONFIDENCE=float(os.getenv("FACE_DETECTION_CONFIDENCE", Config.FACE_DETECTION_CONFIDENCE)),
        FACE_TRACKING_CONFIDENCE=float(os.getenv("FACE_TRACKING_CONFIDENCE", Config.FACE_TRACKING_CONFIDENCE)),
        TF_EMOTION_EVERY_N_FRAMES=int(os.getenv("TF_EMOTION_EVERY_N_FRAMES", Config.TF_EMOTION_EVERY_N_FRAMES)),
        # TTS
        TTS_VOICE=os.getenv("TTS_VOICE", Config.TTS_VOICE),
        TTS_RATE=os.getenv("TTS_RATE", Config.TTS_RATE),
        TTS_VOLUME=os.getenv("TTS_VOLUME", Config.TTS_VOLUME),
        # EEG
        EEG_CHANNELS=int(os.getenv("EEG_CHANNELS", Config.EEG_CHANNELS)),
        EEG_SAMPLE_RATE=int(os.getenv("EEG_SAMPLE_RATE", Config.EEG_SAMPLE_RATE)),
        # Fusion
        AFFECT_WINDOW_SECONDS=int(os.getenv("AFFECT_WINDOW_SECONDS", Config.AFFECT_WINDOW_SECONDS)),
        FEATURE_FUSION_DIM=int(os.getenv("FEATURE_FUSION_DIM", Config.FEATURE_FUSION_DIM)),
        SYNTHESIS_INTERVAL_SECONDS=int(os.getenv("SYNTHESIS_INTERVAL_SECONDS", Config.SYNTHESIS_INTERVAL_SECONDS)),
        # Safety
        CRISIS_CHECK_ENABLED=str(os.getenv("CRISIS_CHECK_ENABLED", Config.CRISIS_CHECK_ENABLED)).lower() in ("true", "1", "yes", "t"),
        # Logging
        LOG_LEVEL=os.getenv("LOG_LEVEL", Config.LOG_LEVEL),
    )

    print("OK Config loaded successfully")
    return config


def validate_config(config: Config) -> bool:
    """Validate critical configuration values. Raises on failure."""
    errors = []

    # Groq API key must be set
    if not config.GROQ_API_KEY:
        errors.append("GROQ_API_KEY must not be empty.")

    # Severity thresholds must be sane
    if not (0.0 < config.SEVERITY_ESCALATION_THRESHOLD < config.CRISIS_THRESHOLD <= 1.0):
        errors.append(
            f"Threshold ordering violated: escalation={config.SEVERITY_ESCALATION_THRESHOLD}, "
            f"crisis={config.CRISIS_THRESHOLD}. Must be 0 < escalation < crisis <= 1."
        )

    # Kafka broker format
    if ":" not in config.KAFKA_BROKER:
        errors.append(f"KAFKA_BROKER '{config.KAFKA_BROKER}' missing port")

    if errors:
        for e in errors:
            print(f"  ERR {e}")
        raise ValueError(f"Config validation failed with {len(errors)} error(s)")

    print("OK Config validated successfully")
    return True


if __name__ == "__main__":
    cfg = get_config()
    try:
        validate_config(cfg)
        print(f"\n  Groq Model:       {cfg.GROQ_MODEL}")
        print(f"  Ollama Vision:   {cfg.OLLAMA_VISION_MODEL}")
        print(f"  Kafka Broker:    {cfg.KAFKA_BROKER}")
        print(f"  Whisper Model:   {cfg.WHISPER_MODEL_SIZE} ({cfg.WHISPER_DEVICE})")
        print(f"  TTS Voice:       {cfg.TTS_VOICE}")
        print(f"  Escalation @:    {cfg.SEVERITY_ESCALATION_THRESHOLD}")
        print(f"  Crisis @:        {cfg.CRISIS_THRESHOLD}")
    except ValueError as e:
        print(f"\n⚠ {e}")
