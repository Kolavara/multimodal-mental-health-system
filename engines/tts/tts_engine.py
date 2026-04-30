import asyncio
import threading
import subprocess
import logging
from queue import Queue

try:
    from config import get_config
    CFG = get_config()
except ImportError:
    class FallbackConfig:
        TTS_VOICE = "en-US-AriaNeural"
    CFG = FallbackConfig()


class TTSEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.speech_queue = Queue()
        self._running = False
        self._current_process = None
        self._worker_thread = None

    def _worker(self):
        """Background thread that pops text from queue and plays it."""
        while self._running:
            try:
                # Block until text is available
                text = self.speech_queue.get(timeout=0.5)
                if not text:
                    continue
                
                self.logger.info(f"TTS Engine speaking: {text[:30]}...")
                
                # Use edge-playback subprocess. This handles async edge-tts generation
                # and local playback without needing complex async loop management here.
                command = [
                    "edge-playback",
                    "--text", text,
                    "--voice", CFG.TTS_VOICE
                ]
                
                # We start the process and wait for it.
                # If stop() is called, it will kill self._current_process
                self._current_process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                
                self._current_process.wait()
                self._current_process = None
                
            except Exception as e:
                pass

    def start(self):
        """Start the TTS background worker."""
        if not self._running:
            self._running = True
            self._worker_thread = threading.Thread(target=self._worker, daemon=True)
            self._worker_thread.start()

    def stop_current_speech(self):
        """Instantly stop the currently playing speech."""
        if self._current_process and self._current_process.poll() is None:
            self.logger.info("Interrupting current TTS playback.")
            self._current_process.terminate()
            self._current_process = None
            
        # Clear the pending queue
        while not self.speech_queue.empty():
            self.speech_queue.get()

    def speak(self, text: str):
        """Queue text to be spoken."""
        # Sanitize text for CLI
        text = text.replace('"', '').replace('\n', ' ')
        self.speech_queue.put(text)

    def shutdown(self):
        """Cleanly shutdown the engine."""
        self._running = False
        self.stop_current_speech()
        if self._worker_thread:
            self._worker_thread.join(timeout=1.0)


if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)
    
    engine = TTSEngine()
    engine.start()
    
    print("Testing TTS... Should hear two sentences.")
    engine.speak("Hello, this is the psychologist agent.")
    engine.speak("I am here to help you.")
    
    time.sleep(3)
    
    print("Testing interruption...")
    engine.speak("This is a very long sentence that will be interrupted halfway through because the patient started speaking.")
    time.sleep(2)
    engine.stop_current_speech()
    print("Interrupted!")
    
    time.sleep(1)
    engine.shutdown()
