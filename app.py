import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="NOC Maintenance System",
    page_icon="📡",
    layout="wide"
)

# ---------------- Custom styling ----------------
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #0f2027, #203a43, #2c5364);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .main-header h1 {
        color: white;
        margin: 0;
    }
    .main-header p {
        color: #cfd8dc;
        margin: 0.3rem 0 0 0;
    }
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] div {
        color: #1b2a38 !important;
    }
    .status-badge {
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        color: white;
    }
    .badge-open { background-color: #e63946; }
    .badge-progress { background-color: #f4a261; }
    .badge-resolved { background-color: #2a9d8f; }
    .badge-closed { background-color: #6c757d; }
    section[data-testid="stSidebar"] {
        background-color: #1b2a38;
    }
    section[data-testid="stSidebar"] * {
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- Database setup ----------------
conn = sqlite3.connect("noc_maintenance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tt_id TEXT UNIQUE,
    site_id TEXT,
    region TEXT,
    alarm_type TEXT,
    priority TEXT,
    status TEXT,
    fe_name TEXT,
    opened_at TEXT,
    resolved_at TEXT
)
""")
conn.commit()

existing_cols = [row[1] for row in cursor.execute("PRAGMA table_info(tickets)")]
new_columns = {
    "alarm_time": "TEXT",
    "utin_verification": "TEXT",
    "verification_result": "TEXT",
    "notes": "TEXT",
}
for col, col_type in new_columns.items():
    if col not in existing_cols:
        cursor.execute(f"ALTER TABLE tickets ADD COLUMN {col} {col_type}")
conn.commit()

# ---------------- Sidebar navigation ----------------
st.sidebar.title("📡 NOC Maintenance")
page = st.sidebar.radio(
    "Navigate",
    ["📊 Dashboard", "➕ New Trouble Ticket", "📋 Trouble Tickets", "🔍 Alarm Verification"]
)

df = pd.read_sql_query("SELECT * FROM tickets", conn)


def status_badge_html(status):
    css_class = {
        "Open": "badge-open",
        "In Progress": "badge-progress",
        "Resolved": "badge-resolved",
        "Closed": "badge-closed",
    }.get(status, "badge-closed")
    return f'<span class="status-badge {css_class}">{status}</span>'


# ==================================================
# PAGE 1 — DASHBOARD
# ==================================================
if page == "📊 Dashboard":
    st.markdown("""
    <div class="main-header">
        <h1>📡 NOC Maintenance Dashboard</h1>
        <p>Real-time overview of Trouble Tickets and alarm activity</p>
    </div>
    """, unsafe_allow_html=True)

    total_tts = len(df)
    open_tts = len(df[df["status"] == "Open"]) if not df.empty else 0
    in_progress_tts = len(df[df["status"] == "In Progress"]) if not df.empty else 0
    resolved_tts = len(df[df["status"].isin(["Resolved", "Closed"])]) if not df.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total TTs", total_tts)
    col2.metric("Open", open_tts)
    col3.metric("In Progress", in_progress_tts)
    col4.metric("Resolved / Closed", resolved_tts)

    st.write("")
    st.subheader("📊 Most Common Alarm Types")
    if not df.empty and df["alarm_type"].notna().any():
        alarm_counts = df["alarm_type"].value_counts()
        st.bar_chart(alarm_counts)
    else:
        st.info("No alarm data yet.")

    st.subheader("🕒 Recent Trouble Tickets")
    if not df.empty:
        recent = df.sort_values("opened_at", ascending=False).head(5).copy()
        recent["status"] = recent["status"].apply(status_badge_html)
        st.write(
            recent[["tt_id", "site_id", "alarm_type", "priority", "status", "opened_at"]]
            .to_html(escape=False, index=False),
            unsafe_allow_html=True
        )
    else:
        st.info("No tickets yet. Create one from the 'New Trouble Ticket' page.")

# ==================================================
# PAGE 2 — NEW TROUBLE TICKET
# ==================================================
elif page == "➕ New Trouble Ticket":
    st.markdown("""
    <div class="main-header">
        <h1>➕ New Trouble Ticket</h1>
        <p>Log a new alarm and open a Trouble Ticket</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("new_tt_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            tt_id = st.text_input("TT ID")
            site_id = st.text_input("Site ID")
            region = st.text_input("Region")
            alarm_type = st.text_input("Alarm Type")
            alarm_time = st.text_input("Alarm Time (e.g. 2026-09-24 10:30)")

        with col2:
            utin_verification = st.selectbox("UTin Verification", ["Active", "Not Detected", "Flapping"])
            verification_result = st.selectbox(
                "Verification Result",
                ["Possible Genuine Alarm", "Possible False Alarm", "Possible Flapping Alarm", "Not Verified Yet"]
            )
            fe_name = st.text_input("FE Name")
            priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
            status = st.selectbox("Status", ["Open", "In Progress", "Resolved", "Closed"])

        notes = st.text_area("Notes")

        submitted = st.form_submit_button("✅ Create TT")

        if submitted:
            if not tt_id or not site_id:
                st.error("TT ID required", icon=":material/error:")
            else:
                try:
                    opened_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO tickets (
                            tt_id, site_id, region, alarm_type, priority, status,
                            fe_name, opened_at, alarm_time, utin_verification,
                            verification_result, notes
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        tt_id, site_id, region, alarm_type, priority, status,
                        fe_name, opened_at, alarm_time, utin_verification,
                        verification_result, notes
                    ))
                    conn.commit()
                    st.success(f"Ticket {tt_id} created successfully!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"TT ID '{tt_id}' already exists. Use a unique ID.")

# ==================================================
# PAGE 3 — TROUBLE TICKETS (view / search / update)
# ==================================================
elif page == "📋 Trouble Tickets":
    st.markdown("""
    <div class="main-header">
        <h1>📋 Trouble Tickets</h1>
        <p>Search, review, and update ticket statuses</p>
    </div>
    """, unsafe_allow_html=True)

    search_term = st.text_input("🔍 Search by TT ID, Site ID, or Alarm Type")

    filtered_df = df.copy()
    if search_term:
        mask = (
            df["tt_id"].str.contains(search_term, case=False, na=False)
            | df["site_id"].str.contains(search_term, case=False, na=False)
            | df["alarm_type"].str.contains(search_term, case=False, na=False)
        )
        filtered_df = df[mask]

    if not filtered_df.empty:
        display_df = filtered_df.copy()
        display_df["status"] = display_df["status"].apply(status_badge_html)
        st.write(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.info("No matching tickets found.")

    st.write("")
    st.subheader("🔄 Update Ticket Status")
    if not df.empty:
        selected_tt = st.selectbox("Select TT ID", df["tt_id"])
        new_status = st.selectbox("New Status", ["Open", "In Progress", "Resolved", "Closed"])

        if st.button("Update Status"):
            resolved_at = None
            if new_status in ["Resolved", "Closed"]:
                resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                UPDATE tickets
                SET status = ?, resolved_at = COALESCE(?, resolved_at)
                WHERE tt_id = ?
            """, (new_status, resolved_at, selected_tt))
            conn.commit()
            st.success(f"Ticket {selected_tt} updated to '{new_status}'.")
            st.rerun()
    else:
        st.info("No tickets available to update.")

# ==================================================
# PAGE 4 — ALARM VERIFICATION (rule-based)
# ==================================================
elif page == "🔍 Alarm Verification":
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Alarm Verification</h1>
        <p>Rule-based check for genuine, false, or flapping alarms</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("alarm_verification_form"):
        col1, col2 = st.columns(2)
        with col1:
            site = st.text_input("Site ID")
            alarm_type = st.text_input("Alarm Type")
        with col2:
            rtcm_status = st.selectbox("RTCM Status", ["Active", "Cleared"])
            utin_status = st.selectbox("UTin Status", ["Active", "Not Detected", "Flapping"])

        check = st.form_submit_button("🔎 Verify Alarm")

        if check:
            if not site.strip() or not alarm_type.strip():
                st.error("Please fill in both Site ID and Alarm Type before verifying.")
            else:
                if rtcm_status == "Active" and utin_status == "Active":
                    result = "✅ Possible Genuine Alarm"
                    st.success(result)
                elif rtcm_status == "Active" and utin_status == "Flapping":
                    result = "⚠️ Possible Flapping Alarm"
                    st.warning(result)
                elif rtcm_status == "Active" and utin_status == "Not Detected":
                    result = "❓ Mismatch — Possible False Alarm (RTCM active but UTin not detecting)"
                    st.warning(result)
                elif rtcm_status == "Cleared" and utin_status == "Active":
                    result = "❓ Mismatch — Possible False Alarm (RTCM cleared but UTin still active)"
                    st.warning(result)
                elif rtcm_status == "Cleared" and utin_status == "Flapping":
                    result = "⚠️ Possible Flapping Alarm"
                    st.warning(result)
                else:
                    result = "❌ Possible False Alarm"
                    st.error(result)

                st.write(f"**Site:** {site} | **Alarm Type:** {alarm_type}")
                st.write(f"**Suggested Result:** {result}")
conn.close()