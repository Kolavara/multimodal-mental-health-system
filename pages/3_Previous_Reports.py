import streamlit as st
import os
import json
from datetime import datetime

st.set_page_config(page_title="Previous Reports", page_icon="📂", layout="wide")

# Load custom CSS
css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Auth guard
if not st.session_state.get("logged_in"):
    st.warning("🔒 Please log in from the main page first.")
    st.stop()

from utils.ui import apply_role_based_sidebar
apply_role_based_sidebar()

# Hide from admin
if st.session_state.get("role") == "admin":
    st.warning("This page is for patients only.")
    st.stop()

from utils.db import init_db, get_reports_for_user
init_db()

# ── Page Title ────────────────────────────────────────────────
st.title("📂 Previous Reports")
st.caption(f"Report history for **{st.session_state.get('display_name', 'User')}**")

# ── Fetch reports ─────────────────────────────────────────────
user_id = st.session_state.get("user_id")
reports = get_reports_for_user(user_id)

if not reports:
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.info("📭 No reports yet. Complete a session on the main page and click 'End Session & Evaluate' to generate your first report.")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════
# SUMMARY DASHBOARD
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="neu-card">', unsafe_allow_html=True)
st.markdown('<p class="section-header">📊 Your Summary</p>', unsafe_allow_html=True)

# Calculate summary stats
total_sessions = len(reports)
severities = [r.get("avg_severity", 0.0) for r in reports]
avg_risk = sum(severities) / len(severities) if severities else 0.0

# Count analysis types
psych_count = sum(1 for r in reports if r.get("psychologist_conclusion", ""))
psychiatrist_count = sum(1 for r in reports if r.get("psychiatrist_params", "{}") != "{}" and r.get("psychiatrist_params", ""))
integrated_count = sum(1 for r in reports if r.get("integrated_summary", ""))

# Latest session date
try:
    latest_date = datetime.fromisoformat(reports[0]["timestamp"]).strftime("%b %d, %Y")
except:
    latest_date = "Unknown"

# Risk label
if avg_risk >= 0.7:
    risk_label = "HIGH"
elif avg_risk >= 0.3:
    risk_label = "MODERATE"
else:
    risk_label = "LOW"

# Layout: metrics on left, chart on right
import altair as alt
import pandas as pd

left_col, right_col = st.columns([3, 2])

