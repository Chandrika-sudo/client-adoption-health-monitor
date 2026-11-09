import pandas as pd

from src.analytics import MIN_BOOKING_USERS, MIN_ELIGIBLE_BOOKINGS, MIN_INVITED_USERS
from src.recommendations import recommended_action


ACTIVATION_THRESHOLD = 50.0
REPEAT_THRESHOLD = 40.0
NO_SHOW_THRESHOLD = 30.0
CHECKIN_THRESHOLD = 60.0
RULES = (
    ("activation_rate", "invited_users", MIN_INVITED_USERS, ACTIVATION_THRESHOLD, "below", "Onboarding gap", "High"),
    ("repeat_booking_rate", "first_booking_users", MIN_BOOKING_USERS, REPEAT_THRESHOLD, "below", "Low engagement", "Medium"),
    ("no_show_rate", "eligible_bookings", MIN_ELIGIBLE_BOOKINGS, NO_SHOW_THRESHOLD, "above", "Booking policy or reminder issue", "High"),
    ("checkin_rate", "eligible_bookings", MIN_ELIGIBLE_BOOKINGS, CHECKIN_THRESHOLD, "below", "Check-in adoption gap", "High"),
)
GAP_COLUMNS = ["client_id", "client_name", "detected_issue", "metric_value", "threshold", "severity", "status", "sample_size", "recommended_action"]


def detect_gaps(metrics, rules=None):
    records = []
    for _, client in metrics.iterrows():
        for metric, denominator, minimum, threshold, direction, issue, severity in RULES if rules is None else rules:
            value = client[metric]
            insufficient = client[denominator] < minimum or pd.isna(value)
            breached = False if insufficient else (value < threshold if direction == "below" else value > threshold)
            if insufficient or breached:
                records.append({
                    "client_id": client["client_id"], "client_name": client["company_name"],
                    "detected_issue": issue, "metric_value": value, "threshold": f"{direction} {threshold:g}%",
                    "severity": "Unrated" if insufficient else severity,
                    "status": "Insufficient Data" if insufficient else "Potential gap",
                    "sample_size": int(client[denominator]),
                    "recommended_action": f"Collect at least {minimum} observations in {denominator.replace('_', ' ')} before applying this rule." if insufficient else recommended_action(issue),
                })
    return pd.DataFrame(records, columns=GAP_COLUMNS)
