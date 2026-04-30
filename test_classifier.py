import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GROQ_API_KEY")

llm = ChatGroq(
    api_key=api_key,
    model_name="llama-3.1-8b-instant",
    temperature=0.0
)

text = "The government has implanted a chip in my tooth and the voices are telling me what to do."

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
response = llm.invoke(msg)
print(response.content)
