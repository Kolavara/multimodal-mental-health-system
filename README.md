# 🧠 Multimodal Clinical AI Platform

A state-of-the-art, local-first multimodal clinical AI platform built to assist healthcare professionals in diagnosing and tracking mental health disorders. The platform integrates real-time facial emotion recognition, speech sentiment analysis, and a LangGraph-powered AI conversational agent.

## 🌟 Key Features

*   **Multimodal Feature Fusion:** Real-time blending of visual (facial expressions) and auditory (speech sentiment) distress signals to calculate a dynamic patient severity score.
*   **Role-Based Access Control:** Secure authentication system with tailored views for patients, clinicians, and administrators.
*   **AI Psychologist Agent:** A conversational agent that conducts interactive therapy sessions, tracks patient state, and synthesizes clinical notes.
*   **Integrated Psychiatric Reports:** Blends conversational findings with simulated clinical biomarkers (e.g., Cortisol, Serotonin) to generate a comprehensive diagnostic summary.
*   **Longitudinal Tracking:** Persistent patient history with interactive "Risk Level Trend" visualization to track progress over multiple sessions.
*   **Local-First Architecture:** Designed to run sensitive inferencing locally on hardware, ensuring data privacy and low latency.

---

## 📸 Platform Interface

### 1. Secure Authentication Portal
Role-based login system separating Patient access from the Administrator portal. Features a clean, dark neumorphic design.

![Login Page](assets/images/login_page_1777518479859.png)

### 2. Live Clinician Dashboard
The primary interface during a therapy session. Features real-time facial emotion telemetry, live voice-to-text transcription, and a conversation panel with the AI Psychologist. It continuously monitors the global severity score.

![Clinician Dashboard](assets/images/clinician_dashboard_1777518495403.png)

### 3. Integrated Psychiatrist Report
Generates a formal medical evaluation combining the AI Psychologist's conversational findings with the AI Psychiatrist's biomarker analysis. Calculates a blended clinical risk level based on the abnormalities detected.

![Psychiatrist Report](assets/images/psychiatrist_report_1777518617983.png)

### 4. Patient History & Trend Analysis
A dedicated portal for patients to review their past sessions. Includes an interactive Altair chart mapping their longitudinal Risk Level (%) against session progression.

![Previous Reports](assets/images/previous_reports_1777518632160.png)

### 5. Administrator Fleet View
A high-level dashboard for hospital administrators or head clinicians to monitor all patients. Displays a grid of patient cards highlighting their session count and current diagnostic risk.

![Admin Portal](assets/images/admin_portal_1777518699652.png)

---

## 🛠️ Technology Stack

*   **Frontend UI:** Streamlit with custom CSS (Neumorphism aesthetic).
*   **Charting:** Altair (Declarative statistical visualization).
*   **AI Agent Orchestration:** LangChain & LangGraph.
*   **Facial Recognition:** MediaPipe + custom TensorFlow Keras Emotion Classifier.
*   **Speech Processing:** Whisper (faster-whisper) + edge-tts.
*   **Database:** SQLite (local persistence).
*   **Data Streaming:** Python Dataclasses and internal state management.

## 🚀 Getting Started

### Prerequisites
*   Python 3.10+
*   Dependencies listed in `requirements.txt`

### Installation
1. Clone the repository.
2. Install the requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your `.env` file (see `config.py` for required variables, e.g., `GROQ_API_KEY`).

### Running the App
Start the Streamlit development server:
```bash
streamlit run app.py
```
