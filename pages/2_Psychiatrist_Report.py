import streamlit as st
import os
import PyPDF2
import re

st.set_page_config(page_title="Psychiatrist Report", page_icon="⚕️", layout="wide")

# Load custom CSS
css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Auth guard
if not st.session_state.get("logged_in"):
    st.warning("🔒 Please log in from the main page first.")
    st.stop()


# ── Constants ─────────────────────────────────────────────────
NORMAL_RANGES = {
    "Cortisol_AM": (5.0, 25.0),
    "TSH": (0.4, 4.0),
    "PHQ-9": (0, 4),
    "GAD-7": (0, 4),
    "MADRS": (0, 6),
    "YMRS": (0, 12),
    "PANSS": (30, 60),
    "PCL-5": (0, 30),
    "CAGE-AID": (0, 0),
}

DISORDER_MAPPING = {
    "Cortisol_AM": "Stress-Stressor Related Disorders (PTSD, Acute Stress) or Severe Mood Disorders.",
    "TSH": "If abnormal, can mimic Mood Disorders (Depression/Bipolar) or Anxiety Disorders. Requires medical clearance first.",
    "PHQ-9": "Major Depressive Disorder (MDD), Persistent Depressive Disorder (Dysthymia), or Bipolar (Depressive episode).",
    "GAD-7": "Generalized Anxiety Disorder (GAD), Panic Disorder, or Social Anxiety Disorder.",
    "MADRS": "Major Depressive Disorder (MDD).",
    "YMRS": "Bipolar I & II (Manic, Hypomanic, or Cyclothymic cycling).",
    "PANSS": "Schizophrenia, Schizoaffective Disorder, or Brief Psychotic Disorder.",
    "PCL-5": "PTSD or Complex PTSD (C-PTSD).",
    "CAGE-AID": "Alcohol/Drug Use Disorder.",
}

SOLUTIONS = {
    "Cortisol_AM": "Consult an endocrinologist. Implement stress-reduction techniques and regulate sleep polysomnography (PSG) patterns.",
    "TSH": "Consult a physician for a full thyroid panel (T3, T4) and potential thyroid medication.",
    "PHQ-9": "Consider psychotherapy (CBT) and psychiatric evaluation for SSRI/SNRI antidepressant therapy.",
    "GAD-7": "Engage in exposure therapy, CBT, and consider anxiolytic medications or SSRIs.",
    "MADRS": "Intensive psychiatric evaluation for mood stabilizers or antidepressants; assess for safety.",
    "YMRS": "Immediate psychiatric consult to assess for Bipolar disorder; consider mood stabilizers (e.g., Lithium) or atypical antipsychotics.",
    "PANSS": "Urgent psychiatric intervention required. Antipsychotic medication and structured care environments are recommended.",
    "PCL-5": "Trauma-focused therapy (EMDR, TF-CBT). Assess dissociative symptoms.",
    "CAGE-AID": "Referral to substance abuse counseling, detoxification programs, or support groups.",
}

# ── Helper Functions ──────────────────────────────────────────

def extract_text_from_pdf(uploaded_file):
    """Reads an uploaded PDF and extracts its text."""
    text = ""
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None


def extract_parameters(text):
    """Uses regex to find parameters and their numerical values in the text."""
    extracted_data = {}
    for param in NORMAL_RANGES.keys():
        pattern = rf"{param}\s*[:\-]?\s*(\d+(\.\d+)?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_data[param] = float(match.group(1))
    return extracted_data


def generate_report(patient_data):
    """Compares patient data to thresholds and generates the report."""
    if not patient_data:
        return None, [], []

    abnormal = []
    normal = []

    for param, value in patient_data.items():
        min_val, max_val = NORMAL_RANGES[param]
        entry = {
            "param": param,
            "value": value,
            "min": min_val,
            "max": max_val,
            "disorder": DISORDER_MAPPING.get(param, "Unknown"),
            "solution": SOLUTIONS.get(param, "Consult a specialist."),
        }
        if value < min_val or value > max_val:
            abnormal.append(entry)
        else:
            normal.append(entry)

    return patient_data, abnormal, normal


# ── Page Layout ───────────────────────────────────────────────

st.title("⚕️ Psychiatrist Diagnostic Report")

st.markdown('<div class="neu-card">', unsafe_allow_html=True)
st.markdown('<p class="section-header">📄 Upload Patient Report (PDF)</p>', unsafe_allow_html=True)

