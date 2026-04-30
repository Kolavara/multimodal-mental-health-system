from langchain_core.tools import tool
import random

# Mock Medical Database (EHR/FHIR)
MOCK_PATIENT_DB = {
    "demo_patient_001": {
        "name": "Jane Doe",
        "age": 28,
        "history": ["GAD (Generalized Anxiety Disorder)", "Insomnia"],
        "medications": ["Sertraline 50mg"],
        "recent_labs": {
            "thyroid_tsh": "Normal (1.5 mIU/L)",
            "vitamin_d": "Low (18 ng/mL)"
        },
        "eeg_baseline": "Normal alpha rhythm, mild frontal beta excess"
    }
}


@tool
def fetch_patient_medical_history(patient_id: str) -> str:
    """Fetch the patient's EHR records, history, and current medications."""
    data = MOCK_PATIENT_DB.get(patient_id)
    if not data:
        return "No medical history found for this patient."
    
    return (f"Patient Name: {data['name']}, Age: {data['age']}\n"
            f"History: {', '.join(data['history'])}\n"
            f"Current Meds: {', '.join(data['medications'])}")

@tool
def fetch_recent_lab_results(patient_id: str) -> str:
    """Fetch recent laboratory results (bloodwork, etc.) for the patient."""
    data = MOCK_PATIENT_DB.get(patient_id)
    if not data or "recent_labs" not in data:
        return "No recent labs available."
    
    labs = data["recent_labs"]
    return "\n".join([f"{k}: {v}" for k, v in labs.items()])

@tool
def fetch_eeg_neuro_profile(patient_id: str) -> str:
    """Fetch the patient's baseline EEG and neurological profile."""
    data = MOCK_PATIENT_DB.get(patient_id)
    if not data or "eeg_baseline" not in data:
        return "No EEG data available."
    
    return f"EEG Baseline: {data['eeg_baseline']}"

# List of tools for the Psychiatrist Agent to bind
psychiatrist_tools = [
    fetch_patient_medical_history, 
    fetch_recent_lab_results, 
    fetch_eeg_neuro_profile
]
