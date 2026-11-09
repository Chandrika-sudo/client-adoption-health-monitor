import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics import executive_summary, load_analytics
from src.gap_detector import detect_gaps
from src.generate_data import DATA_DIRECTORY
from src.recommendations import product_feedback_summary, recommendation_export, recommendations_for_client


st.set_page_config(page_title="Client Adoption Monitor", page_icon="📊", layout="wide")


@st.cache_data(show_spinner=False)
def cached_analytics(fingerprint):
    return load_analytics()


def percentage(value):
    return "N/A" if value is None or pd.isna(value) else f"{value:.1f}%"


def style_chart(figure):
    figure.update_layout(template="plotly_white", font=dict(family="Arial", color="#172554"), margin=dict(l=20, r=20, t=35, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return figure


st.title("Client Adoption & Implementation Health Monitor")

st.info("Portfolio simulation ")

paths = [DATA_DIRECTORY / f"{name}.csv" for name in ("clients", "users", "bookings", "checkins")]
if not all(path.exists() for path in paths):
    st.error("Dataset missing. Run `python -m src.generate_data` from the project folder, then reload.")
    st.stop()

try:
    fingerprint = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
    metrics, weekly, period = cached_analytics(fingerprint)
except Exception as error:
    st.error(f"Unable to load analytics. Check the CSV schemas and regenerate the simulation if necessary. Details: {error}")
    st.stop()

if metrics.empty:
    st.warning("No clients available. Generate data to begin.")
    st.stop()

gaps = detect_gaps(metrics)
summary = executive_summary(metrics)
with st.sidebar:
    st.header("Analysis workspace")
    st.caption(f"Observation period: {pd.Timestamp(period[0]):%d %b %Y} – {pd.Timestamp(period[1]):%d %b %Y}")
    selected_id = st.selectbox("Client", metrics["client_id"].tolist(), format_func=lambda client_id: metrics.set_index("client_id").loc[client_id, "company_name"])
    st.caption("All-time metrics within the fixed 30-day simulation. Weekly activity uses Monday-based calendar weeks; boundary weeks are partial.")
    st.caption("Health requires ≥10 invited users, ≥10 booking users and ≥10 eligible bookings. Rules indicate investigation priorities, not proven causes.")

client = metrics.loc[metrics["client_id"] == selected_id].iloc[0]
overview, adoption, monitor, success = st.tabs(["Executive overview", "Client adoption", "Implementation gaps", "Success recommendations"])

with overview:
    st.subheader("Portfolio health at a glance")
    columns = st.columns(5)
    for column, label, value in zip(columns, ["Total clients", "Total users", "Overall activation", "Overall check-in", "At-risk clients"], [summary["total_clients"], summary["total_users"], percentage(summary["activation_rate"]), percentage(summary["checkin_rate"]), summary["at_risk_clients"]]):
        column.metric(label, value)
    st.caption("Overall rates use summed numerators and denominators across clients. At-risk count uses the weighted health score; high-severity gaps may also exist in other health bands.")
    palette = {"Healthy": "#2563eb", "Needs Attention": "#d97706", "At Risk": "#dc2626", "Insufficient Data": "#64748b"}
    chart = px.bar(metrics, x="company_name", y="health_score", color="health_status", color_discrete_map=palette, range_y=[0, 100], labels={"company_name": "Client", "health_score": "Health score", "health_status": "Status"}, hover_data=["activation_rate", "repeat_booking_rate", "checkin_rate", "no_show_rate"])
    chart.add_hline(y=75, line_dash="dot", line_color="#94a3b8")
    chart.add_hline(y=50, line_dash="dot", line_color="#94a3b8")
    st.plotly_chart(style_chart(chart), width="stretch")
    st.dataframe(metrics[["company_name", "health_score", "health_status", "activation_rate", "repeat_booking_rate", "checkin_rate", "no_show_rate"]].rename(columns=lambda name: name.replace("_", " ").title()), hide_index=True, width="stretch")

with adoption:
    st.subheader(f"Adoption analysis · {client['company_name']}")
    columns = st.columns(4)
    for column, label, value in zip(columns, ["Activation rate", "First booking conversion", "Repeat booking rate", "Avg. days to first booking"], [percentage(client["activation_rate"]), percentage(client["first_booking_conversion"]), percentage(client["repeat_booking_rate"]), "N/A" if pd.isna(client["avg_days_to_first_booking"]) else f"{client['avg_days_to_first_booking']:.2f}"]):
        column.metric(label, value)
    left, right = st.columns(2)
    with left:
        funnel = go.Figure(go.Funnel(y=["Invited", "Activated", "First booking", "Repeat booking", "Checked in after repeat"], x=[client[column] for column in ["invited_users", "activated_users", "first_booking_users", "repeat_booking_users", "checked_in_users"]], textinfo="value+percent initial", marker_color="#2563eb"))
        funnel.update_layout(title="Adoption funnel · distinct users")
        st.plotly_chart(style_chart(funnel), width="stretch")
    with right:
        activity = weekly.loc[weekly["client_id"] == selected_id]
        chart = px.line(activity, x="week_start", y="weekly_active_users", markers=True, labels={"week_start": "Week starting Monday", "weekly_active_users": "Active users"}, title="Weekly active users")
        chart.update_traces(line_color="#2563eb")
        chart.update_yaxes(rangemode="tozero", dtick=10)
        st.plotly_chart(style_chart(chart), width="stretch")
    st.caption("Booking metrics include cancelled reservations as booking intent. Time to first booking measures activation to reservation creation. The final funnel stage requires a valid check-in at or after the user's second reservation was created. Weekly activity counts reservation creation or check-in events, not scheduled office dates.")
    st.metric("Check-in rate", percentage(client["checkin_rate"]))
    st.metric("No-show rate", percentage(client["no_show_rate"]))

with monitor:
    st.subheader("Potential implementation and adoption gaps")
    st.caption("Illustrative thresholds flag hypotheses for investigation. No-show bookings also reduce check-in rate, so these findings can overlap.")
    left, right = st.columns(2)
    filter_clients = left.multiselect("Filter clients", metrics["company_name"].tolist())
    filter_severity = right.multiselect("Filter severity", ["High", "Medium", "Unrated"])
    filtered = gaps.copy()
    if filter_clients:
        filtered = filtered.loc[filtered["client_name"].isin(filter_clients)]
    if filter_severity:
        filtered = filtered.loc[filtered["severity"].isin(filter_severity)]
    if filtered.empty:
        st.success("No findings match the current filters.")
    else:
        display = filtered[["client_name", "detected_issue", "severity", "status", "metric_value", "threshold", "sample_size", "recommended_action"]].copy()
        display["metric_value"] = display["metric_value"].map(percentage)
        display.columns = ["Client", "Detected issue", "Severity", "Status", "Current metric", "Threshold", "Sample size", "Recommended action"]
        st.dataframe(display, hide_index=True, width="stretch")

with success:
    st.subheader(f"Client success brief · {client['company_name']}")
    score = "N/A" if pd.isna(client["health_score"]) else f"{client['health_score']:.1f}/100"
    st.write(f"**Health: {client['health_status']} · {score}**")
    st.write(f"{client['activated_users']} of {client['invited_users']} invited employees activated. {client['first_booking_users']} made a reservation; {client['repeat_booking_users']} booked at least twice.")
    client_gaps = gaps.loc[gaps["client_id"] == selected_id]
    st.markdown("**Key risks and evidence**")
    if client_gaps.empty:
        st.write("No rule thresholds breached with sufficient observations. Continue monitoring.")
    for _, finding in client_gaps.iterrows():
        st.write(f"• {finding['detected_issue']}: {percentage(finding['metric_value'])} · {finding['status']} · {finding['severity']}")
    st.markdown("**Recommended follow-up actions**")
    for action in recommendations_for_client(client, gaps):
        st.write(f"• {action}")
    st.download_button("Download client recommendations as CSV", data=recommendation_export(metrics.loc[metrics["client_id"] == selected_id], gaps), file_name=f"{selected_id}_recommendations.csv", mime="text/csv")
    st.markdown("**Recurring issues for Product Managers · all clients**")
    st.caption("Rule-based findings ranked by affected clients. These are investigation topics, not client feedback, interviews, or feature requests.")
    feedback = product_feedback_summary(gaps)
    if feedback.empty:
        st.write("No recurring issues detected.")
    else:
        st.dataframe(feedback.rename(columns=lambda name: name.replace("_", " ").title()), hide_index=True, width="stretch")
    st.download_button("Download all client recommendations", data=recommendation_export(metrics, gaps), file_name="all_client_recommendations.csv", mime="text/csv")
