from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Combat Robot Live", page_icon="🤖", layout="wide")
st.markdown(
    """
    <style>
    .block-container {max-width:1450px;padding-top:1.0rem;padding-bottom:3rem;}
    .live-card {border:3px solid #666;border-radius:14px;padding:14px 18px;margin:.5rem 0;background:rgba(120,130,145,.07)}
    .live-card.red {border-color:#c62828;background:#fff0f0}.live-card.blue {border-color:#1565c0;background:#eef6ff}
    .group-card {border:3px solid rgba(80,90,110,.55);border-radius:12px;overflow:hidden;margin:.5rem 0 1.1rem;background:rgba(120,130,145,.055)}
    .group-title {font-size:1.08rem;font-weight:850;padding:.55rem .75rem;background:rgba(105,115,130,.18);border-bottom:2px solid rgba(80,90,110,.4)}
    .group-card table {width:100%;border-collapse:collapse;font-size:.9rem}.group-card th{padding:.42rem .5rem;text-align:left;background:rgba(100,110,130,.10);border-bottom:2px solid rgba(80,90,110,.3)}
    .group-card td{padding:.4rem .5rem;border-bottom:1px solid rgba(90,100,120,.20)}.group-card tr.qualifier{background:rgba(55,150,90,.11)}
    @media (max-width: 700px){.block-container{padding-left:.7rem;padding-right:.7rem}.group-card table{font-size:.78rem}}
    </style>
    """,
    unsafe_allow_html=True,
)


def _config():
    try:
        return str(st.secrets["SUPABASE_URL"]).rstrip("/"), str(st.secrets["SUPABASE_PUBLISHABLE_KEY"])
    except Exception:
        st.error("This public viewer has not been configured yet. The organiser needs to add the Supabase URL and publishable key to Streamlit Cloud secrets.")
        st.stop()


