from io import BytesIO

import pandas as pd
import pytest

from src.analytics import add_health_scores, calculate_metrics, classify_health, executive_summary, weekly_active_users
from src.database import connect_database
from src.gap_detector import detect_gaps
from src.generate_data import SCHEMAS, generate_frames, write_data
from src.recommendations import product_feedback_summary, recommendation_export


def controlled_frames():
    rows = {
        "clients": [["C1", "Fixture", 20, 3, 7, "2026-10-01"], ["C2", "Empty", 20, 3, 7, "2026-10-01"]],
        "users": [[f"U{i}", "C1", "2026-10-01", "2026-10-02" if i <= 4 else None, "Sales"] for i in range(1, 6)],
        "bookings": [
            ["B1", "U1", "C1", "2026-10-05", "2026-10-03", "completed"],
            ["B2", "U1", "C1", "2026-10-06", "2026-10-04", "no_show"],
            ["B3", "U2", "C1", "2026-10-05", "2026-10-04", "completed"],
            ["B4", "U3", "C1", "2026-10-06", "2026-10-05", "cancelled"],
        ],
        "checkins": [
            ["I1", "B1", "U1", "C1", "2026-10-05 10:00:00"],
            ["I2", "B1", "U1", "C1", "2026-10-05 10:30:00"],
            ["I3", "B2", "U1", "C1", "2026-10-06 10:00:00"],
            ["I4", "B4", "U3", "C1", "2026-10-06 10:00:00"],
            ["I5", "B3", "U1", "C1", "2026-10-05 10:00:00"],
            ["I6", "B3", "U2", "C1", "2026-10-04 10:00:00"],
        ],
    }
    return {name: pd.DataFrame(rows[name], columns=columns) for name, columns in SCHEMAS.items()}


@pytest.fixture
def controlled_connection():
    connection = connect_database(frames=controlled_frames())
    yield connection
    connection.close()


def test_known_metrics_and_nested_funnel(controlled_connection):
    metrics = calculate_metrics(controlled_connection).set_index("client_id")
    client = metrics.loc["C1"]
    assert client["activation_rate"] == pytest.approx(80)
    assert client["first_booking_conversion"] == pytest.approx(75)
    assert client["repeat_booking_rate"] == pytest.approx(100 / 3)
    assert client["no_show_rate"] == pytest.approx(100 / 3)
    assert client["checkin_rate"] == pytest.approx(100 / 3)
    assert client["avg_days_to_first_booking"] == pytest.approx(2)
    assert [client[name] for name in ["invited_users", "activated_users", "first_booking_users", "repeat_booking_users", "checked_in_users"]] == [5, 4, 3, 1, 1]
    assert client["eligible_bookings"] == 3
    assert client["total_bookings"] == 4


def test_duplicate_bookings_do_not_inflate_metrics():
    frames = controlled_frames()
    frames["bookings"] = pd.concat([frames["bookings"], frames["bookings"].iloc[[2]]], ignore_index=True)
    with connect_database(frames=frames) as connection:
        client = calculate_metrics(connection).iloc[0]
    assert client["repeat_booking_users"] == 1
    assert client["total_bookings"] == 4
    assert client["checkin_rate"] == pytest.approx(100 / 3)


def test_final_funnel_stage_requires_repeat_before_checkin():
    frames = controlled_frames()
    frames["bookings"].loc[1, "created_at"] = "2026-10-05 12:00:00"
    with connect_database(frames=frames) as connection:
        client = calculate_metrics(connection).iloc[0]
    assert client["checked_in_users"] == 0
    assert client["checked_in_bookings"] == 1


def test_zero_denominators_and_insufficient_data(controlled_connection):
    metrics = calculate_metrics(controlled_connection)
    client = metrics.loc[metrics["client_id"] == "C2"].iloc[0]
    for metric in ["activation_rate", "first_booking_conversion", "repeat_booking_rate", "no_show_rate", "checkin_rate", "avg_days_to_first_booking", "health_score"]:
        assert pd.isna(client[metric])
    assert client["health_status"] == "Insufficient Data"
    gaps = detect_gaps(metrics)
    assert len(gaps.loc[gaps["client_id"] == "C2"]) == 4
    assert set(gaps["status"]) == {"Insufficient Data"}
    assert set(gaps["severity"]) == {"Unrated"}
    summary = executive_summary(metrics)
    assert summary["activation_rate"] == pytest.approx(80)