st.caption(
    "Upload a clinical PDF containing any of the following parameters: "
    "**Cortisol_AM, TSH, PHQ-9, GAD-7, MADRS, YMRS, PANSS, PCL-5, CAGE-AID**. "
    "The system will extract values, compare them against standard clinical thresholds, "
    "and generate a diagnostic triage report."
)

uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

# ── Manual Entry Fallback ─────────────────────────────────────
st.markdown('<div class="neu-card">', unsafe_allow_html=True)
st.markdown('<p class="section-header">✏️ Or Enter Values Manually</p>', unsafe_allow_html=True)

with st.expander("Manual Parameter Entry", expanded=False):
    manual_cols = st.columns(3)
    manual_data = {}
    params_list = list(NORMAL_RANGES.keys())

    for i, param in enumerate(params_list):
        col = manual_cols[i % 3]
        min_val, max_val = NORMAL_RANGES[param]
        with col:
            val = st.number_input(
                f"{param} (Normal: {min_val}–{max_val})",
                min_value=0.0,
                max_value=200.0,
                value=0.0,
                step=0.1,
                key=f"manual_{param}",
            )
            if val > 0:
                manual_data[param] = val

    if st.button("Generate Report from Manual Values"):
        st.session_state["psych_manual_data"] = manual_data

st.markdown('</div>', unsafe_allow_html=True)


# ── Process and Display Report ────────────────────────────────

patient_data = None

# Priority: uploaded PDF > manual entry
if uploaded_file is not None:
    pdf_text = extract_text_from_pdf(uploaded_file)
    if pdf_text:
        patient_data = extract_parameters(pdf_text)
        if not patient_data:
            st.warning("No recognizable clinical parameters were found in the uploaded PDF. Try manual entry instead.")
elif "psych_manual_data" in st.session_state and st.session_state["psych_manual_data"]:
    patient_data = st.session_state["psych_manual_data"]

if patient_data:
    _, abnormal, normal = generate_report(patient_data)

    # ── Summary Metrics ───────────────────────────────────────
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">📊 Diagnostic Summary</p>', unsafe_allow_html=True)

    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("Parameters Analyzed", len(patient_data))
    with s2:
        st.metric("Abnormalities Found", len(abnormal))
    with s3:
        risk = "HIGH" if len(abnormal) >= 3 else "MODERATE" if len(abnormal) >= 1 else "LOW"
        st.metric("Overall Risk", risk)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Abnormalities ─────────────────────────────────────────
    if abnormal:
        st.markdown('<div class="neu-card">', unsafe_allow_html=True)
        st.markdown('<p class="section-header">🚨 Abnormalities Detected</p>', unsafe_allow_html=True)

        for entry in abnormal:
            with st.expander(f"⚠️ {entry['param']} — Value: {entry['value']} (Normal: {entry['min']}–{entry['max']})", expanded=True):
                st.markdown(f"**Likely Disorder(s):** {entry['disorder']}")
                st.markdown(f"**Recommended Action:** {entry['solution']}")
                # Visual severity bar
                severity = min(abs(entry["value"] - entry["max"]) / (entry["max"] - entry["min"] + 1e-6), 1.0)
                st.progress(severity, text=f"Deviation Severity: {severity:.0%}")

        st.markdown('</div>', unsafe_allow_html=True)

    # ── Normal Parameters ─────────────────────────────────────
    if normal:
        st.markdown('<div class="neu-card">', unsafe_allow_html=True)
        st.markdown('<p class="section-header">✅ Parameters Within Normal Limits</p>', unsafe_allow_html=True)

        for entry in normal:
            st.caption(f"**{entry['param']}** — {entry['value']} (Normal: {entry['min']}–{entry['max']})")

        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# INTEGRATED DIAGNOSIS — works with psychological, psychiatric, or both
# ══════════════════════════════════════════════════════════════
psych_eval = st.session_state.get("evaluation_result", None)
has_psychological = psych_eval is not None
has_psychiatric = patient_data is not None

