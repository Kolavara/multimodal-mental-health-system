from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from agents.state import ClinicalState
from agents.tools import psychiatrist_tools
from config import get_config

CFG = get_config()

PSYCHIATRIST_PROMPT = """You are Dr. Smith, a senior Clinical Psychiatrist.
You have been paged because the patient's real-time multimodal severity score has exceeded the clinical threshold ({severity} > {threshold}).
Your role is to:
1. Review the conversation history with the Psychologist.
2. Use your tools to fetch the patient's medical history, recent labs, and EEG profile.
3. Provide a brief, formal, clinical assessment and a concrete treatment recommendation.
4. EXPLICITLY ask the patient to provide their lab reports (e.g., blood work, EEG data, or recent medical tests) so you can accurately diagnose their predicted disorder and try to fix it.

Here is the real-time telemetry and predicted disorder from the background systems:
- Current Multimodal Severity: {severity}
- AI-Predicted Likely Disorder: {predicted_disorder}
- Vocal Arousal/Distress: {vocal_arousal}

You are speaking to the patient, but in a professional, clinical manner.
You must use your tools to check their chart before making a recommendation.
"""

def psychiatrist_node(state: ClinicalState) -> dict:
    """The Psychiatrist agent node."""
    # We use temperature 0.0 for clinical accuracy and tool use
    llm = ChatGroq(
        api_key=CFG.GROQ_API_KEY,
        model_name=CFG.GROQ_MODEL,
        temperature=0.0,
        max_retries=2,
        timeout=30,
    ).bind_tools(psychiatrist_tools)
    
    s_feat = state.get('speech_features', {})
    
    sys_prompt = PSYCHIATRIST_PROMPT.format(
        severity=round(state.get('current_severity', 0.0), 2),
        threshold=CFG.SEVERITY_ESCALATION_THRESHOLD,
        predicted_disorder=s_feat.get('likely_disorder', 'Unknown'),
        vocal_arousal=round(s_feat.get('vocal_arousal', 0.0), 2)
    )
    
    messages = [SystemMessage(content=sys_prompt)] + state['messages']
    
    response = llm.invoke(messages)
    
    return {"messages": [response]}
