from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage


class ClinicalState(TypedDict):
    """
    The state shared between nodes in the LangGraph clinical pipeline.
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    patient_id: str
    session_id: str
    
    # Live Multimodal Data (Injected by Streamlit UI / Redpanda)
    current_severity: float
    facial_features: dict
    speech_features: dict
    
    # Agent Memory & Routing
    current_agent: str      # "psychologist" or "psychiatrist"
    escalation_reason: str  # Why the handoff occurred
    clinical_summary: str   # Psychologist's notes passed to Psychiatrist
