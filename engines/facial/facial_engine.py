"""
facial_engine.py — MediaPipe + TensorFlow Facial Analysis Engine

Uses MediaPipe Face Landmarker (Tasks API) with blendshapes enabled for
real-time facial analysis. All processing runs on CPU. Thread-safe.
"""

import cv2
import numpy as np
import mediapipe as mp
from collections import deque, Counter
import time
import math
import logging
import threading
import os

from engines.facial.emotion_classifier import get_emotion_classifier
from engines.facial.microexpression import MicroexpressionDetector

BLENDSHAPE_NAMES = [
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft",
    "browOuterUpRight", "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
    "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen",
    "jawRight", "mouthClose", "mouthDimpleLeft", "mouthDimpleRight",
    "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft",
    "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft",
    "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower",
    "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft",
    "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft",
    "noseSneerRight", "_neutral"
]


class FacialAnalysisEngine:
    def __init__(self, patient_id: str, session_id: str):
        self.patient_id = patient_id
        self.session_id = session_id
        self.frame_count = 0
        self.blink_active = False
        self.last_head_pose = None

        model_path = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Face landmarker model not found at {model_path}. "
                "Download from: https://storage.googleapis.com/mediapipe-models/"
                "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
            )

        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.7,
            min_face_presence_confidence=0.7,
            min_tracking_confidence=0.7,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=False,
        )
        self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

        self.emotion_classifier = get_emotion_classifier()
        self.micro_detector = MicroexpressionDetector()

        self.valence_history = deque(maxlen=900)
        self.arousal_history = deque(maxlen=900)
        self.gaze_history = deque(maxlen=300)
        self.blink_timestamps = deque(maxlen=200)
        self.emotion_history = deque(maxlen=300)
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

    def process_frame_sync(self, frame: np.ndarray) -> dict:
        """Synchronous processing for WebRTC video threads."""
        with self._lock:
            try:
                return self._process_internal(frame)
            except Exception as e:
                self.logger.error(f"Frame processing error: {e}", exc_info=True)
                return self._empty_features()

    def _process_internal(self, frame: np.ndarray) -> dict:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(mp_image)

        if not result.face_landmarks or len(result.face_landmarks) == 0:
            return self._empty_features()

        h, w = frame.shape[:2]
        raw_landmarks = result.face_landmarks[0]
        lm = np.array([[l.x * w, l.y * h, l.z] for l in raw_landmarks])

        # Blendshapes + Emotion Classification
        bs_dict, bs_scores = {}, []
        dominant_emotion, emotion_confidence, emotion_probs = "neutral", 0.0, {}

        if result.face_blendshapes and len(result.face_blendshapes) > 0:
            for cat in result.face_blendshapes[0]:
                bs_dict[cat.category_name] = cat.score
            for name in BLENDSHAPE_NAMES:
                bs_scores.append(bs_dict.get(name, 0.0))

            emo = self.emotion_classifier.predict(bs_scores)
            dominant_emotion = emo['dominant_emotion']
            emotion_confidence = emo['confidence']
            emotion_probs = emo['probabilities']
            self.emotion_history.append(dominant_emotion)
            self.micro_detector.update(bs_dict)

        valence, arousal = self._compute_valence_arousal(bs_dict, lm)
        blink_detected, ear, blink_rate = self._compute_blink(lm, bs_dict)
        gaze_entropy, eye_contact = self._compute_gaze(lm)
        head_pose, head_vel = self._compute_head_pose_safe(lm, frame.shape)

        self.valence_history.append(valence)
        self.arousal_history.append(arousal)
        recent = list(self.valence_history)[-30:]
        stability = float(np.std(recent)) if len(recent) >= 30 else 0.5
        self.frame_count += 1

        return {
            'timestamp': time.time(), 'face_detected': True,
            'frame_count': self.frame_count,
            'dominant_emotion': dominant_emotion,
            'emotion_confidence': float(emotion_confidence),
            'emotion_probabilities': emotion_probs,
            'facial_valence': float(valence), 'facial_arousal': float(arousal),
            'affect_stability_score': float(stability),
            'eye_contact_ratio': float(eye_contact),
            'gaze_direction_entropy': float(gaze_entropy),
            'head_pose': head_pose, 'head_movement_velocity': float(head_vel),
            'top_blendshapes': self._top_bs(bs_dict),
            'recent_microexpressions': self.micro_detector.get_recent_events(30),
        }

    def _compute_valence_arousal(self, bs, lm):
        if bs:
            smile = (bs.get('mouthSmileLeft', 0) + bs.get('mouthSmileRight', 0)) / 2
            frown = (bs.get('mouthFrownLeft', 0) + bs.get('mouthFrownRight', 0)) / 2
            brow_d = (bs.get('browDownLeft', 0) + bs.get('browDownRight', 0)) / 2
            brow_u = bs.get('browInnerUp', 0)
            eye_w = (bs.get('eyeWideLeft', 0) + bs.get('eyeWideRight', 0)) / 2
            jaw = bs.get('jawOpen', 0)
            cheek = (bs.get('cheekSquintLeft', 0) + bs.get('cheekSquintRight', 0)) / 2
            v = (smile * 0.6 + cheek * 0.2) - (frown * 0.5 + brow_d * 0.3)
            a = eye_w * 0.3 + jaw * 0.2 + brow_u * 0.2 + abs(v) * 0.3
            return max(-1, min(1, v)), max(0, min(1, a))
        try:
            lm61, lm291 = lm[61][:2], lm[291][:2]
            mw = np.linalg.norm(lm61 - lm291)
            mh = np.linalg.norm(lm[13][:2] - lm[14][:2])
            r = mw / (mh + 1e-6)
            return (0.6 if r > 3 else -0.4 if r < 1.5 else 0.0), 0.5
        except (IndexError, ValueError):
            return 0.0, 0.5

    def _compute_blink(self, lm, bs_dict):
        if bs_dict:
            # Neural-network blendshapes are much more accurate than geometric EAR
            blink_left = bs_dict.get('eyeBlinkLeft', 0.0)
            blink_right = bs_dict.get('eyeBlinkRight', 0.0)
            avg_blink = (blink_left + blink_right) / 2.0
            
            det = False
            if avg_blink > 0.45 and not self.blink_active:
                self.blink_active = True
                self.blink_timestamps.append(time.time())
                det = True
            elif avg_blink <= 0.35:
                self.blink_active = False
                
            now = time.time()
            rate = float(sum(1 for t in self.blink_timestamps if now - t < 60))
            return det, float(avg_blink), rate
        else:
            return False, 0.0, 0.0

    def _compute_gaze(self, lm):
        try:
            iris = lm[468, :2].copy() if len(lm) > 468 else lm[[159, 145], :2].mean(axis=0)
            center = lm[[33, 133], :2].mean(axis=0)
            gaze = iris - center
            self.gaze_history.append(gaze)
            if len(self.gaze_history) < 30:
                return 0.0, (1.0 if abs(gaze[0]) < 5 and abs(gaze[1]) < 5 else 0.0)
            dirs = np.array(list(self.gaze_history))
            angles = np.arctan2(dirs[:, 1], dirs[:, 0])
            bins = np.histogram(angles, bins=8, range=(-np.pi, np.pi))[0]
            s = bins.sum()
            if s == 0:
                return 0.0, 0.0
            p = bins[bins > 0] / s
            entropy = float(-np.sum(p * np.log2(p)))
            contact = 1.0 if abs(gaze[0]) < 5 and abs(gaze[1]) < 5 else 0.0
            return entropy, contact
        except (IndexError, ValueError):
            return 0.0, 0.0

    def _compute_head_pose_safe(self, lm, shape):
        try:
            pose = self._compute_head_pose(lm, shape)
        except Exception:
            pose = {'pitch': 0, 'yaw': 0, 'roll': 0}
        if self.last_head_pose:
            vel = math.sqrt(sum((pose[k] - self.last_head_pose[k])**2 for k in ('pitch', 'yaw', 'roll')))
        else:
            vel = 0.0
        self.last_head_pose = pose
        return pose, vel

    def _compute_head_pose(self, lm, shape):
        ip = np.array([lm[1,:2], lm[152,:2], lm[226,:2], lm[446,:2], lm[57,:2], lm[287,:2]], dtype=np.float64)
        mp_ = np.array([[0,0,0],[0,-330,-65],[-165,170,-135],[165,170,-135],[-150,-150,-125],[150,-150,-125]], dtype=np.float64)
        h, w = shape[:2]
        cm = np.array([[w,0,w/2],[0,w,h/2],[0,0,1]], dtype=np.float64)
        ok, rv, tv = cv2.solvePnP(mp_, ip, cm, np.zeros((4,1)), flags=cv2.SOLVEPNP_ITERATIVE)
        if ok:
            rm, _ = cv2.Rodrigues(rv)
            a, _, _, _, _, _ = cv2.RQDecomp3x3(rm)
            return {'pitch': a[0], 'yaw': a[1], 'roll': a[2]}
        return {'pitch': 0, 'yaw': 0, 'roll': 0}

    def _top_bs(self, bs, n=5):
        if not bs:
            return []
        return [{'name': k, 'score': round(v, 3)} for k, v in sorted(bs.items(), key=lambda x: x[1], reverse=True)[:n] if v > 0.01]

    def _empty_features(self):
        return {
            'timestamp': time.time(), 'face_detected': False, 'frame_count': self.frame_count,
            'dominant_emotion': 'unknown', 'emotion_confidence': 0.0, 'emotion_probabilities': {},
            'facial_valence': 0.0, 'facial_arousal': 0.0, 'affect_stability_score': 0.0,
            'blink_detected': False, 'blink_rate_per_min': 0.0, 'ear': 0.0,
            'eye_contact_ratio': 0.0, 'gaze_direction_entropy': 0.0,
            'head_pose': {'pitch': 0, 'yaw': 0, 'roll': 0}, 'head_movement_velocity': 0.0,
            'top_blendshapes': [], 'recent_microexpressions': [],
        }

    def get_clinical_summary(self) -> str:
        if self.frame_count == 0:
            return "No facial data captured in this session."
        avg_v = float(np.mean(self.valence_history)) if self.valence_history else 0.0
        blinks = len(self.blink_timestamps)
        stab = float(np.std(list(self.valence_history)[-60:])) if len(self.valence_history) >= 60 else 0.5
        label = "positive" if avg_v > 0.2 else "negative" if avg_v < -0.2 else "neutral"
        emo_str = ""
        if self.emotion_history:
            dom = Counter(self.emotion_history).most_common(1)[0]
            emo_str = f" Predominant emotion: {dom[0]} ({dom[1]}/{len(self.emotion_history)} frames)."
        micro = self.micro_detector.get_summary()
        return (
            f"Facial Analysis ({self.frame_count} frames): "
            f"Average affect is {label} (valence={avg_v:.2f}). "
            f"{blinks} blinks. Stability std={stab:.2f}.{emo_str} "
            f"Microexpressions: {micro['total_count']} — {micro['clinical_significance']}."
        )

    def release(self):
        self.landmarker.close()
        self.logger.info("FacialAnalysisEngine released")
