"""
speech_engine.py — CPU-based Speech Analysis Engine

Uses faster-whisper to transcribe audio in real-time, extracts prosodic features 
(pitch, speech rate, pauses) using numpy, and derives vocal valence/arousal 
to gauge emotional state. All processing strictly on CPU to save VRAM.
"""

import os
import time
import queue
import threading
import tempfile
import numpy as np
from collections import deque
from faster_whisper import WhisperModel
import logging
import sounddevice as sd
import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from config import get_config
    CFG = get_config()
except ImportError:
    # Fallback for standalone testing
    class FallbackConfig:
        WHISPER_MODEL_SIZE = "small"
        WHISPER_DEVICE = "cpu"
        WHISPER_COMPUTE_TYPE = "int8"
        AUDIO_SAMPLE_RATE = 16000
    CFG = FallbackConfig()


# ── Lazy-loaded WhisperModel singleton (only loaded on first transcription) ──
_whisper_model = None
_whisper_lock = threading.Lock()


def _get_cached_whisper_model():
    """Return a singleton WhisperModel, loading it only on first call."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        logging.getLogger(__name__).info(
            f"Loading faster-whisper {CFG.WHISPER_MODEL_SIZE} on {CFG.WHISPER_DEVICE}..."
        )
        _whisper_model = WhisperModel(
            CFG.WHISPER_MODEL_SIZE,
            device=CFG.WHISPER_DEVICE,
            compute_type=CFG.WHISPER_COMPUTE_TYPE
        )
        logging.getLogger(__name__).info("Speech model loaded.")
        return _whisper_model


class SpeechAnalysisEngine:
    def __init__(self, patient_id: str, session_id: str):
        self.patient_id = patient_id
        self.session_id = session_id
        self.logger = logging.getLogger(__name__)
        
        # Whisper model is loaded lazily on first transcription call
        # (not used in current UI — text input goes through Groq LLM)
        self._model = None
        
        # State tracking
        self.transcript_history = []
        self.pitch_history = deque(maxlen=300)
        self.speech_rate_history = deque(maxlen=50)
        self.last_speech_time = time.time()
        self.pause_events = []
        
        # Threading for real-time capture
        self.audio_queue = queue.Queue()
        self._running = False
        self._process_thread = None
        self._stream = None
        self.webrtc_transcript_queue = queue.Queue()
        self._last_speech_detected_time = time.time()
        self._is_speaking = False
        self._current_sentence = []
        self.latest_speech_data = {}
        
        # Init Groq LLM for text analysis
        self.llm = ChatGroq(api_key=CFG.GROQ_API_KEY, model_name=CFG.GROQ_MODEL, temperature=0.0)

    @property
    def model(self):
        """Lazy-load WhisperModel only when transcription is actually needed."""
        if self._model is None:
            self._model = _get_cached_whisper_model()
        return self._model

    def push_webrtc_audio(self, chunk: np.ndarray):
        """Pushed from dashboard/video_call.py WebRTC AudioProcessor"""
        self.audio_queue.put(chunk)

    def process_audio_chunk(self, audio_data: np.ndarray) -> dict:
        """
        Process a chunk of audio for transcription and prosody.
        audio_data should be 16kHz float32 mono.
        """
        start_t = time.time()
        
        # 1. Prosody Analysis (Pitch)
        pitch = self._estimate_pitch(audio_data)
        if pitch > 50: # Ignore noise/silence
            self.pitch_history.append(pitch)
            self.last_speech_time = time.time()
        else:
            # Track pauses > 2 seconds
            silence_duration = time.time() - self.last_speech_time
            if silence_duration > 2.0 and (not self.pause_events or time.time() - self.pause_events[-1]['timestamp'] > 5.0):
                self.pause_events.append({
                    'timestamp': time.time(),
                    'duration': silence_duration
                })
        
        # 2. Transcription
        transcript = ""
        words_per_sec = 0.0
        
        # We only run transcription if there's enough audio and it's not silent
        if np.abs(audio_data).mean() > 0.005: 
            try:
                segments, info = self.model.transcribe(
                    audio_data, 
                    beam_size=5, 
                    language="en",
                    condition_on_previous_text=False
                )
                
                texts = []
                word_count = 0
                for segment in segments:
                    texts.append(segment.text)
                    word_count += len(segment.text.split())
                    
                transcript = " ".join(texts).strip()
                if transcript:
                    duration = len(audio_data) / CFG.AUDIO_SAMPLE_RATE
                    words_per_sec = word_count / duration if duration > 0 else 0
                    self.speech_rate_history.append(words_per_sec)
                    self.transcript_history.append({
                        'timestamp': time.time(),
                        'text': transcript
                    })
            except Exception as e:
                self.logger.error(f"Transcription error: {e}")

        # 3. Emotional Feature Derivation
        valence, arousal = self._derive_vocal_emotion(pitch, words_per_sec)
        
        process_time = time.time() - start_t
        
        return {
            'timestamp': time.time(),
            'transcript': transcript,
            'pitch_hz': float(pitch),
            'speech_rate_wps': float(words_per_sec),
            'vocal_valence': float(valence),
            'vocal_arousal': float(arousal),
            'long_pauses_count': len(self.pause_events),
            'processing_time_ms': round(process_time * 1000, 2)
        }

    def _estimate_pitch(self, audio_data: np.ndarray) -> float:
        """Simple auto-correlation based pitch estimation."""
        if len(audio_data) == 0 or np.abs(audio_data).mean() < 0.001:
            return 0.0
            
        # Simplified zero-crossing rate as proxy for pitch for speed
        zero_crossings = np.where(np.diff(np.sign(audio_data)))[0]
        if len(zero_crossings) < 2:
            return 0.0
            
        rate = CFG.AUDIO_SAMPLE_RATE
        duration = len(audio_data) / rate
        return (len(zero_crossings) / 2) / duration

    def _derive_vocal_emotion(self, pitch: float, wps: float) -> tuple[float, float]:
        """
        Estimate emotional valence/arousal from prosody.
        This is a heuristic proxy for the MVP.
        """
        arousal = 0.5
        valence = 0.0
        
        # High pitch & fast speech -> High arousal (anxiety/excitement)
        if pitch > 200 and wps > 3.0:
            arousal = 0.8
            valence = -0.5 # Leaning anxious
            
        # Low pitch, slow speech, long pauses -> Low arousal, negative valence (depression)
        elif pitch > 0 and pitch < 100 and wps > 0 and wps < 1.5:
            arousal = 0.2
            valence = -0.7
            
        # Monotone (low pitch variance)
        if len(self.pitch_history) > 10:
            pitch_std = np.std(self.pitch_history)
            if pitch_std < 10: # Flat affect
                valence -= 0.3
                
        return max(-1.0, min(1.0, valence)), max(0.0, min(1.0, arousal))

    def get_clinical_summary(self) -> str:
        """Return a summarized clinical view of the conversation analysis."""
        distress = self.latest_speech_data.get('content_distress', 0.0)
        disorder = self.latest_speech_data.get('likely_disorder', 'None')
        n_messages = len(self.transcript_history)

        if n_messages == 0:
            return "No conversation data captured in this session."

        recent_text = " ".join([t['text'] for t in self.transcript_history[-3:]])
        distress_label = (
            "high" if distress > 0.6 else
            "moderate" if distress > 0.3 else
            "low"
        )

        return (
            f"Conversation Analysis ({n_messages} messages): "
            f"Content distress is {distress_label} ({distress:.2f}). "
            f"Predicted disorder: {disorder}. "
            f"Recent excerpt: '{recent_text[-120:]}'"
        )
        
    # --- Live Microphone Capture Methods ---
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice input stream."""
        if status:
            self.logger.warning(f"Audio stream status: {status}")
        self.audio_queue.put(indata.copy())
        
    def _processing_loop(self):
        """Background thread that consumes audio chunks and processes them."""
        # Accumulate ~2 seconds of audio before transcribing
        buffer_size = int(CFG.AUDIO_SAMPLE_RATE * 2.0) 
        audio_buffer = np.zeros(0, dtype=np.float32)
        
        self.logger.info("Speech Engine processing loop started.")
        
        while self._running:
            try:
                # Check for 5 seconds of silence to emit full sentence
                now = time.time()
                if self._is_speaking and (now - self._last_speech_detected_time > 5.0):
                    if self._current_sentence:
                        final_text = " ".join(self._current_sentence).strip()
                        if final_text:
                            # Classify disorder and distress asynchronously
                            self._classify_text_async(final_text)
                            self.webrtc_transcript_queue.put(final_text)
                        self._current_sentence = []
                    self._is_speaking = False
                    
                # Get audio chunk (blocking with timeout)
                chunk = self.audio_queue.get(timeout=0.5)
                # Ensure mono float32
                if chunk.ndim > 1:
                    chunk = chunk.mean(axis=1)
                chunk = chunk.flatten().astype(np.float32)
                
                # Critical Fix: WebRTC chunks come in as raw PCM (often -32768 to 32767). 
                # Whisper requires float32 between -1.0 and 1.0!
                if np.max(np.abs(chunk)) > 2.0:
                    chunk = chunk / 32768.0
                
                audio_buffer = np.concatenate((audio_buffer, chunk))
                
                # Check volume to reset silence timer
                if np.abs(chunk).mean() > 0.005:
                    self._last_speech_detected_time = time.time()
                    self._is_speaking = True
                
                # Process when buffer is full
                if len(audio_buffer) >= buffer_size:
                    result = self.process_audio_chunk(audio_buffer)
                    # Merge with existing latest_speech_data to keep content_distress and likely_disorder
                    for k, v in result.items():
                        self.latest_speech_data[k] = v
                    
                    if result['transcript']:
                        self._current_sentence.append(result['transcript'])
                        self.logger.info(f"Intermediate Transcript: {result['transcript']}")
                    
                    # Slide buffer, keeping last 0.5s for continuity
                    keep = int(CFG.AUDIO_SAMPLE_RATE * 0.5)
                    audio_buffer = audio_buffer[-keep:]
                    
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Processing loop error: {e}")

    def process_wav_bytes(self, wav_bytes: bytes) -> str:
        """Process audio from Streamlit st.audio_input (browser sends WebM/Opus, not WAV)."""
        import subprocess
        import numpy as np
        from scipy.io import wavfile
        import io
        import streamlit as st
        try:
            start_t = time.time()
            print(f"\n{'='*60}")
            print(f"[SPEECH] process_wav_bytes called with {len(wav_bytes)} bytes")
            print(f"{'='*60}")
            
            # Step 1: Save raw browser audio (WebM/Opus format) to a temp file
            tmp_dir = tempfile.gettempdir()
            temp_input = os.path.join(tmp_dir, "clinical_ai_browser_audio.webm")
            temp_output = os.path.join(tmp_dir, "clinical_ai_whisper_audio.wav")
            with open(temp_input, "wb") as f:
                f.write(wav_bytes)
            print(f"[SPEECH] Step 1: Saved {len(wav_bytes)} bytes to {temp_input}")
            
            # Step 2: Use bundled ffmpeg to convert WebM → 16kHz mono WAV
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            print(f"[SPEECH] Step 2: FFmpeg path = {ffmpeg_path}")
            
            result = subprocess.run([
                ffmpeg_path, "-y",
                "-i", temp_input,
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                temp_output
            ], capture_output=True, timeout=15)
            
            if result.returncode != 0:
                err_msg = result.stderr.decode()
                print(f"[SPEECH] ERROR: FFmpeg failed: {err_msg}")
                st.error(f"FFmpeg conversion failed: {err_msg}")
                return ""
            
            print(f"[SPEECH] Step 2: FFmpeg conversion OK → {temp_output}")
            
            # Step 3: Read the clean WAV with scipy and pass numpy array to Whisper
            sample_rate, data = wavfile.read(temp_output)
            data = data.astype(np.float32) / 32768.0  # int16 → float32 [-1, 1]
            duration = len(data) / sample_rate
            print(f"[SPEECH] Step 3: WAV loaded — {sample_rate}Hz, {len(data)} samples, {duration:.1f}s")
            
            print(f"[SPEECH] Step 4: Starting Whisper transcription...")
            segments, info = self.model.transcribe(
                data, 
                beam_size=5, 
                language="en",
                condition_on_previous_text=False
            )
            
            texts = []
            for segment in segments:
                texts.append(segment.text)
                print(f"[SPEECH]   segment: '{segment.text}'")
                
            transcript = " ".join(texts).strip()
            elapsed = time.time() - start_t
            print(f"[SPEECH] Step 5: Transcript = '{transcript}' ({elapsed:.1f}s)")
            
            if transcript:
                self._classify_text_async(transcript)
                self.transcript_history.append({
                    'timestamp': time.time(),
                    'text': transcript
                })
                
                # Update speech metrics with transcription and default baseline prosody
                self.latest_speech_data.update({
                    'timestamp': time.time(),
                    'transcript': transcript,
                    'pitch_hz': 120.0,
                    'speech_rate_wps': 2.5,
                    'vocal_valence': 0.0,
                    'vocal_arousal': 0.5,
                    'long_pauses_count': 0,
                    'processing_time_ms': round((time.time() - start_t) * 1000, 2)
                })
                
            return transcript
        except Exception as e:
            print(f"[SPEECH] EXCEPTION: {e}")
            self.logger.error(f"Streamlit audio transcription error: {e}")
            import traceback
            
            tb = traceback.format_exc()
            print(f"[SPEECH] TRACEBACK:\n{tb}")
            
            with open("error_log.txt", "w") as f:
                f.write(tb)
                
            st.error(f"Transcription Error: {e}")
            return ""

    def _classify_text_async(self, text: str):
        # Save to transcript history so clinical summary works
        self.transcript_history.append({
            'timestamp': time.time(),
            'text': text
        })

        def worker():
            try:
                sys_prompt = (
                    "You are a clinical text analyzer. Analyze the transcript for signs of mental health disorders.\n"
                    "Use these criteria:\n"
                    "1. Mood Disorders (Depression, Bipolar): sadness, slow response, anhedonia, fatigue, pressured speech, grandiosity.\n"
                    "2. Anxiety Disorders (GAD, Social Anxiety, Panic): excessive worry, 'what if', avoidance, fear of judgment.\n"
                    "3. Trauma (PTSD): intrusive memories, emotional numbness, avoidance, hypervigilance.\n"
                    "4. Psychotic Disorders: disorganized thought, delusions, hallucinations, flat affect.\n"
                    "5. Personality Disorders (BPD, Narcissistic): intense fear of abandonment, black-and-white thinking, grandiosity.\n"
                    "6. OCD/Eating/Neurodevelopmental/Substance/Sleep disorders where applicable.\n\n"
                    "Output ONLY valid JSON with two keys: 'content_distress' (float 0.0 to 1.0 indicating emotional distress) and 'likely_disorder' (string, specific disorder name from above, or 'None')."
                )
                msg = [SystemMessage(content=sys_prompt), HumanMessage(content=text)]
                response = self.llm.invoke(msg)
                
                # Extract JSON
                content = response.content
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                
                data = json.loads(content.strip())
                self.latest_speech_data['content_distress'] = float(data.get('content_distress', 0.5))
                self.latest_speech_data['likely_disorder'] = str(data.get('likely_disorder', 'None'))
                self.logger.info(f"Text Classification: {data}")
            except Exception as e:
                self.logger.error(f"Text classification error: {e}")
                
        threading.Thread(target=worker, daemon=True).start()

    def start_processing_thread(self):
        """Start just the background thread (used with WebRTC)."""
        if not self._running:
            self._running = True
            self._process_thread = threading.Thread(target=self._processing_loop)
            self._process_thread.daemon = True
            self._process_thread.start()

    def start_mic_stream(self):
        """Start listening to the default microphone."""
        self.start_processing_thread()
        self._stream = sd.InputStream(
            samplerate=CFG.AUDIO_SAMPLE_RATE,
            channels=1,
            callback=self._audio_callback
        )
        self._stream.start()

    def stop_mic_stream(self):
        """Stop listening to the microphone."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        if self._process_thread:
            self._process_thread.join()
        print("\n🛑 Microphone stream stopped.")
        print("\n=== CLINICAL SUMMARY ===")
        print(self.get_clinical_summary())


if __name__ == "__main__":
    # Test harness
    logging.basicConfig(level=logging.INFO)
    
    engine = SpeechAnalysisEngine("test_patient", "test_session")
    engine.start_mic_stream()
    
    try:
        print("\nPress Ctrl+C to stop...\n")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop_mic_stream()