def fetch_current():
    base, key = _config()
    endpoint = base + "/rest/v1/live_public_events?select=event_key,event_name,snapshot,updated_at&is_active=eq.true&order=updated_at.desc&limit=1"
    req = urllib.request.Request(endpoint, headers={"apikey": key, "Accept": "application/json", "User-Agent":"CombatRobotPublicViewer/1.14"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        st.error(f"The live-data service returned HTTP {exc.code}. {detail[:300]}")
        return None
    except Exception as exc:
        st.error(f"Could not reach the live-data service: {exc}")
        return None
    return rows[0] if rows else None


def cat_icon(value: str) -> str:
    return "🔴" if str(value).casefold() == "destructive" else "🔵"


def queue_card(row: dict, heading: str) -> str:
    destructive = str(row.get("Type", "")).casefold() == "destructive"
    cls = "red" if destructive else "blue"
    bits = [f"Fight {row.get('Order')}" if row.get("Order") else "", row.get("Division", ""), row.get("Stage", "")]
    if row.get("Estimated"):
        bits.append("~" + str(row["Estimated"]))
    if row.get("Arena"):
        bits.append(str(row["Arena"]))
    meta = " · ".join(str(x) for x in bits if x)
    return f"""
    <div class="live-card {cls}">
      <div style="font-size:.82rem;font-weight:850;letter-spacing:.06em">{html.escape(heading)}</div>
      <div style="font-size:1.5rem;font-weight:850;margin:.3rem 0">{html.escape(str(row.get('Robot_1','')))} <span style="opacity:.55">vs</span> {html.escape(str(row.get('Robot_2','')))}</div>
      <div style="font-size:.92rem;opacity:.78">{html.escape(meta)}</div>
    </div>"""


def group_letter(n: int) -> str:
    n = max(1, int(n)); out = ""
    while n:
        n, r = divmod(n - 1, 26); out = chr(65 + r) + out
    return out


def group_card(rows: list[dict], group_number: int) -> str:
    if not rows:
        return ""
    preferred = ["Position","Robot","Team","Played","Wins","Draws","Losses","Points","Against","Difference","Qualifies"]
    columns = [c for c in preferred if any(c in r for r in rows)]
    short = {"Position":"Pos","Played":"P","Wins":"W","Draws":"D","Losses":"L","Points":"Pts","Difference":"Diff","Qualifies":"Q"}
    head = "".join(f"<th>{html.escape(short.get(c,c))}</th>" for c in columns)
    body = []
    for row in rows:
        qualifier = str(row.get("Qualifies", "")).casefold() == "yes"
        cells = "".join(f"<td>{html.escape('' if row.get(c) is None else str(row.get(c)))}</td>" for c in columns)
        body.append(f"<tr class={'qualifier' if qualifier else ''}>{cells}</tr>")
    return f'<div class="group-card"><div class="group-title">Group {group_letter(group_number)}</div><div style="overflow-x:auto"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div></div>'


def render_snapshot(snapshot: dict, updated_at: str):
    event = snapshot.get("event", {})
    metrics = snapshot.get("metrics", {})
    st.title(event.get("event_name", "Combat Robot Live"))
    detail = " · ".join(x for x in [event.get("event_date") or "", event.get("location") or ""] if x)
    st.caption(detail or "Live competition board")

    c1, c2, c3 = st.columns(3)
    c1.metric("Completed", metrics.get("completed", 0))
    c2.metric("Remaining", metrics.get("remaining", 0))
    c3.metric("Pace", f"{float(metrics.get('pace_minutes', 0)):.1f} min/fight" if metrics.get("pace_minutes") else "—")

    queue = snapshot.get("queue", {})
    if queue.get("now"):
        st.markdown(queue_card(queue["now"][0], "NOW FIGHTING"), unsafe_allow_html=True)
    if queue.get("next"):
        st.markdown(queue_card(queue["next"][0], "ON DECK / NEXT"), unsafe_allow_html=True)
    if queue.get("prepare"):
        st.markdown("#### Prepare")
        cols = st.columns(min(2, len(queue["prepare"])))
        for col, row in zip(cols, queue["prepare"][:2]):
            with col:
                st.markdown(queue_card(row, "PREPARE"), unsafe_allow_html=True)

    st.subheader("Fight schedule and results")
    schedule = pd.DataFrame(snapshot.get("schedule", []))
    if schedule.empty:
        st.info("No fights have been published yet.")
    else:
        if "Type" in schedule.columns:
            schedule["Category"] = schedule["Type"].map(lambda v: f"{cat_icon(v)} {v}")
        if "Queue_Status" in schedule.columns:
            schedule["Status"] = schedule["Queue_Status"]
        show_cols = [c for c in ["Order","Estimated","Division","Category","Stage","Group","Robot_1","Robot_2","Result","Status","Arena"] if c in schedule.columns]
        st.dataframe(schedule[show_cols], hide_index=True, use_container_width=True, height=620)

    st.subheader("Current standings")
    for div in snapshot.get("divisions", []):
        icon = cat_icon(div.get("competition_type", ""))
        label = f"{icon} {div.get('weight_class','')} — {div.get('competition_type','')} — {div.get('division_name','')}"
        with st.expander(label, expanded=True):
            standings = div.get("standings", []) or []
            if div.get("has_groups"):
                groups = {}
                for row in standings:
                    try: g = int(row.get("Group"))
                    except Exception: continue
                    groups.setdefault(g, []).append(row)
                group_ids = sorted(groups)
                for i in range(0, len(group_ids), 2):
                    batch = group_ids[i:i+2]
                    cols = st.columns(len(batch))
                    for col, g in zip(cols, batch):
                        with col:
                            st.markdown(group_card(groups[g], g), unsafe_allow_html=True)
            elif standings:
                st.dataframe(pd.DataFrame(standings), hide_index=True, use_container_width=True)
            finals = div.get("finals", []) or []
            if finals:
                st.markdown("**Finals bracket**")
                st.dataframe(pd.DataFrame(finals), hide_index=True, use_container_width=True)

    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        age = max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
        if age > 120:
            st.warning(f"Live data has not updated for about {int(age // 60)} minutes. The organiser may be offline.")
        st.caption(f"Last published: {dt.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}. This page refreshes automatically.")
    except Exception:
        st.caption("This page refreshes automatically.")


@st.fragment(run_every="5s")
def live_board():
    row = fetch_current()
    if not row:
        st.info("There is no active published competition right now. Try again once the organiser enables Online Builder View.")
        return
    render_snapshot(row.get("snapshot") or {}, str(row.get("updated_at") or ""))


live_board()
