import pandas as pd


ACTIONS = {
    "Onboarding gap": "Schedule an onboarding walkthrough and verify whether employees received activation instructions.",
    "Low engagement": "Review employee booking friction and conduct a follow-up session to understand barriers to repeated use.",
    "Booking policy or reminder issue": "Review booking window settings and investigate whether automated reminders could reduce missed reservations.",
    "Check-in adoption gap": "Validate check-in instructions and investigate whether employees are experiencing access or training issues.",
}


def recommended_action(issue):
    return ACTIONS[issue]


def product_feedback_summary(gaps):
    findings = gaps.loc[gaps["status"] == "Potential gap"]
    if findings.empty:
        return pd.DataFrame(columns=["detected_issue", "affected_clients", "clients", "investigation"])
    summary = findings.groupby("detected_issue", as_index=False).agg(
        affected_clients=("client_id", "nunique"),
        clients=("client_name", lambda names: ", ".join(sorted(set(names)))),
        investigation=("recommended_action", "first"),
    )
    return summary.sort_values(["affected_clients", "detected_issue"], ascending=[False, True]).reset_index(drop=True)


def recommendations_for_client(client, gaps):
    findings = gaps.loc[(gaps["client_id"] == client["client_id"]) & (gaps["status"] == "Potential gap")]
    if not findings.empty:
        return findings["recommended_action"].tolist()
    if client["health_status"] == "Insufficient Data":
        return ["Collect at least ten invited users, ten booking users, and ten eligible bookings before interpreting the overall health score."]
    return ["Maintain onboarding guidance and monitor weekly activity; review again after the next observation period."]


def recommendation_export(metrics, gaps):
    records = []
    for _, client in metrics.iterrows():
        findings = gaps.loc[gaps["client_id"] == client["client_id"]]
        if findings.empty:
            records.append({"client_id": client["client_id"], "client_name": client["company_name"], "health_score": client["health_score"], "health_status": client["health_status"], "finding": "No threshold breaches", "severity": "None", "status": "Monitoring", "recommended_action": recommendations_for_client(client, gaps)[0]})
        else:
            for _, finding in findings.iterrows():
                records.append({"client_id": client["client_id"], "client_name": client["company_name"], "health_score": client["health_score"], "health_status": client["health_status"], "finding": finding["detected_issue"], "severity": finding["severity"], "status": finding["status"], "recommended_action": finding["recommended_action"]})
    columns = ["client_id", "client_name", "health_score", "health_status", "finding", "severity", "status", "recommended_action"]
    return pd.DataFrame(records, columns=columns).to_csv(index=False).encode("utf-8-sig")
