import os

def get_psychologist_system_prompt() -> str:
    """
    Reads the file data/mock/psychologist_system_prompt.txt and returns its full contents as a string.
    Has a fallback hardcoded short version if the file is not found.
    """
    filepath = os.path.join('data', 'mock', 'psychologist_system_prompt.txt')
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as file:
                return file.read()
    except Exception as e:
        print(f"Error reading psychologist_system_prompt.txt: {e}")
        
    # Fallback short version
    return (
        "You are ARIA, a clinical AI assistant. You conduct structured "
        "mental health assessments. Never diagnose. Always refer to "
        "licensed clinicians. Flag crisis indicators immediately."
    )
