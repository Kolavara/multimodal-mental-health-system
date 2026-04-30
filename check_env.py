"""
check_env.py — Pre-flight environment validator for the Clinical AI Platform.

Checks:
  1. Python version
  2. All critical imports resolve
  3. Ollama is running and target models are available
  4. GPU VRAM headroom via nvidia-smi
  5. Redpanda/Kafka broker connectivity (Docker)
  6. Config loads and validates

Run:  python check_env.py
"""

import sys
import os
import json
import subprocess
import urllib.request
import urllib.error

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── Formatting helpers ──────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{CYAN}── {msg} ──{RESET}")

errors = []


# ═══════════════════════════════════════════════════════════════
# 1. Python Version
# ═══════════════════════════════════════════════════════════════
header("Python Environment")
v = sys.version_info
if v.major == 3 and v.minor >= 10:
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
else:
    fail(f"Python {v.major}.{v.minor}.{v.micro} — need 3.10+")
    errors.append("Python version")


# ═══════════════════════════════════════════════════════════════
# 2. Critical Imports
# ═══════════════════════════════════════════════════════════════
header("Python Package Imports")

required_packages = {
    "streamlit":        "streamlit",
    "streamlit_webrtc": "streamlit-webrtc",
    "faster_whisper":   "faster-whisper",
    "mediapipe":        "mediapipe",
    "cv2":              "opencv-python-headless",
    "langchain_ollama": "langchain-ollama",
    "langgraph":        "langgraph",
    "edge_tts":         "edge-tts",
    "numpy":            "numpy",
    "dotenv":           "python-dotenv",
    "pydantic":         "pydantic",
}

optional_packages = {
    "confluent_kafka": "confluent-kafka",
    "mne":             "mne",
}

for module, pip_name in required_packages.items():
    try:
        __import__(module)
        ok(f"{pip_name}")
    except ImportError:
        fail(f"{pip_name} — run: pip install {pip_name}")
        errors.append(f"Missing: {pip_name}")

for module, pip_name in optional_packages.items():
    try:
        __import__(module)
        ok(f"{pip_name} (optional)")
    except ImportError:
        warn(f"{pip_name} not installed (optional) — pip install {pip_name}")


# ═══════════════════════════════════════════════════════════════
# 3. Ollama Status & Models
# ═══════════════════════════════════════════════════════════════
header("Ollama LLM Server")

ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
target_model = os.getenv("GROQ_MODEL", "llama3-8b-8192") # Not pulled locally
vision_model = os.getenv("OLLAMA_VISION_MODEL", "llava:7b")

try:
    resp = urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=5)
    data = json.loads(resp.read().decode())
    model_names = [m["name"] for m in data.get("models", [])]
    ok(f"Ollama running at {ollama_url}")
    ok(f"Models available: {', '.join(model_names) if model_names else '(none)'}")

    # Check for target models
    # Ollama model names can be "llama3:8b" or "llama3:latest" etc.
    def model_present(target, available):
        base = target.split(":")[0]
        for m in available:
            if m.startswith(base):
                return True
        return False

    if model_present(vision_model, model_names):
        ok(f"Vision model '{vision_model}' found")
    else:
        warn(f"Vision model '{vision_model}' not found — run: ollama pull {vision_model}")
        errors.append(f"Missing vision model: {vision_model}")

except urllib.error.URLError:
    fail(f"Ollama not reachable at {ollama_url} — is it running?")
    errors.append("Ollama not running")


# ═══════════════════════════════════════════════════════════════
# 4. GPU / VRAM Check
# ═══════════════════════════════════════════════════════════════
header("GPU & VRAM")

try:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 4:
                name, total, used, free = parts
                ok(f"{name}: {total} MB total, {used} MB used, {free} MB free")
                free_mb = int(free)
                if free_mb < 5000:
                    warn(f"Only {free_mb} MB free VRAM — Llama-3 8B needs ~5 GB")
                else:
                    ok(f"Sufficient VRAM headroom ({free_mb} MB free)")
    else:
        warn("nvidia-smi returned an error")
except FileNotFoundError:
    fail("nvidia-smi not found — NVIDIA drivers not installed?")
    errors.append("No GPU detected")


# ═══════════════════════════════════════════════════════════════
# 5. Redpanda / Kafka Broker
# ═══════════════════════════════════════════════════════════════
header("Redpanda Streaming Bus")

kafka_broker = os.getenv("KAFKA_BROKER", "localhost:19092")
try:
    import socket
    host, port = kafka_broker.rsplit(":", 1)
    sock = socket.create_connection((host, int(port)), timeout=3)
    sock.close()
    ok(f"Redpanda broker reachable at {kafka_broker}")
except Exception:
    warn(f"Redpanda broker not reachable at {kafka_broker}")
    warn("Start with: docker compose up -d  (from project root)")


# ═══════════════════════════════════════════════════════════════
# 6. Config Load & Validate
# ═══════════════════════════════════════════════════════════════
header("Configuration")

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import get_config, validate_config
    cfg = get_config()
    ok(f"Groq Model:      {cfg.GROQ_MODEL}")
    ok(f"Ollama Vision:   {cfg.OLLAMA_VISION_MODEL}")
    ok(f"Whisper Model:   {cfg.WHISPER_MODEL_SIZE} ({cfg.WHISPER_DEVICE})")
    ok(f"TTS Voice:       {cfg.TTS_VOICE}")
    ok(f"Escalation @:    {cfg.SEVERITY_ESCALATION_THRESHOLD}")
    ok(f"Crisis @:        {cfg.CRISIS_THRESHOLD}")
except Exception as e:
    fail(f"Config error: {e}")
    errors.append(f"Config: {e}")


# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
header("Summary")

if errors:
    print(f"\n  {RED}{BOLD}{len(errors)} issue(s) found:{RESET}")
    for e in errors:
        print(f"    • {e}")
    print(f"\n  Fix the above and re-run: python check_env.py\n")
    sys.exit(1)
else:
    print(f"\n  {GREEN}{BOLD}All checks passed! Ready to build.{RESET}\n")
    sys.exit(0)
