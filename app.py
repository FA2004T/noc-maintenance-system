"""
NOC Maintenance System
-----------------------
A Streamlit application for logging, tracking, and verifying network
Trouble Tickets (TTs) in a Network Operations Center (NOC).

Requires: streamlit >= 1.31 (for st.dialog modals)
Run with:
    streamlit run noc_maintenance_app.py
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, date

import pandas as pd
import streamlit as st

# =====================================================================
# CONFIG / CONSTANTS
# =====================================================================

DB_PATH = "noc_maintenance.db"

STATUS_OPTIONS = ["Open", "In Progress", "Resolved", "Closed"]
PRIORITY_OPTIONS = ["Low", "Medium", "High", "Critical"]
UTIN_OPTIONS = ["Active", "Not Detected", "Flapping"]
VERIFICATION_OPTIONS = [
    "Possible Genuine Alarm",
    "Possible False Alarm",
    "Possible Flapping Alarm",
    "Not Verified Yet",
]

STATUS_COLORS = {"Open": "#e63946", "In Progress": "#f4a261", "Resolved": "#2a9d8f", "Closed": "#6c757d"}
PRIORITY_COLORS = {"Low": "#4895ef", "Medium": "#f4a261", "High": "#e76f51", "Critical": "#d00000"}

NAV_ITEMS = [
    ("Dashboard", "📊"),
    ("New Ticket", "➕"),
    ("Tickets", "📋"),
    ("Verification", "🔍"),
]

st.set_page_config(page_title="NOC Maintenance System", page_icon="📡", layout="wide", initial_sidebar_state="expanded")

# =====================================================================
# STYLING — real visual identity, not just tweaks
# =====================================================================

st.markdown(
    """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    #MainMenu, footer, header {visibility: hidden;}

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .block-container { padding-top: 1.2rem; max-width: 1200px; }

    /* ---- Hero banner ---- */
    .hero {
        background: radial-gradient(circle at 20% 20%, #274156 0%, #0f2027 60%);
        padding: 1.9rem 2.2rem;
        border-radius: 18px;
        margin-bottom: 1.4rem;
        position: relative;
        overflow: hidden;
    }
    .hero::after {
        content: "";
        position: absolute; top: -40%; right: -10%;
        width: 260px; height: 260px; border-radius: 50%;
        background: radial-gradient(circle, rgba(56,180,204,0.25), transparent 70%);
    }
    .hero h1 { color: #fff; margin: 0; font-size: 1.7rem; font-weight: 800; letter-spacing: -0.3px; }
    .hero p { color: #b9c6d1; margin: 0.35rem 0 0 0; font-size: 0.95rem; }

    /* ---- Nav pills (rendered via st.button, styled below) ---- */
    div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button {
        border-radius: 999px !important;
        font-weight: 600;
        transition: all 0.15s ease;
    }
    div[data-testid="stButton"] button:hover { transform: translateY(-1px); }

    /* ---- KPI cards ---- */
    .kpi-card {
        background: #fff; border-radius: 14px; padding: 1rem 1.2rem;
        border: 1px solid #ececec; box-shadow: 0 2px 10px rgba(15,32,39,0.05);
        border-left: 5px solid var(--accent, #274156);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .kpi-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(15,32,39,0.1); }
    .kpi-card .kpi-label { font-size: 0.78rem; color: #7a8894; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; }
    .kpi-card .kpi-value { font-size: 1.7rem; font-weight: 800; color: #1b2a38; margin-top: 0.15rem; }

    /* ---- Ticket cards ---- */
    .ticket-card {
        background: #fff; border-radius: 14px; padding: 0.95rem 1.1rem;
        border: 1px solid #ececec; border-left: 6px solid var(--pcolor, #ccc);
        box-shadow: 0 1px 6px rgba(15,32,39,0.04);
        margin-bottom: 0.7rem; transition: box-shadow 0.15s ease, transform 0.15s ease;
    }
    .ticket-card:hover { box-shadow: 0 6px 16px rgba(15,32,39,0.09); transform: translateY(-1px); }
    .ticket-card .tt-top { display: flex; justify-content: space-between; align-items: center; }
    .ticket-card .tt-id { font-weight: 800; color: #1b2a38; font-size: 1rem; }
    .ticket-card .tt-meta { color: #7a8894; font-size: 0.82rem; margin-top: 0.2rem; }
    .badge {
        padding: 3px 11px; border-radius: 999px; font-size: 0.72rem;
        font-weight: 700; color: #fff; display: inline-block; letter-spacing: 0.2px;
    }

    /* ---- Empty state ---- */
    .empty-state {
        text-align: center; padding: 3rem 1rem; background: #fafbfc;
        border: 1.5px dashed #dbe2e8; border-radius: 16px; color: #7a8894;
    }
    .empty-state .icon { font-size: 2.4rem; }

    /* ---- Stepper ---- */
    .step-dot {
        width: 30px; height: 30px; border-radius: 50%; display: inline-flex;
        align-items: center; justify-content: center; font-weight: 700; font-size: 0.85rem;
        color: #fff; background: #d7dee3;
    }
    .step-dot.active { background: #274156; }
    .step-dot.done { background: #2a9d8f; }
    .step-label { font-size: 0.75rem; color: #7a8894; margin-top: 4px; }

    section[data-testid="stSidebar"] { background-color: #12222f; }
    section[data-testid="stSidebar"] * { color: #eef2f5 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# =====================================================================
# DATABASE LAYER
# =====================================================================

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tt_id TEXT UNIQUE, site_id TEXT, region TEXT, alarm_type TEXT,
                priority TEXT, status TEXT, fe_name TEXT, opened_at TEXT, resolved_at TEXT,
                alarm_time TEXT, utin_verification TEXT, verification_result TEXT, notes TEXT
            )
            """
        )
        existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(tickets)")]
        for col, col_type in {"alarm_time": "TEXT", "utin_verification": "TEXT",
                               "verification_result": "TEXT", "notes": "TEXT"}.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {col} {col_type}")


def load_tickets() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM tickets ORDER BY id DESC", conn)
    if not df.empty:
        df["opened_at_dt"] = pd.to_datetime(df["opened_at"], errors="coerce")
        df["resolved_at_dt"] = pd.to_datetime(df["resolved_at"], errors="coerce")
    return df


def generate_tt_id() -> str:
    return f"TT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:5].upper()}"


def insert_ticket(values: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tickets (tt_id, site_id, region, alarm_type, priority, status, fe_name,
                opened_at, alarm_time, utin_verification, verification_result, notes)
            VALUES (:tt_id, :site_id, :region, :alarm_type, :priority, :status, :fe_name,
                :opened_at, :alarm_time, :utin_verification, :verification_result, :notes)
            """,
            values,
        )


def update_ticket_status(tt_id: str, new_status: str):
    resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status in ("Resolved", "Closed") else None
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET status = ?, resolved_at = COALESCE(?, resolved_at) WHERE tt_id = ?",
            (new_status, resolved_at, tt_id),
        )


def update_ticket_full(tt_id: str, values: dict):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tickets SET site_id=:site_id, region=:region, alarm_type=:alarm_type,
                priority=:priority, status=:status, fe_name=:fe_name, notes=:notes
            WHERE tt_id=:tt_id
            """,
            {**values, "tt_id": tt_id},
        )


def delete_ticket(tt_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM tickets WHERE tt_id = ?", (tt_id,))


# =====================================================================
# APP STATE
# =====================================================================

init_db()
if "df" not in st.session_state:
    st.session_state.df = load_tickets()
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "wizard_step" not in st.session_state:
    st.session_state.wizard_step = 1
if "open_ticket" not in st.session_state:
    st.session_state.open_ticket = None


def refresh():
    st.session_state.df = load_tickets()


def go_to(page_name: str):
    st.session_state.page = page_name


df = st.session_state.df

# =====================================================================
# SIDEBAR — quick stats + global search (flow shortcut)
# =====================================================================

st.sidebar.markdown("## 📡 NOC Maintenance")
st.sidebar.caption("Trouble Ticket & Alarm Verification Suite")
st.sidebar.divider()

quick_search = st.sidebar.text_input("🔎 Quick jump to TT ID")
if quick_search:
    match = df[df["tt_id"].str.contains(quick_search, case=False, na=False)] if not df.empty else pd.DataFrame()
    if not match.empty:
        if st.sidebar.button(f"Open {match.iloc[0]['tt_id']}", use_container_width=True):
            st.session_state.open_ticket = match.iloc[0]["tt_id"]
            go_to("Tickets")
            st.rerun()
    else:
        st.sidebar.caption("No match.")

st.sidebar.divider()
st.sidebar.metric("Open Now", int((df["status"] == "Open").sum()) if not df.empty else 0)
st.sidebar.metric("Critical Priority", int((df["priority"] == "Critical").sum()) if not df.empty else 0)
st.sidebar.divider()
st.sidebar.caption(f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# =====================================================================
# TOP NAVBAR — real navigation flow (not a sidebar radio)
# =====================================================================

nav_cols = st.columns(len(NAV_ITEMS))
for col, (name, icon) in zip(nav_cols, NAV_ITEMS):
    is_active = st.session_state.page == name
    if col.button(f"{icon}  {name}", key=f"nav_{name}", use_container_width=True,
                  type="primary" if is_active else "secondary"):
        go_to(name)
        st.rerun()

st.write("")

# =====================================================================
# SHARED UI HELPERS
# =====================================================================

def hero(icon: str, title: str, subtitle: str):
    st.markdown(f'<div class="hero"><h1>{icon} {title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def kpi_card(col, label, value, accent):
    col.markdown(
        f'<div class="kpi-card" style="--accent:{accent}">'
        f'<div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def badge(text, color_map):
    return f'<span class="badge" style="background:{color_map.get(text, "#6c757d")}">{text}</span>'


def empty_state(icon, title, subtitle, cta_label=None, cta_target=None):
    st.markdown(
        f'<div class="empty-state"><div class="icon">{icon}</div>'
        f'<h4>{title}</h4><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )
    if cta_label and cta_target:
        _, c, _ = st.columns([1, 1, 1])
        if c.button(cta_label, use_container_width=True, type="primary"):
            go_to(cta_target)
            st.rerun()


@st.dialog("Ticket Details")
def ticket_modal(tt_id: str):
    row = df[df["tt_id"] == tt_id]
    if row.empty:
        st.warning("This ticket no longer exists.")
        return
    row = row.iloc[0]

    t_view, t_edit = st.tabs(["📄 Details", "✏️ Edit / Update"])

    with t_view:
        st.markdown(
            f"### {row['tt_id']} &nbsp; {badge(row['status'], STATUS_COLORS)} {badge(row['priority'], PRIORITY_COLORS)}",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        c1.write(f"**Site:** {row['site_id']}")
        c1.write(f"**Region:** {row['region'] or '—'}")
        c1.write(f"**Alarm Type:** {row['alarm_type']}")
        c1.write(f"**FE Name:** {row['fe_name'] or '—'}")
        c2.write(f"**Opened:** {row['opened_at']}")
        c2.write(f"**Resolved:** {row['resolved_at'] or '—'}")
        c2.write(f"**UTin Verification:** {row['utin_verification'] or '—'}")
        c2.write(f"**Verification Result:** {row['verification_result'] or '—'}")
        st.write("**Notes:**")
        st.info(row["notes"] or "No notes recorded.")

    with t_edit:
        e1, e2 = st.columns(2)
        with e1:
            edit_site = st.text_input("Site ID", value=row["site_id"], key="m_site")
            edit_region = st.text_input("Region", value=row["region"] or "", key="m_region")
            edit_alarm = st.text_input("Alarm Type", value=row["alarm_type"] or "", key="m_alarm")
            edit_fe = st.text_input("FE Name", value=row["fe_name"] or "", key="m_fe")
        with e2:
            edit_priority = st.selectbox("Priority", PRIORITY_OPTIONS,
                                          index=PRIORITY_OPTIONS.index(row["priority"]) if row["priority"] in PRIORITY_OPTIONS else 1,
                                          key="m_priority")
            edit_status = st.selectbox("Status", STATUS_OPTIONS,
                                        index=STATUS_OPTIONS.index(row["status"]) if row["status"] in STATUS_OPTIONS else 0,
                                        key="m_status")
            edit_notes = st.text_area("Notes", value=row["notes"] or "", key="m_notes")

        b1, b2, b3 = st.columns(3)
        if b1.button("💾 Save", use_container_width=True, type="primary"):
            update_ticket_full(tt_id, {
                "site_id": edit_site.strip(), "region": edit_region.strip(), "alarm_type": edit_alarm.strip(),
                "priority": edit_priority, "status": edit_status, "fe_name": edit_fe.strip(), "notes": edit_notes.strip(),
            })
            refresh()
            st.toast(f"Ticket {tt_id} updated", icon="✅")
            st.session_state.open_ticket = None
            st.rerun()

        if b2.button("🔄 Status Only", use_container_width=True):
            update_ticket_status(tt_id, edit_status)
            refresh()
            st.toast(f"Status set to {edit_status}", icon="🔄")
            st.session_state.open_ticket = None
            st.rerun()

        confirm = b3.checkbox("Confirm", key="m_confirm_delete")
        if b3.button("🗑️ Delete", use_container_width=True, disabled=not confirm):
            delete_ticket(tt_id)
            refresh()
            st.toast(f"Ticket {tt_id} deleted", icon="🗑️")
            st.session_state.open_ticket = None
            st.rerun()

    if st.button("Close", use_container_width=True):
        st.session_state.open_ticket = None
        st.rerun()


def render_ticket_card(row):
    accent = PRIORITY_COLORS.get(row["priority"], "#ccc")
    with st.container():
        st.markdown(
            f"""
            <div class="ticket-card" style="--pcolor:{accent}">
                <div class="tt-top">
                    <span class="tt-id">{row['tt_id']}</span>
                    {badge(row['status'], STATUS_COLORS)}
                </div>
                <div class="tt-meta">📍 {row['site_id']} &nbsp;·&nbsp; ⚡ {row['alarm_type']} &nbsp;·&nbsp; {badge(row['priority'], PRIORITY_COLORS)}</div>
                <div class="tt-meta">🕒 Opened {row['opened_at']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("View / Update →", key=f"open_{row['tt_id']}", use_container_width=True):
            st.session_state.open_ticket = row["tt_id"]
            st.rerun()


# =====================================================================
# PAGE — DASHBOARD
# =====================================================================

if st.session_state.page == "Dashboard":
    hero("📊", "NOC Maintenance Dashboard", "Real-time overview of Trouble Tickets and alarm activity")

    total = len(df)
    open_ct = int((df["status"] == "Open").sum()) if total else 0
    prog_ct = int((df["status"] == "In Progress").sum()) if total else 0
    done_ct = int(df["status"].isin(["Resolved", "Closed"]).sum()) if total else 0
    avg_res = "—"
    if total and df["resolved_at_dt"].notna().any():
        mask = df["resolved_at_dt"].notna() & df["opened_at_dt"].notna()
        if mask.any():
            avg_res = f"{((df.loc[mask,'resolved_at_dt']-df.loc[mask,'opened_at_dt']).dt.total_seconds().mean()/3600):.1f} h"

    k1, k2, k3, k4, k5 = st.columns(5)
    kpi_card(k1, "Total TTs", total, "#274156")
    kpi_card(k2, "Open", open_ct, STATUS_COLORS["Open"])
    kpi_card(k3, "In Progress", prog_ct, STATUS_COLORS["In Progress"])
    kpi_card(k4, "Resolved / Closed", done_ct, STATUS_COLORS["Resolved"])
    kpi_card(k5, "Avg. Resolution", avg_res, "#4895ef")

    st.write("")

    if df.empty:
        empty_state("🗂️", "No tickets yet", "Get started by logging your first Trouble Ticket.",
                     "➕ Create a Trouble Ticket", "New Ticket")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### Alarm Types")
            st.bar_chart(df["alarm_type"].value_counts())
        with col_b:
            st.markdown("#### Tickets by Priority")
            st.bar_chart(df["priority"].value_counts().reindex(PRIORITY_OPTIONS).dropna())

        st.markdown("#### Tickets Opened Over Time")
        if df["opened_at_dt"].notna().any():
            st.line_chart(df.dropna(subset=["opened_at_dt"]).set_index("opened_at_dt").resample("D").size())

        st.markdown("#### 🕒 Recent Activity")
        for _, row in df.head(4).iterrows():
            render_ticket_card(row)

# =====================================================================
# PAGE — NEW TICKET (multi-step wizard)
# =====================================================================

elif st.session_state.page == "New Ticket":
    hero("➕", "New Trouble Ticket", "A guided, three-step flow for logging a new alarm")

    steps = ["Ticket Info", "Verification", "Review & Submit"]
    dots = st.columns(len(steps))
    for i, (col, label) in enumerate(zip(dots, steps), start=1):
        state = "done" if i < st.session_state.wizard_step else ("active" if i == st.session_state.wizard_step else "")
        col.markdown(
            f'<div style="text-align:center"><span class="step-dot {state}">{"✓" if state=="done" else i}</span>'
            f'<div class="step-label">{label}</div></div>',
            unsafe_allow_html=True,
        )
    st.write("")

    if "wizard_data" not in st.session_state:
        st.session_state.wizard_data = {}
    wd = st.session_state.wizard_data

    # ---- Step 1 ----
    if st.session_state.wizard_step == 1:
        with st.container(border=True):
            auto_id = st.toggle("Auto-generate TT ID", value=True)
            c1, c2 = st.columns(2)
            with c1:
                wd["tt_id"] = generate_tt_id() if auto_id else st.text_input("TT ID *", value=wd.get("tt_id", ""))
                if auto_id:
                    st.caption(f"Generated ID: **{wd['tt_id']}**")
                wd["site_id"] = st.text_input("Site ID *", value=wd.get("site_id", ""))
                wd["region"] = st.text_input("Region", value=wd.get("region", ""))
            with c2:
                wd["alarm_type"] = st.text_input("Alarm Type *", value=wd.get("alarm_type", ""))
                wd["fe_name"] = st.text_input("FE Name", value=wd.get("fe_name", ""))
                wd["priority"] = st.selectbox("Priority", PRIORITY_OPTIONS,
                                               index=PRIORITY_OPTIONS.index(wd.get("priority", "Medium")))
        nav1, nav2 = st.columns([1, 1])
        if nav2.button("Next: Verification →", use_container_width=True, type="primary"):
            if not wd.get("site_id", "").strip() or not wd.get("alarm_type", "").strip():
                st.error("Site ID and Alarm Type are required.")
            else:
                st.session_state.wizard_step = 2
                st.rerun()

    # ---- Step 2 ----
    elif st.session_state.wizard_step == 2:
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                wd["utin_verification"] = st.selectbox("UTin Verification", UTIN_OPTIONS,
                                                         index=UTIN_OPTIONS.index(wd.get("utin_verification", "Active")))
                wd["status"] = st.selectbox("Initial Status", STATUS_OPTIONS,
                                             index=STATUS_OPTIONS.index(wd.get("status", "Open")))
            with c2:
                wd["verification_result"] = st.selectbox("Verification Result", VERIFICATION_OPTIONS,
                                                           index=VERIFICATION_OPTIONS.index(wd.get("verification_result", "Not Verified Yet")))
            wd["notes"] = st.text_area("Notes", value=wd.get("notes", ""))
        nav1, nav2 = st.columns([1, 1])
        if nav1.button("← Back", use_container_width=True):
            st.session_state.wizard_step = 1
            st.rerun()
        if nav2.button("Next: Review →", use_container_width=True, type="primary"):
            st.session_state.wizard_step = 3
            st.rerun()

    # ---- Step 3 ----
    elif st.session_state.wizard_step == 3:
        st.markdown("#### Review before submitting")
        render_ticket_card(pd.Series({
            "tt_id": wd.get("tt_id", "—"), "status": wd.get("status", "Open"),
            "site_id": wd.get("site_id", ""), "alarm_type": wd.get("alarm_type", ""),
            "priority": wd.get("priority", "Medium"), "opened_at": "just now",
        }))
        st.write(f"**Region:** {wd.get('region') or '—'}  |  **FE Name:** {wd.get('fe_name') or '—'}")
        st.write(f"**UTin Verification:** {wd.get('utin_verification')}  |  **Result:** {wd.get('verification_result')}")
        st.write(f"**Notes:** {wd.get('notes') or '—'}")

        nav1, nav2 = st.columns([1, 1])
        if nav1.button("← Back", use_container_width=True):
            st.session_state.wizard_step = 2
            st.rerun()
        if nav2.button("✅ Submit Ticket", use_container_width=True, type="primary"):
            try:
                insert_ticket({
                    "tt_id": wd["tt_id"].strip(), "site_id": wd["site_id"].strip(),
                    "region": wd.get("region", "").strip(), "alarm_type": wd["alarm_type"].strip(),
                    "priority": wd["priority"], "status": wd["status"], "fe_name": wd.get("fe_name", "").strip(),
                    "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "alarm_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "utin_verification": wd["utin_verification"], "verification_result": wd["verification_result"],
                    "notes": wd.get("notes", "").strip(),
                })
                refresh()
                st.toast(f"Ticket {wd['tt_id']} created", icon="🎉")
                st.session_state.wizard_step = 1
                st.session_state.wizard_data = {}
                go_to("Tickets")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error(f"TT ID '{wd['tt_id']}' already exists. Go back and change it.")

# =====================================================================
# PAGE — TICKETS (card grid + table view + modal)
# =====================================================================

elif st.session_state.page == "Tickets":
    hero("📋", "Trouble Tickets", "Search, filter, and manage tickets")

    if st.session_state.open_ticket:
        ticket_modal(st.session_state.open_ticket)

    f1, f2, f3, f4, f5 = st.columns([2, 1, 1, 1, 1])
    search_term = f1.text_input("🔍 Search")
    status_filter = f2.multiselect("Status", STATUS_OPTIONS)
    priority_filter = f3.multiselect("Priority", PRIORITY_OPTIONS)
    region_filter = f4.text_input("Region")
    view_mode = f5.radio("View", ["Cards", "Table"], horizontal=True)

    filtered_df = df.copy()
    if search_term:
        mask = (filtered_df["tt_id"].str.contains(search_term, case=False, na=False)
                | filtered_df["site_id"].str.contains(search_term, case=False, na=False)
                | filtered_df["alarm_type"].str.contains(search_term, case=False, na=False))
        filtered_df = filtered_df[mask]
    if status_filter:
        filtered_df = filtered_df[filtered_df["status"].isin(status_filter)]
    if priority_filter:
        filtered_df = filtered_df[filtered_df["priority"].isin(priority_filter)]
    if region_filter:
        filtered_df = filtered_df[filtered_df["region"].str.contains(region_filter, case=False, na=False)]

    st.caption(f"Showing {len(filtered_df)} of {len(df)} ticket(s)")

    if filtered_df.empty:
        empty_state("🔍", "No matching tickets", "Try adjusting your filters, or create a new ticket.",
                     "➕ New Ticket", "New Ticket")
    elif view_mode == "Cards":
        grid_cols = st.columns(2)
        for i, (_, row) in enumerate(filtered_df.iterrows()):
            with grid_cols[i % 2]:
                render_ticket_card(row)
    else:
        st.dataframe(
            filtered_df[["tt_id", "site_id", "region", "alarm_type", "priority", "status", "fe_name", "opened_at", "resolved_at"]],
            use_container_width=True, hide_index=True,
        )
        csv = filtered_df.drop(columns=["opened_at_dt", "resolved_at_dt"], errors="ignore").to_csv(index=False)
        st.download_button("⬇️ Export CSV", data=csv, file_name="trouble_tickets.csv", mime="text/csv")

# =====================================================================
# PAGE — ALARM VERIFICATION
# =====================================================================

elif st.session_state.page == "Verification":
    hero("🔍", "Alarm Verification", "Rule-based check for genuine, false, or flapping alarms")

    RULES = {
        ("Active", "Active"): ("Possible Genuine Alarm", "success", "✅"),
        ("Active", "Flapping"): ("Possible Flapping Alarm", "warning", "⚠️"),
        ("Active", "Not Detected"): ("Mismatch — Possible False Alarm (RTCM active but UTin not detecting)", "warning", "❓"),
        ("Cleared", "Active"): ("Mismatch — Possible False Alarm (RTCM cleared but UTin still active)", "warning", "❓"),
        ("Cleared", "Flapping"): ("Possible Flapping Alarm", "warning", "⚠️"),
        ("Cleared", "Not Detected"): ("Possible False Alarm", "error", "❌"),
    }

    if "verify_history" not in st.session_state:
        st.session_state.verify_history = []

    left, right = st.columns([2, 1])

    with left:
        with st.container(border=True):
            with st.form("alarm_verification_form"):
                c1, c2 = st.columns(2)
                site = c1.text_input("Site ID")
                alarm_type = c1.text_input("Alarm Type")
                rtcm_status = c2.selectbox("RTCM Status", ["Active", "Cleared"])
                utin_status = c2.selectbox("UTin Status", UTIN_OPTIONS)
                check = st.form_submit_button("🔎 Verify Alarm", use_container_width=True, type="primary")

                if check:
                    if not site.strip() or not alarm_type.strip():
                        st.error("Please fill in both Site ID and Alarm Type before verifying.")
                    else:
                        label, kind, icon = RULES[(rtcm_status, utin_status)]
                        getattr(st, kind)(f"{icon} {label}")
                        st.session_state.verify_history.insert(0, {
                            "site": site, "alarm_type": alarm_type, "result": label,
                            "icon": icon, "time": datetime.now().strftime("%H:%M:%S"),
                        })
                        st.toast("Verification complete", icon=icon)

    with right:
        st.markdown("#### Recent Checks")
        if not st.session_state.verify_history:
            st.caption("No checks run yet this session.")
        for item in st.session_state.verify_history[:6]:
            st.markdown(
                f"""<div class="ticket-card" style="--pcolor:#274156">
                <div class="tt-top"><span class="tt-id">{item['icon']} {item['site']}</span>
                <span class="tt-meta">{item['time']}</span></div>
                <div class="tt-meta">{item['alarm_type']}</div>
                <div class="tt-meta">{item['result']}</div></div>""",
                unsafe_allow_html=True,
            )