from datetime import datetime, timedelta
from pathlib import Path
import random

import pandas as pd


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
START_DATE = datetime(2026, 10, 1)
OBSERVATION_DAYS = 30
SEED = 42
SCENARIOS = [
    ("C001", "Northstar Labs", 90, 0.95, 0.95, 0.88, 0.04, 0.98),
    ("C002", "CedarWorks", 80, 0.94, 0.85, 0.15, 0.06, 0.95),
    ("C003", "Orbit Studio", 85, 0.92, 0.95, 0.86, 0.55, 0.95),
    ("C004", "MapleBridge", 75, 0.32, 0.85, 0.80, 0.06, 0.95),
    ("C005", "Harbor Collective", 95, 0.96, 0.95, 0.90, 0.05, 0.30),
]
SCHEMAS = {
    "clients": ["client_id", "company_name", "total_seats", "expected_office_days", "booking_window_days", "onboarding_date"],
    "users": ["user_id", "client_id", "invited_date", "activated_date", "department"],
    "bookings": ["booking_id", "user_id", "client_id", "booking_date", "created_at", "booking_status"],
    "checkins": ["checkin_id", "booking_id", "user_id", "client_id", "checkin_time"],
}


def generate_frames(seed=SEED):
    rng = random.Random(seed)
    clients, users, bookings, checkins = [], [], [], []
    office_dates = [START_DATE + timedelta(days=day) for day in range(OBSERVATION_DAYS) if (START_DATE + timedelta(days=day)).weekday() < 5]
    for client_id, company, population, activation, conversion, repeat, no_show, completion in SCENARIOS:
        booking_window = 14 if client_id == "C003" else 7
        clients.append([client_id, company, population + 15, 3, booking_window, START_DATE.date()])
        for position in range(population):
            user_id = f"{client_id}-U{position + 1:03d}"
            invited = START_DATE + timedelta(days=rng.randint(0, 3), hours=8)
            activated = invited + timedelta(hours=rng.randint(1, 72)) if rng.random() < activation else None
            users.append([user_id, client_id, invited, activated, rng.choice(["Engineering", "Operations", "Finance", "Sales", "People"])])
            if activated is None or rng.random() >= conversion:
                continue
            count = rng.randint(4, 11) if rng.random() < repeat else 1
            available = [day for day in office_dates if day.replace(hour=9) > activated + timedelta(hours=1)]
            for day in sorted(rng.sample(available, min(count, len(available)))):
                booking_id = f"B{len(bookings) + 1:05d}"
                booked_for = day.replace(hour=9)
                earliest = max(activated, booked_for - timedelta(days=booking_window))
                created = earliest + (booked_for - earliest) * rng.uniform(0.05, 0.85)
                draw = rng.random()
                status = "cancelled" if draw < 0.08 else "no_show" if draw < 0.08 + 0.92 * no_show else "completed"
                bookings.append([booking_id, user_id, client_id, day.date(), created, status])
                if status == "completed" and rng.random() < completion:
                    checkins.append([f"I{len(checkins) + 1:05d}", booking_id, user_id, client_id, booked_for + timedelta(minutes=rng.randint(0, 120))])
    rows = {"clients": clients, "users": users, "bookings": bookings, "checkins": checkins}
    return {name: pd.DataFrame(rows[name], columns=columns) for name, columns in SCHEMAS.items()}


def write_data(directory=DATA_DIRECTORY, seed=SEED):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    frames = generate_frames(seed)
    for name, frame in frames.items():
        frame.to_csv(directory / f"{name}.csv", index=False)
    return frames


if __name__ == "__main__":
    for name, frame in write_data().items():
        print(f"{name}: {len(frame):,} synthetic records")