with left_col:
    # Metrics in 2x2 grid
    s1, s2 = st.columns(2)
    with s1:
        st.metric("Total Sessions", total_sessions)
    with s2:
        st.metric("Avg Risk Level", f"{risk_label} ({avg_risk:.0%})")

    s3, s4 = st.columns(2)
    with s3:
        st.metric("Last Visit", latest_date)
    with s4:
        st.metric("Integrated Reports", integrated_count)

    # Analysis breakdown dots
    st.markdown(f"""
    <div style="display:flex;gap:1.5rem;margin-top:0.5rem;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:0.4rem;">
            <span style="width:10px;height:10px;border-radius:50%;background:#48BB78;display:inline-block;"></span>
            <span style="font-size:0.8rem;color:var(--text-muted);">Psychologist: <strong>{psych_count}</strong></span>
        </div>
        <div style="display:flex;align-items:center;gap:0.4rem;">
            <span style="width:10px;height:10px;border-radius:50%;background:#4299E1;display:inline-block;"></span>
            <span style="font-size:0.8rem;color:var(--text-muted);">Psychiatrist: <strong>{psychiatrist_count}</strong></span>
        </div>
        <div style="display:flex;align-items:center;gap:0.4rem;">
            <span style="width:10px;height:10px;border-radius:50%;background:#9F7AEA;display:inline-block;"></span>
            <span style="font-size:0.8rem;color:var(--text-muted);">Integrated: <strong>{integrated_count}</strong></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with right_col:
    # Compact Risk Level Trend chart
    if total_sessions >= 1:
        chart_data = []
        for idx, r in enumerate(reversed(reports)):
            sev_val = r.get("avg_severity", 0.0)
            chart_data.append({
                "Session": idx + 1,
                "Risk (%)": round(sev_val * 100, 1),
            })
        df = pd.DataFrame(chart_data)

        line = alt.Chart(df).mark_line(
            color="#667eea", strokeWidth=2.5, interpolate="monotone"
        ).encode(
            x=alt.X("Session:Q", title="Session #",
                     axis=alt.Axis(tickMinStep=1, labelFontSize=9, titleFontSize=10, grid=False)),
            y=alt.Y("Risk (%):Q", title="Risk %",
                     scale=alt.Scale(domain=[0, 100]),
                     axis=alt.Axis(labelFontSize=9, titleFontSize=10, gridColor="#e2e8f0", gridOpacity=0.3)),
        )

        dots = alt.Chart(df).mark_circle(
            size=45, color="#667eea", opacity=0.95
        ).encode(
            x="Session:Q",
            y="Risk (%):Q",
            tooltip=["Session:Q", "Risk (%):Q"],
        )

        # Danger threshold at 70%
        threshold = alt.Chart(pd.DataFrame({"y": [70]})).mark_rule(
            color="#E53E3E", strokeDash=[4, 3], opacity=0.45
        ).encode(y="y:Q")

        chart = (line + dots + threshold).properties(
            height=170,
            title=alt.Title("Risk Level Trend", fontSize=11, color="#4A5568"),
        ).configure_view(strokeWidth=0).configure(background="transparent")

        st.altair_chart(chart, use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# REPORT CARDS (vertical, newest first)
# ══════════════════════════════════════════════════════════════
st.markdown(f"### 📋 All Reports ({total_sessions})")

for i, report in enumerate(reports):
    # Parse timestamp
    try:
        ts = datetime.fromisoformat(report["timestamp"])
        ts_str = ts.strftime("%B %d, %Y — %I:%M %p")
    except:
        ts_str = report["timestamp"]

    # Severity
    sev = report.get("avg_severity", 0.0)
    if sev >= 0.7:
        sev_color = "var(--accent-danger)"
        sev_label = "HIGH RISK"
    elif sev >= 0.3:
        sev_color = "#D69E2E"
        sev_label = "MODERATE"
    else:
        sev_color = "var(--accent-success)"
        sev_label = "LOW RISK"

    disorder = report.get("likely_disorder", "Unknown")

    # Analysis type badges
    has_psych = bool(report.get("psychologist_conclusion", ""))
    has_psychiatrist = bool(report.get("psychiatrist_params", "")) and report.get("psychiatrist_params", "{}") != "{}"
    has_integrated = bool(report.get("integrated_summary", ""))

    badge_style = "display:inline-block;padding:0.15rem 0.5rem;border-radius:12px;font-size:0.6rem;font-weight:700;margin-right:0.35rem;"
    psych_badge = f'<span style="{badge_style}background:{"#C6F6D5" if has_psych else "#EDF2F7"};color:{"#276749" if has_psych else "#A0AEC0"};">🧠 Psychologist {"✓" if has_psych else "—"}</span>'
    psychiatrist_badge = f'<span style="{badge_style}background:{"#BEE3F8" if has_psychiatrist else "#EDF2F7"};color:{"#2B6CB0" if has_psychiatrist else "#A0AEC0"};">⚕️ Psychiatrist {"✓" if has_psychiatrist else "—"}</span>'
    integrated_badge = f'<span style="{badge_style}background:{"#E9D8FD" if has_integrated else "#EDF2F7"};color:{"#553C9A" if has_integrated else "#A0AEC0"};">🧬 Integrated {"✓" if has_integrated else "—"}</span>'

    # Card header
    st.markdown(f"""
    <div style="
        background: var(--bg-base);
        border-radius: var(--radius-card);
        padding: 1.5rem 2rem;
        margin-bottom: 0.5rem;
        box-shadow: var(--extruded);
    ">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
            <div>
                <span style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em;">
                    Session #{total_sessions - i}
                </span>
                <h4 style="margin:0.25rem 0;font-size:1.1rem;">📅 {ts_str}</h4>
            </div>
            <div style="display:flex;gap:0.75rem;align-items:center;">
                <span style="
                    background:{sev_color};color:#fff;padding:0.25rem 0.75rem;
                    border-radius:20px;font-size:0.7rem;font-weight:700;letter-spacing:0.05em;
                ">{sev_label} ({sev:.0%})</span>
                <span style="
                    background:var(--accent-primary);color:#fff;padding:0.25rem 0.75rem;
                    border-radius:20px;font-size:0.7rem;font-weight:600;
                ">{disorder}</span>
            </div>
        </div>
        <div style="margin-top:0.25rem;">
            {psych_badge}{psychiatrist_badge}{integrated_badge}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Expandable detail sections
    with st.expander(f"🧠 Psychologist Findings — Session #{total_sessions - i}", expanded=False):
        psych_facial = report.get("psychologist_facial", "")
        psych_convo = report.get("psychologist_conversation", "")
        psych_conclusion = report.get("psychologist_conclusion", "")

        if psych_facial or psych_convo or psych_conclusion:
            if psych_facial:
                st.markdown("**Facial Analysis:**")
                st.write(psych_facial)
            if psych_convo:
                st.markdown("**Conversation Analysis:**")
                st.write(psych_convo)
            if psych_conclusion:
                st.markdown("**Agent Conclusion:**")
                st.write(psych_conclusion)
        else:
            st.caption("No psychologist data recorded for this session.")

    with st.expander(f"⚕️ Psychiatrist Findings — Session #{total_sessions - i}", expanded=False):
        try:
            params = json.loads(report.get("psychiatrist_params", "{}"))
            abnormalities = json.loads(report.get("psychiatrist_abnormalities", "[]"))
        except:
            params = {}
            abnormalities = []

        if params:
            st.markdown("**Parameters:**")
            for param, value in params.items():
                st.caption(f"• **{param}**: {value}")
        if abnormalities:
            st.markdown("**Abnormalities:**")
            for abn in abnormalities:
                st.warning(f"⚠️ **{abn.get('param', '?')}** = {abn.get('value', '?')} → {abn.get('disorder', 'Unknown')}")
                st.caption(f"Recommended: {abn.get('solution', 'Consult specialist')}")
        if not params and not abnormalities:
            st.caption("No psychiatrist data recorded for this session.")

    with st.expander(f"🧬 Integrated Summary — Session #{total_sessions - i}", expanded=(i == 0 and has_integrated)):
        integrated = report.get("integrated_summary", "")
        if integrated:
            st.write(integrated)
        else:
            st.caption("No integrated summary generated for this session.")

    st.markdown("<div style='margin-bottom:1.5rem;'></div>", unsafe_allow_html=True)

# Footer
st.divider()
st.caption(
    "⚖️ **Disclaimer:** These reports are for clinical reference purposes only "
    "and do not constitute a formal medical diagnosis."
)
