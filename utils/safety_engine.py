import time
import logging

try:
    from config import get_config
    CFG = get_config()
except ImportError:
    class FallbackConfig:
        CRISIS_THRESHOLD = 0.9
    CFG = FallbackConfig()

class SafetyEngine:
    """
    Monitors the patient state for critical crisis markers.
    Triggers 'kill switch' (HALT) and alerts clinicians if criteria are met.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.crisis_keywords = ["suicide", "kill myself", "end it", "don't want to live"]
        self.is_halted = False
        self.halt_reason = ""

    def evaluate_state(self, state: dict) -> bool:
        """
        Evaluate the multimodal state vector. Returns True if a crisis is detected.
        """
        if self.is_halted:
            return True
            
        severity = state.get("severity_score", 0.0)
        speech_data = state.get("speech", {})
        
        # 1. Hard threshold override
        if severity >= CFG.CRISIS_THRESHOLD:
            self._trigger_halt(f"Severity ({severity:.2f}) exceeded crisis threshold ({CFG.CRISIS_THRESHOLD}).")
            return True
            
        # 2. Keyword detection in latest transcript
        transcript = speech_data.get("transcript", "").lower()
        for kw in self.crisis_keywords:
            if kw in transcript:
                self._trigger_halt(f"Crisis keyword detected: '{kw}'")
                return True
                
        # 3. Sudden extreme valence drop + high arousal
        f_valence = state.get("facial", {}).get("facial_valence", 0.0)
        s_arousal = speech_data.get("vocal_arousal", 0.0)
        
        if f_valence < -0.8 and s_arousal > 0.8:
            self._trigger_halt("Extreme distress profile detected (high arousal, negative valence).")
            return True

        return False

    def _trigger_halt(self, reason: str):
        self.is_halted = True
        self.halt_reason = reason
        self.logger.critical(f"CRISIS DETECTED - SYSTEM HALTED. Reason: {reason}")
        # In a real app, this would page a human operator via PagerDuty/Twilio

    def manual_override(self):
        self._trigger_halt("Manual Clinician Override.")

    def reset(self):
        self.is_halted = False
        self.halt_reason = ""
        self.logger.info("Safety Engine reset by clinician.")

# Singleton instance
safety_monitor = SafetyEngine()
