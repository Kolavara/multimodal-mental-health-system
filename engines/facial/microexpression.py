"""
microexpression.py — Microexpression Detection Engine

Detects rapid facial expression changes (< 500ms) that indicate
suppressed or involuntary emotional displays. Clinically relevant
for detecting concealed distress or incongruent affect.

Based on Ekman's research on micro-expressions:
- Duration: 1/25th to 1/5th of a second
- Often contradict the dominant expressed emotion
"""

import time
import numpy as np
from collections import deque
import logging

logger = logging.getLogger(__name__)

# Minimum AU change threshold to register as a significant movement
AU_CHANGE_THRESHOLD = 0.25
# Maximum duration (seconds) for a movement to qualify as microexpression
MICRO_MAX_DURATION = 0.5
# Minimum duration (seconds)
MICRO_MIN_DURATION = 0.04  # ~1 frame at 25fps

# Key AUs to monitor for microexpressions and their associated emotions
MICRO_AU_MAP = {
    "mouthSmileLeft": "happiness_leak",
    "mouthSmileRight": "happiness_leak",
    "mouthFrownLeft": "sadness_leak",
    "mouthFrownRight": "sadness_leak",
    "browDownLeft": "anger_leak",
    "browDownRight": "anger_leak",
    "eyeWideLeft": "fear_leak",
    "eyeWideRight": "fear_leak",
    "noseSneerLeft": "disgust_leak",
    "noseSneerRight": "disgust_leak",
    "browInnerUp": "distress_leak",
}


class MicroexpressionDetector:
    """
    Tracks rapid AU transitions across frames to detect microexpressions.
    
    A microexpression is detected when:
    1. An AU rapidly increases above threshold (onset)
    2. Then rapidly decreases back (offset)
    3. The total duration is < 500ms
    """
    
    def __init__(self, history_size: int = 60):
        # Store recent AU snapshots: (timestamp, {au_name: score})
        self.au_history = deque(maxlen=history_size)
        self.detected_events = deque(maxlen=100)
        
        # Track ongoing potential microexpressions
        # {au_name: {'onset_time': float, 'peak_value': float}}
        self._active_onsets = {}
        
        self._prev_scores = {}
    
    def update(self, blendshape_scores: dict, timestamp: float = None) -> list:
        """
        Process a new frame's blendshape scores and return any detected
        microexpression events.
        
        Args:
            blendshape_scores: dict of {au_name: float_score}
            timestamp: frame timestamp (defaults to time.time())
            
        Returns:
            List of detected microexpression event dicts
        """
        if timestamp is None:
            timestamp = time.time()
        
        self.au_history.append((timestamp, blendshape_scores.copy()))
        
        new_events = []
        
        for au_name, emotion_type in MICRO_AU_MAP.items():
            current_val = blendshape_scores.get(au_name, 0.0)
            prev_val = self._prev_scores.get(au_name, 0.0)
            delta = current_val - prev_val
            
            # Detect onset: rapid increase
            if delta > AU_CHANGE_THRESHOLD and au_name not in self._active_onsets:
                self._active_onsets[au_name] = {
                    'onset_time': timestamp,
                    'peak_value': current_val,
                }
            
            # Track peak
            elif au_name in self._active_onsets:
                active = self._active_onsets[au_name]
                if current_val > active['peak_value']:
                    active['peak_value'] = current_val
                
                # Detect offset: rapid decrease back to near-baseline
                if current_val < prev_val - AU_CHANGE_THRESHOLD * 0.5:
                    duration = timestamp - active['onset_time']
                    
                    if MICRO_MIN_DURATION <= duration <= MICRO_MAX_DURATION:
                        # Microexpression detected!
                        event = {
                            'timestamp': timestamp,
                            'type': emotion_type,
                            'action_unit': au_name,
                            'duration_ms': round(duration * 1000, 1),
                            'peak_intensity': round(active['peak_value'], 3),
                            'clinical_note': self._get_clinical_note(emotion_type),
                        }
                        new_events.append(event)
                        self.detected_events.append(event)
                        logger.info(
                            f"Microexpression detected: {emotion_type} "
                            f"(AU={au_name}, duration={duration*1000:.0f}ms, "
                            f"peak={active['peak_value']:.2f})"
                        )
                    
                    # Clear the onset tracking
                    del self._active_onsets[au_name]
                
                # Timeout: if onset is too old, discard it
                elif timestamp - active['onset_time'] > MICRO_MAX_DURATION * 1.5:
                    del self._active_onsets[au_name]
        
        self._prev_scores = blendshape_scores.copy()
        return new_events
    
    def _get_clinical_note(self, emotion_type: str) -> str:
        """Return a brief clinical interpretation of the microexpression type."""
        notes = {
            "happiness_leak": "Brief genuine smile suppression — possible concealed positive affect",
            "sadness_leak": "Fleeting sadness display — possible masked grief or despair",
            "anger_leak": "Brief anger flash — possible suppressed hostility or frustration",
            "fear_leak": "Rapid fear expression — possible concealed anxiety or threat response",
            "disgust_leak": "Brief disgust display — possible self-directed contempt or aversion",
            "distress_leak": "Fleeting brow raise — possible suppressed worry or concern",
        }
        return notes.get(emotion_type, "Unclassified microexpression detected")
    
    def get_recent_events(self, window_seconds: float = 60.0) -> list:
        """Get microexpression events detected in the last N seconds."""
        cutoff = time.time() - window_seconds
        return [e for e in self.detected_events if e['timestamp'] > cutoff]
    
    def get_summary(self) -> dict:
        """Get a summary of all detected microexpressions in the session."""
        events = list(self.detected_events)
        if not events:
            return {
                'total_count': 0,
                'types': {},
                'avg_duration_ms': 0,
                'clinical_significance': 'No microexpressions detected',
            }
        
        type_counts = {}
        durations = []
        for e in events:
            t = e['type']
            type_counts[t] = type_counts.get(t, 0) + 1
            durations.append(e['duration_ms'])
        
        # Clinical significance assessment
        total = len(events)
        negative_leaks = sum(
            type_counts.get(t, 0) 
            for t in ['sadness_leak', 'anger_leak', 'fear_leak', 'distress_leak']
        )
        
        if negative_leaks > 5:
            significance = "HIGH — Frequent negative affect suppression detected"
        elif negative_leaks > 2:
            significance = "MODERATE — Some negative affect suppression detected"
        elif total > 0:
            significance = "LOW — Occasional microexpressions, within normal range"
        else:
            significance = "NONE — No microexpressions detected"
        
        return {
            'total_count': total,
            'types': type_counts,
            'avg_duration_ms': round(np.mean(durations), 1) if durations else 0,
            'clinical_significance': significance,
        }
