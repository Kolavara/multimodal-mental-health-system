"""
feature_fusion.py — Multimodal Feature Fusion Engine

Current Distress  → updates every refresh from facial valence (real-time).
Average Distress  → snapshot taken only when the user sends a chat message
                    (blends facial + text at that moment).
"""

import time
import logging

try:
    from config import get_config
    CFG = get_config()
except ImportError:
    class FallbackConfig:
        SEVERITY_ESCALATION_THRESHOLD = 0.7
    CFG = FallbackConfig()


class FeatureFusionEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.latest_facial = {}
        self.latest_speech = {}
        self.current_severity_score = 0.0   # Live, facial-driven
        self.severity_history = []           # Only appended on user chat
        self.disorder_prediction = "Unknown"
        self.patient_state_vector = {}

    def update_facial(self, facial_data: dict):
        self.latest_facial = facial_data
        self._recalculate()

    def update_speech(self, speech_data: dict):
        self.latest_speech = speech_data
        self._recalculate()

    def _recalculate(self):
        """Re-compute the CURRENT severity from facial data only.
        Average is NOT touched here — it is only updated via record_chat_snapshot().
        """
        if not self.latest_facial and not self.latest_speech:
            self.current_severity_score = 0.0
            self.patient_state_vector = {
                "timestamp": time.time(),
                "severity_score": 0.0,
                "average_severity_score": 0.0,
                "likely_disorder": "Unknown",
                "facial": {},
                "speech": {}
            }
            return

        # Current Distress = purely facial (real-time, no delay)
        fv = self.latest_facial.get('facial_valence', 0.0)
        facial_distress = max(0.0, min(1.0, -fv))
        self.current_severity_score = facial_distress

        # Capture disorder prediction from text classification if available
        disorder = self.latest_speech.get('likely_disorder')
        if disorder:
            self.disorder_prediction = disorder

        # Average from history (only updated on chat)
        avg_score = (
            sum(self.severity_history) / len(self.severity_history)
            if self.severity_history else 0.0
        )

        self.patient_state_vector = {
            "timestamp": time.time(),
            "severity_score": self.current_severity_score,
            "average_severity_score": avg_score,
            "likely_disorder": self.disorder_prediction,
            "facial": self.latest_facial,
            "speech": self.latest_speech
        }

    def record_chat_snapshot(self):
        """Called when user sends a chat message.
        Takes a blended snapshot of facial + text distress and appends to history.
        """
        fv = self.latest_facial.get('facial_valence', 0.0)
        facial_distress = max(0.0, min(1.0, -fv))
        content_distress = self.latest_speech.get('content_distress', 0.0)

        # 50/50 blend at the moment the user interacted
        blended = (facial_distress * 0.50) + (content_distress * 0.50)
        blended = min(1.0, max(0.0, blended))

        self.severity_history.append(blended)
        self.logger.info(
            f"Chat snapshot: facial={facial_distress:.2f}, "
            f"text={content_distress:.2f}, blended={blended:.2f}, "
            f"avg={sum(self.severity_history)/len(self.severity_history):.2f}"
        )
        # Refresh the state vector with the new average
        self._recalculate()

    def get_state(self) -> dict:
        return self.patient_state_vector

    def should_escalate(self) -> bool:
        if not self.severity_history:
            return False
        avg_score = sum(self.severity_history) / len(self.severity_history)
        return avg_score >= CFG.SEVERITY_ESCALATION_THRESHOLD


if __name__ == "__main__":
    fusion = FeatureFusionEngine()

    # Simulate neutral
    fusion.update_facial({'facial_valence': 0.2, 'face_detected': True})
    fusion.update_speech({'content_distress': 0.0})
    fusion.record_chat_snapshot()
    print(f"Neutral Severity: {fusion.current_severity_score:.2f}")

    # Simulate distress
    fusion.update_facial({'facial_valence': -0.8, 'face_detected': True})
    fusion.update_speech({'content_distress': 0.9})
    fusion.record_chat_snapshot()
    print(f"Distress Severity: {fusion.current_severity_score:.2f}")
    print(f"Avg: {fusion.get_state()['average_severity_score']:.2f}")
    print("Feature Fusion Test: PASS")