def test_completely_empty_tables():
    frames = {name: pd.DataFrame(columns=columns) for name, columns in SCHEMAS.items()}
    with connect_database(frames=frames) as connection:
        metrics = calculate_metrics(connection)
        assert metrics.empty
        assert weekly_active_users(connection).empty
    assert executive_summary(metrics)["activation_rate"] is None
    assert detect_gaps(metrics).empty
    assert product_feedback_summary(detect_gaps(metrics)).empty


def test_invited_users_without_bookings():
    frames = controlled_frames()
    frames["bookings"] = frames["bookings"].iloc[:0]
    frames["checkins"] = frames["checkins"].iloc[:0]
    with connect_database(frames=frames) as connection:
        client = calculate_metrics(connection).iloc[0]
    assert client["activation_rate"] == 80
    assert client["first_booking_conversion"] == 0
    assert pd.isna(client["repeat_booking_rate"])
    assert client["health_status"] == "Insufficient Data"


def test_weekly_activity_uses_event_times_and_distinct_users(controlled_connection):
    weekly = weekly_active_users(controlled_connection)
    populated = weekly.loc[weekly["client_id"] == "C1"].set_index("week_start")
    assert populated.loc[pd.Timestamp("2026-09-28"), "weekly_active_users"] == 2
    assert populated.loc[pd.Timestamp("2026-10-05"), "weekly_active_users"] == 2
    assert len(populated) == 5
    assert (weekly.loc[weekly["client_id"] == "C2", "weekly_active_users"] == 0).all()


@pytest.mark.parametrize("score, expected", [(0, "At Risk"), (49.99, "At Risk"), (50, "Needs Attention"), (74.99, "Needs Attention"), (75, "Healthy"), (100, "Healthy"), (float("nan"), "Insufficient Data")])
def test_health_boundaries(score, expected):
    assert classify_health(score) == expected


def test_health_weighting_and_minimum_samples():
    metrics = pd.DataFrame([{"invited_users": 10, "first_booking_users": 10, "eligible_bookings": 10, "activation_rate": 80, "repeat_booking_rate": 60, "checkin_rate": 40, "no_show_rate": 20}])
    assert add_health_scores(metrics).iloc[0]["health_score"] == pytest.approx(65)
    for denominator in ["invited_users", "first_booking_users", "eligible_bookings"]:
        insufficient = metrics.copy()
        insufficient[denominator] = 9
        assert add_health_scores(insufficient).iloc[0]["health_status"] == "Insufficient Data"


@pytest.mark.parametrize("metric, boundary, breach, issue", [
    ("activation_rate", 50, 49.99, "Onboarding gap"),
    ("repeat_booking_rate", 40, 39.99, "Low engagement"),
    ("no_show_rate", 30, 30.01, "Booking policy or reminder issue"),
    ("checkin_rate", 60, 59.99, "Check-in adoption gap"),
])
def test_strict_gap_thresholds(metric, boundary, breach, issue):
    frame = pd.DataFrame([{"client_id": "C1", "company_name": "Fixture", "invited_users": 10, "first_booking_users": 10, "eligible_bookings": 10, "activation_rate": 90, "repeat_booking_rate": 90, "no_show_rate": 5, "checkin_rate": 90}])
    frame[metric] = boundary
    assert detect_gaps(frame).empty
    frame[metric] = breach
    gaps = detect_gaps(frame)
    assert len(gaps) == 1
    assert gaps.iloc[0]["detected_issue"] == issue
    assert len(gaps.iloc[0]["recommended_action"]) > 30


def test_rule_configuration():
    frame = pd.DataFrame([{"client_id": "C1", "company_name": "Fixture", "invited_users": 10, "activation_rate": 65}])
    rules = [("activation_rate", "invited_users", 10, 70, "below", "Onboarding gap", "High")]
    assert len(detect_gaps(frame, rules)) == 1


