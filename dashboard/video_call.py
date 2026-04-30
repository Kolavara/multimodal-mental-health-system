import cv2
import av
import streamlit as st
import numpy as np
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration

RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# Emotion → Color mapping for overlay
EMOTION_COLORS = {
    'happy': (16, 185, 129),     # emerald
    'sad': (99, 102, 241),       # indigo
    'angry': (239, 68, 68),      # red
    'fear': (168, 85, 247),      # purple
    'surprise': (245, 158, 11),  # amber
    'disgust': (234, 179, 8),    # yellow
    'neutral': (148, 163, 184),  # slate
    'unknown': (100, 100, 100),
}


def draw_rounded_rect(img, pt1, pt2, color, radius, thickness=-1):
    """Draw a rounded rectangle on an image."""
    x1, y1 = pt1
    x2, y2 = pt2
    r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    overlay = img.copy()
    # Draw filled rounded rectangle
    cv2.rectangle(overlay, (x1 + r, y1), (x2 - r, y2), color, thickness)
    cv2.rectangle(overlay, (x1, y1 + r), (x2, y2 - r), color, thickness)
    cv2.circle(overlay, (x1 + r, y1 + r), r, color, thickness)
    cv2.circle(overlay, (x2 - r, y1 + r), r, color, thickness)
    cv2.circle(overlay, (x1 + r, y2 - r), r, color, thickness)
    cv2.circle(overlay, (x2 - r, y2 - r), r, color, thickness)
    cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)


# AudioProcessor removed as audio is now handled by native st.audio_input


class VideoProcessor:
    def __init__(self, facial_engine, feature_fusion_engine):
        self.facial_engine = facial_engine
        self.feature_fusion_engine = feature_fusion_engine
        self.frame_counter = 0
        self.last_result = None

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]

        self.frame_counter += 1
        
        # Process every 6th frame to handle 60fps smoothly without melting the CPU (10 AI fps)
        if self.frame_counter % 6 == 1 or self.last_result is None:
            result = self.facial_engine.process_frame_sync(img)
            self.feature_fusion_engine.update_facial(result)
            self.last_result = result
        else:
            result = self.last_result

        severity = self.feature_fusion_engine.current_severity_score
        emotion = result.get('dominant_emotion', 'neutral')
        valence = result.get('facial_valence', 0.0)
        blink_rate = result.get('blink_rate_per_min', 0.0)
        confidence = result.get('emotion_confidence', 0.0)
        face_detected = result.get('face_detected', False)

        # --- Severity color ---
        if severity < 0.3:
            sev_color = (16, 185, 129)  # green
            sev_label = "LOW"
        elif severity < 0.7:
            sev_color = (245, 158, 11)  # amber
            sev_label = "MED"
        else:
            sev_color = (239, 68, 68)   # red
            sev_label = "HIGH"

        # --- Top bar: severity badge ---
        draw_rounded_rect(img, (10, 8), (220, 42), (0, 0, 0), 8)
        cv2.putText(img, f"Distress: {severity:.2f} [{sev_label}]", (18, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, sev_color, 2, cv2.LINE_AA)

        if face_detected:
            # --- Emotion badge ---
            emo_color = EMOTION_COLORS.get(emotion, (148, 163, 184))
            draw_rounded_rect(img, (10, 48), (240, 80), (0, 0, 0), 8)
            cv2.putText(img, f"Emotion: {emotion.title()} ({confidence:.0%})", (18, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, emo_color, 1, cv2.LINE_AA)

            # --- Valence bar ---
            draw_rounded_rect(img, (10, 86), (240, 112), (0, 0, 0), 8)
            cv2.putText(img, f"Valence: {valence:+.2f}", (18, 106),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
            # Mini bar
            bar_x = 150
            bar_w = 80
            bar_center = bar_x + bar_w // 2
            bar_fill = int(bar_center + valence * (bar_w // 2))
            cv2.rectangle(img, (bar_x, 94), (bar_x + bar_w, 104), (50, 50, 50), -1)
            v_col = (16, 185, 129) if valence >= 0 else (239, 68, 68)
            cv2.rectangle(img, (min(bar_center, bar_fill), 94), (max(bar_center, bar_fill), 104), v_col, -1)

            # --- Blink rate ---
            draw_rounded_rect(img, (10, 118), (180, 144), (0, 0, 0), 8)
            cv2.putText(img, f"Blinks: {blink_rate:.0f}/min", (18, 138),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
        else:
            draw_rounded_rect(img, (10, 48), (200, 78), (0, 0, 0), 8)
            cv2.putText(img, "No face detected", (18, 68),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


def render_video_call(facial_engine, feature_fusion_engine, speech_engine=None):
    """Render the WebRTC video call component."""
    st.markdown('<div class="video-container">', unsafe_allow_html=True)

    webrtc_ctx = webrtc_streamer(
        key="clinical-video-call",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=RTC_CONFIGURATION,
        video_processor_factory=lambda: VideoProcessor(facial_engine, feature_fusion_engine),
        media_stream_constraints={
            "video": {"width": {"ideal": 1280}, "height": {"ideal": 720}, "frameRate": {"ideal": 30, "max": 30}},
            "audio": False
        },
        async_processing=True,
    )

    st.markdown('</div>', unsafe_allow_html=True)
    return webrtc_ctx
