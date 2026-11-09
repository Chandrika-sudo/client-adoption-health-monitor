from pathlib import Path

import pandas as pd

from src.database import connect_database
from src.generate_data import DATA_DIRECTORY


SQL_DIRECTORY = Path(__file__).resolve().parents[1] / "sql"
MIN_INVITED_USERS = 10
MIN_BOOKING_USERS = 10
MIN_ELIGIBLE_BOOKINGS = 10
HEALTH_WEIGHTS = {"activation_rate": 0.30, "repeat_booking_rate": 0.25, "checkin_rate": 0.25, "attendance_reliability": 0.20}


def classify_health(score):
    if pd.isna(score):
        return "Insufficient Data"
    if score >= 75:
        return "Healthy"
    if score >= 50:
        return "Needs Attention"
    return "At Risk"


def add_health_scores(metrics):
    result = metrics.copy()
    result["attendance_reliability"] = 100 - result["no_show_rate"]
    sufficient = (result["invited_users"] >= MIN_INVITED_USERS) & (result["first_booking_users"] >= MIN_BOOKING_USERS) & (result["eligible_bookings"] >= MIN_ELIGIBLE_BOOKINGS)
    score = sum(result[column] * weight for column, weight in HEALTH_WEIGHTS.items())
    result["health_score"] = score.where(sufficient)
    result["health_status"] = result["health_score"].map(classify_health)
    return result


def calculate_metrics(connection):
    return add_health_scores(connection.execute((SQL_DIRECTORY / "adoption_metrics.sql").read_text(encoding="utf-8")).df())


def weekly_active_users(connection):
    return connection.execute("""
        WITH bounds AS (
            SELECT MIN(onboarding_date) AS start_date,
                   GREATEST(MAX(onboarding_date) + INTERVAL 29 DAY,
                            COALESCE((SELECT MAX(CAST(activity_time AS DATE)) FROM user_activity), MAX(onboarding_date))) AS end_date
            FROM clients
        ), weeks AS (
            SELECT CAST(week_start AS DATE) AS week_start FROM bounds,
            generate_series(date_trunc('week', start_date), date_trunc('week', end_date), INTERVAL 1 WEEK) AS t(week_start)
        ), activity AS (
            SELECT client_id, CAST(date_trunc('week', activity_time) AS DATE) AS week_start,
                   COUNT(DISTINCT user_id) AS weekly_active_users
            FROM user_activity GROUP BY client_id, week_start
        )
        SELECT c.client_id, c.company_name, w.week_start, COALESCE(a.weekly_active_users, 0) AS weekly_active_users
        FROM clients c CROSS JOIN weeks w
        LEFT JOIN activity a ON c.client_id = a.client_id AND w.week_start = a.week_start
        ORDER BY c.client_id, w.week_start
    """).df()


def executive_summary(metrics):
    totals = metrics.sum(numeric_only=True)
    return {
        "total_clients": len(metrics),
        "total_users": int(totals.get("invited_users", 0)),
        "activation_rate": 100 * totals.get("activated_users", 0) / totals["invited_users"] if totals.get("invited_users", 0) else None,
        "checkin_rate": 100 * totals.get("checked_in_bookings", 0) / totals["eligible_bookings"] if totals.get("eligible_bookings", 0) else None,
        "at_risk_clients": int((metrics["health_status"] == "At Risk").sum()),
    }


def load_analytics(data_directory=DATA_DIRECTORY):
    connection = connect_database(data_directory)
    try:
        metrics = calculate_metrics(connection)
        weekly = weekly_active_users(connection)
        period = connection.execute("SELECT MIN(onboarding_date), MAX(onboarding_date) + INTERVAL 29 DAY FROM clients").fetchone()
        return metrics, weekly, period
    finally:
        connection.close()
