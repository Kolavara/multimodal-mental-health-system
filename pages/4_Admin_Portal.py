import streamlit as st
import os
import json
from datetime import datetime

st.set_page_config(page_title="Admin Portal", page_icon="🔑", layout="wide")

# Load custom CSS
css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

from utils.db import init_db, get_all_users, get_reports_for_user, get_user_report_count, get_user_latest_report
init_db()

# ── Auth Guard ────────────────────────────────────────────────
if not st.session_state.get("logged_in") or st.session_state.get("role") != "admin":
    st.warning("🔒 Access Denied — Administrator login required.")
    st.caption("Please go to the main page and log in as an administrator.")
    st.stop()

# ── Page Title ────────────────────────────────────────────────
st.title("🔑 Administrator Portal")
st.caption(f"Logged in as **{st.session_state.get('display_name', 'Admin')}**")

# ── Fetch all users ──────────────────────────────────────────
users = get_all_users(role="user")

if not users:
    st.markdown('<div class="neu-card">', unsafe_allow_html=True)
    st.info("No registered patients found. Users will appear here after they complete a session.")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# ══════════════════════════════════════════════════════════════
# VIEW MODE: Patient Detail (selected patient's reports)
# ══════════════════════════════════════════════════════════════
if "admin_selected_user" in st.session_state:
    selected_user_id = st.session_state["admin_selected_user"]
    selected_user_name = st.session_state.get("admin_selected_name", "Patient")

    # Back button
    if st.button("← Back to All Patients", key="back_btn"):
        del st.session_state["admin_selected_user"]
        if "admin_selected_name" in st.session_state:
            del st.session_state["admin_selected_name"]
        st.rerun()

    # User info card
    from utils.db import get_all_users as _gau
    all_u = _gau(role="user")
    user_info = next((u for u in all_u if u["id"] == selected_user_id), None)

    if user_info:
        try:
            created = datetime.fromisoformat(user_info["created_at"]).strftime("%B %d, %Y")
        except:
            created = user_info.get("created_at", "Unknown")

        st.markdown(f"""
        <div style="
            background: var(--bg-base);
            border-radius: var(--radius-card);
            padding: 1.25rem 2rem;
            margin-bottom: 1.5rem;
            box-shadow: var(--extruded);
            display: flex;
            align-items: center;
            gap: 1.25rem;
        ">
            <div style="
                width: 60px; height: 60px; border-radius: 50%;
                background: linear-gradient(135deg, var(--accent-primary), var(--accent-light));
                display: flex; align-items: center; justify-content: center;
                box-shadow: var(--extruded-small); flex-shrink: 0;
            ">
                <span style="font-size: 1.6rem; color: #fff;">👤</span>
            </div>
            <div>
                <h3 style="margin:0;font-size:1.3rem;">{user_info['display_name']}</h3>
                <p style="margin:0.15rem 0;font-size:0.8rem;color:var(--text-muted);">
                    @{user_info['username']} • Registered: {created}
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    reports = get_reports_for_user(selected_user_id)

    if not reports:
        st.markdown('<div class="neu-card">', unsafe_allow_html=True)
        st.info("No reports found for this patient yet.")
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

    st.caption(f"Showing {len(reports)} report(s), newest first")


    # ── Vertical scrollable list of reports ───────────────────
    for i, report in enumerate(reports):
        # Parse timestamp
        try:
            ts = datetime.fromisoformat(report["timestamp"])
            ts_str = ts.strftime("%B %d, %Y — %I:%M %p")
        except:
            ts_str = report["timestamp"]

        # Severity badge color
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

        # Detect which analyses are present
        has_psych = bool(report.get("psychologist_conclusion", ""))
        has_psychiatrist = bool(report.get("psychiatrist_params", "")) and report.get("psychiatrist_params", "{}") != "{}"
        has_integrated = bool(report.get("integrated_summary", ""))

        badge_style = "display:inline-block;padding:0.15rem 0.5rem;border-radius:12px;font-size:0.6rem;font-weight:700;margin-right:0.35rem;"
        psych_badge = f'<span style="{badge_style}background:{"#C6F6D5" if has_psych else "#EDF2F7"};color:{"#276749" if has_psych else "#A0AEC0"};">🧠 Psychologist {"✓" if has_psych else "—"}</span>'
        psychiatrist_badge = f'<span style="{badge_style}background:{"#BEE3F8" if has_psychiatrist else "#EDF2F7"};color:{"#2B6CB0" if has_psychiatrist else "#A0AEC0"};">⚕️ Psychiatrist {"✓" if has_psychiatrist else "—"}</span>'
        integrated_badge = f'<span style="{badge_style}background:{"#E9D8FD" if has_integrated else "#EDF2F7"};color:{"#553C9A" if has_integrated else "#A0AEC0"};">🧬 Integrated {"✓" if has_integrated else "—"}</span>'

        # Report card
        st.markdown(f"""
        <div style="
            background: var(--bg-base);
            border-radius: var(--radius-card);
            padding: 1.5rem 2rem;
            margin-bottom: 1.25rem;
            box-shadow: var(--extruded);
        ">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
                <div>
                    <span style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em;">
                        Session #{len(reports) - i}
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


        # Expandable sections inside Streamlit (below the HTML header)
        with st.expander(f"🧠 Psychologist Findings — Session #{len(reports) - i}", expanded=False):
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

        with st.expander(f"⚕️ Psychiatrist Findings — Session #{len(reports) - i}", expanded=False):
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

        with st.expander(f"🧬 Integrated Summary — Session #{len(reports) - i}", expanded=i == 0):
            integrated = report.get("integrated_summary", "")
            if integrated:
                st.write(integrated)
            else:
                st.caption("No integrated summary generated for this session.")

        st.markdown("---")

    st.stop()


# ══════════════════════════════════════════════════════════════
# VIEW MODE: Patient Card Grid (default)
# ══════════════════════════════════════════════════════════════

st.markdown(f"### 👥 Registered Patients ({len(users)})")

# Create card grid — 3 per row
cols_per_row = 3
for row_start in range(0, len(users), cols_per_row):
    row_users = users[row_start:row_start + cols_per_row]
    cols = st.columns(cols_per_row)

    for col_idx, user in enumerate(row_users):
        with cols[col_idx]:
            user_id = user["id"]
            name = user["display_name"]
            username = user["username"]
            report_count = get_user_report_count(user_id)
            latest = get_user_latest_report(user_id)

            # Determine severity badge
            if latest:
                sev = latest.get("avg_severity", 0.0)
                disorder = latest.get("likely_disorder", "Unknown")
                try:
                    last_ts = datetime.fromisoformat(latest["timestamp"])
                    last_date = last_ts.strftime("%b %d, %Y")
                except:
                    last_date = "Unknown"
            else:
                sev = 0.0
                disorder = "N/A"
                last_date = "No sessions"

            if sev >= 0.7:
                sev_color = "var(--accent-danger)"
                sev_label = "HIGH"
                badge_bg = "#FED7D7"
            elif sev >= 0.3:
                sev_color = "#D69E2E"
                sev_label = "MODERATE"
                badge_bg = "#FEFCBF"
            else:
                sev_color = "var(--accent-success)"
                sev_label = "LOW"
                badge_bg = "#C6F6D5"

            # Card HTML
            st.markdown(f"""
            <div style="
                background: var(--bg-base);
                border-radius: var(--radius-card);
                padding: 1.5rem;
                box-shadow: var(--extruded);
                text-align: center;
                min-height: 220px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                margin-bottom: 1rem;
            ">
                <div>
                    <div style="
                        width: 56px; height: 56px; border-radius: 50%;
                        background: linear-gradient(135deg, var(--accent-primary), var(--accent-light));
                        display: flex; align-items: center; justify-content: center;
                        margin: 0 auto 0.75rem;
                        box-shadow: var(--extruded-small);
                    ">
                        <span style="font-size: 1.5rem; color: #fff;">👤</span>
                    </div>
                    <h4 style="margin:0;font-size:1.05rem;">{name}</h4>
                    <p style="font-size:0.75rem;color:var(--text-muted);margin:0.25rem 0;">@{username}</p>
                </div>
                <div style="margin-top:0.75rem;">
                    <div style="display:flex;justify-content:space-around;margin-bottom:0.5rem;">
                        <div>
                            <span style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">Sessions</span><br>
                            <span style="font-weight:700;font-size:1.1rem;">{report_count}</span>
                        </div>
                        <div>
                            <span style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">Risk</span><br>
                            <span style="font-weight:700;font-size:0.85rem;color:{sev_color};">{sev_label}</span>
                        </div>
                    </div>
                    <p style="font-size:0.7rem;color:var(--text-muted);margin:0;">Last: {last_date}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Click button
            if st.button(f"View Reports", key=f"view_{user_id}", use_container_width=True):
                st.session_state["admin_selected_user"] = user_id
                st.session_state["admin_selected_name"] = name
                st.rerun()