def test_generated_relationships_and_sequences():
    frames = generate_frames()
    for name, primary_key in [("clients", "client_id"), ("users", "user_id"), ("bookings", "booking_id"), ("checkins", "checkin_id")]:
        assert frames[name][primary_key].is_unique
        pd.testing.assert_frame_equal(frames[name], generate_frames()[name])
    users = frames["users"]
    assert users.groupby("client_id").size().between(50, 100).all()
    assert users["client_id"].isin(frames["clients"]["client_id"]).all()
    assert (users.loc[users["activated_date"].notna(), "activated_date"] >= users.loc[users["activated_date"].notna(), "invited_date"]).all()
    bookings = frames["bookings"].merge(users, on=["user_id", "client_id"], how="left", validate="many_to_one").merge(frames["clients"], on="client_id", validate="many_to_one")
    assert bookings["activated_date"].notna().all()
    assert (bookings["created_at"] >= bookings["activated_date"]).all()
    booked_for = pd.to_datetime(bookings["booking_date"].astype(str) + " 09:00:00")
    assert (bookings["created_at"] < booked_for).all()
    assert ((pd.to_datetime(bookings["booking_date"]) - bookings["created_at"]).dt.days <= bookings["booking_window_days"]).all()
    assert pd.to_datetime(bookings["booking_date"]).between("2026-10-01", "2026-10-30").all()
    assert set(bookings["booking_status"]) == {"completed", "cancelled", "no_show"}
    joined = frames["checkins"].merge(frames["bookings"], on=["booking_id", "user_id", "client_id"], how="left", validate="one_to_one")
    assert joined["booking_status"].eq("completed").all()
    assert (joined["checkin_time"] >= joined["created_at"]).all()
    assert (joined["checkin_time"].dt.date == joined["booking_date"]).all()


def test_seeded_scenarios_and_csv_loading(tmp_path):
    write_data(tmp_path)
    with connect_database(tmp_path) as connection:
        metrics = calculate_metrics(connection)
    clients = metrics.set_index("client_id")
    assert clients.loc["C001", "health_status"] == "Healthy"
    assert clients.loc["C001", "checkin_rate"] > 85
    assert clients.loc["C002", "activation_rate"] > 80
    assert clients.loc["C002", "repeat_booking_rate"] < 40
    assert clients.loc["C003", "no_show_rate"] > 30
    assert clients.loc["C004", "activation_rate"] < 50
    assert clients.loc["C005", "total_bookings"] > 300
    assert clients.loc["C005", "checkin_rate"] < 60
    gaps = detect_gaps(metrics)
    pairs = set(zip(gaps["client_id"], gaps["detected_issue"]))
    assert ("C002", "Low engagement") in pairs
    assert ("C003", "Booking policy or reminder issue") in pairs
    assert ("C004", "Onboarding gap") in pairs
    assert ("C005", "Check-in adoption gap") in pairs
    assert not gaps["client_id"].eq("C001").any()
    feedback = product_feedback_summary(gaps)
    assert feedback.iloc[0]["detected_issue"] == "Check-in adoption gap"
    assert feedback.iloc[0]["affected_clients"] == 2
    csv = pd.read_csv(BytesIO(recommendation_export(metrics, gaps)))
    assert csv["client_id"].nunique() == 5
    assert csv["recommended_action"].notna().all()
    summary = executive_summary(metrics)
    assert summary["activation_rate"] == pytest.approx(100 * metrics["activated_users"].sum() / metrics["invited_users"].sum())
    assert summary["checkin_rate"] == pytest.approx(100 * metrics["checked_in_bookings"].sum() / metrics["eligible_bookings"].sum())


def test_source_has_no_comments_or_docstrings():
    import ast
    import io
    from pathlib import Path
    import tokenize

    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", *list((root / "src").glob("*.py")), *list((root / "tests").glob("*.py"))]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert all(token.type != tokenize.COMMENT for token in tokenize.generate_tokens(io.StringIO(source).readline))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                assert ast.get_docstring(node) is None