if has_psychological or has_psychiatric:
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">🧬 Integrated Clinical Summary</p>', unsafe_allow_html=True)

    # ── Build psychiatrist findings text ──────────────────────
    abnormal = []
    normal = []
    psych_report_lines = []
    if has_psychiatric:
        _, abnormal, normal = generate_report(patient_data)
        for entry in abnormal:
            psych_report_lines.append(
                f"- {entry['param']}: {entry['value']} (Normal: {entry['min']}–{entry['max']}) → {entry['disorder']}"
            )
        for entry in normal:
            psych_report_lines.append(
                f"- {entry['param']}: {entry['value']} (Normal: {entry['min']}–{entry['max']}) → Within normal limits"
            )
    psychiatrist_text = "\n".join(psych_report_lines) if psych_report_lines else "No psychiatric lab/scale data provided."

    # ── Build psychologist findings text ──────────────────────
    if has_psychological:
        psychologist_text = (
            f"Facial Analysis: {psych_eval.get('facial', 'N/A')}\n"
            f"Conversation Analysis: {psych_eval.get('conversation', 'N/A')}\n"
            f"Agent Conclusion: {psych_eval.get('conclusion', 'N/A')}"
        )
    else:
        psychologist_text = "No psychologist session evaluation available."

    # ── Display source data previews ─────────────────────────
    st.markdown("##### 🧠 Psychologist Session Evaluation")
    if has_psychological:
        with st.expander("View Psychologist Findings", expanded=False):
            st.write(psych_eval.get("facial", ""))
            st.write(psych_eval.get("conversation", ""))
            st.markdown(f"**Agent Conclusion:** {psych_eval.get('conclusion', 'N/A')}")
    else:
        st.info("No psychologist session data. You can still generate a diagnosis from psychiatric data alone.")

    st.markdown("##### ⚕️ Psychiatrist Lab/Scale Report")
    if has_psychiatric:
        with st.expander("View Psychiatrist Findings", expanded=False):
            for line in psych_report_lines:
                st.caption(line)
    else:
        st.info("No psychiatric lab data. You can still generate a diagnosis from the psychological session alone.")

    # Show which sources are active
    sources = []
    if has_psychological:
        sources.append("🧠 Psychological Session")
    if has_psychiatric:
        sources.append("⚕️ Psychiatric Lab Data")
    st.caption(f"**Active data sources:** {' + '.join(sources)}")

    st.divider()

    # ── Generate combined AI summary ─────────────────────────
    if st.button("🧬 Generate Integrated Diagnosis & Recommendations", use_container_width=True):
        try:
            from langchain_groq import ChatGroq
            from langchain_core.messages import SystemMessage, HumanMessage
            from config import get_config
            CFG = get_config()

            llm = ChatGroq(api_key=CFG.GROQ_API_KEY, model_name=CFG.GROQ_MODEL, temperature=0.2)

            # Adapt the system prompt based on which data sources are available
            if has_psychological and has_psychiatric:
                system_prompt = (
                    "You are a senior clinical psychiatrist reviewing two reports for the same patient:\n"
                    "1. A PSYCHOLOGIST SESSION REPORT based on a conversational interview and facial expression analysis.\n"
                    "2. A PSYCHIATRIST LAB/SCALE REPORT based on clinical biomarkers and standardized psychiatric scales.\n\n"
                    "Your task:\n"
                    "- Cross-reference findings from both reports.\n"
                    "- Identify the most likely diagnosis or diagnoses.\n"
                    "- Explain how the two reports corroborate or contradict each other.\n"
                    "- Provide clear, actionable next steps (therapy type, medication considerations, referrals, lifestyle changes).\n"
                    "- Use professional clinical language but keep it readable.\n"
                    "- Structure your response with clear headings: Integrated Diagnosis, Corroborating Evidence, Recommended Treatment Plan.\n"
                )
            elif has_psychological:
                system_prompt = (
                    "You are a senior clinical psychiatrist reviewing a PSYCHOLOGIST SESSION REPORT for a patient.\n"
                    "The report is based on a conversational interview and facial expression analysis.\n"
                    "No psychiatric lab or scale data is available at this time.\n\n"
                    "Your task:\n"
                    "- Based solely on the psychological session data, identify the most likely diagnosis or diagnoses.\n"
                    "- Note any red flags or areas that warrant further psychiatric investigation (lab tests, scales).\n"
                    "- Provide clear, actionable next steps (therapy type, medication considerations, referrals, lifestyle changes).\n"
                    "- Use professional clinical language but keep it readable.\n"
                    "- Structure your response with clear headings: Preliminary Diagnosis, Key Observations, Recommended Next Steps, Suggested Lab Tests.\n"
                )
            else:
                system_prompt = (
                    "You are a senior clinical psychiatrist reviewing a PSYCHIATRIST LAB/SCALE REPORT for a patient.\n"
                    "The report is based on clinical biomarkers and standardized psychiatric scales.\n"
                    "No psychological session data (interview/facial analysis) is available at this time.\n\n"
                    "Your task:\n"
                    "- Based solely on the lab/scale data, identify the most likely diagnosis or diagnoses.\n"
                    "- Note any areas where a psychological interview would help clarify the clinical picture.\n"
                    "- Provide clear, actionable next steps (therapy type, medication considerations, referrals, lifestyle changes).\n"
                    "- Use professional clinical language but keep it readable.\n"
                    "- Structure your response with clear headings: Preliminary Diagnosis, Lab Findings Analysis, Recommended Treatment Plan, Recommended Psychological Assessment.\n"
                )

            user_prompt = (
                f"=== PSYCHOLOGIST SESSION REPORT ===\n{psychologist_text}\n\n"
                f"=== PSYCHIATRIST LAB/SCALE REPORT ===\n{psychiatrist_text}\n\n"
                "Please provide a clinical diagnosis and recommendations."
            )

            with st.spinner("🧬 Generating integrated clinical summary..."):
                response = llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])

            st.session_state["integrated_summary"] = response.content

            # ── AUTO-SAVE to database ────────────────────────
            try:
                from utils.db import update_report_integrated, update_report_psychiatrist, update_report_severity, get_latest_report_id, save_report

                user_id = st.session_state.get("user_id")
                report_id = st.session_state.get("current_report_id")

                # ── Calculate severity based on available data ──
                psych_severity = 0.0
                if hasattr(st.session_state, "fusion_engine"):
                    live = st.session_state.fusion_engine.get_state()
                    psych_severity = live.get('average_severity_score', 0.0)
                elif "clinical_state" in st.session_state:
                    psych_severity = st.session_state.clinical_state.get("average_severity_score", 0.0)

                total_params = len(abnormal) + len(normal)
                psychiatric_severity = len(abnormal) / total_params if total_params > 0 else 0.0

                # Adaptive blending based on available sources
                if has_psychological and has_psychiatric:
                    # Both: 50/50
                    blended_severity = (psych_severity * 0.50) + (psychiatric_severity * 0.50)
                elif has_psychological:
                    # Psychological only: 60% facial + 40% text (already in psych_severity)
                    blended_severity = psych_severity
                else:
                    # Psychiatric only
                    blended_severity = psychiatric_severity

                blended_severity = min(1.0, max(0.0, blended_severity))

                # Prepare psychiatrist data dicts
                params_dict = {e["param"]: e["value"] for e in abnormal + normal} if has_psychiatric else {}
                abnormal_list = [{"param": e["param"], "value": e["value"], "disorder": e["disorder"], "solution": e["solution"]} for e in abnormal] if has_psychiatric else []

                if user_id and report_id:
                    if has_psychiatric:
                        update_report_psychiatrist(report_id, params_dict, abnormal_list)
                    update_report_integrated(report_id, response.content)
                    update_report_severity(report_id, blended_severity)
                elif user_id:
                    eval_data = st.session_state.get("evaluation_result", {})
                    rid = save_report(
                        user_id=user_id,
                        psychologist_facial=eval_data.get("facial", ""),
                        psychologist_conversation=eval_data.get("conversation", ""),
                        psychologist_conclusion=eval_data.get("conclusion", ""),
                        psychiatrist_params=params_dict,
                        psychiatrist_abnormalities=abnormal_list,
                        integrated_summary=response.content,
                        avg_severity=blended_severity,
                    )
                    st.session_state["current_report_id"] = rid
            except Exception as db_err:
                st.caption(f"⚠️ DB save note: {db_err}")

        except Exception as e:
            st.error(f"⚠️ Failed to generate summary: {e}")

    # Display persisted summary
    if "integrated_summary" in st.session_state:
        st.markdown("---")
        st.markdown("#### 🩺 Integrated Clinical Assessment")
        st.write(st.session_state["integrated_summary"])

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Disclaimer ────────────────────────────────────────────
    st.caption(
        "⚖️ **Disclaimer:** This automated report is for clinical triage purposes only "
        "and does not constitute a formal medical diagnosis. Always consult a licensed practitioner."
    )
