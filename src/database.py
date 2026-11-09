from pathlib import Path

import duckdb

from src.generate_data import DATA_DIRECTORY


TABLE_TYPES = {
    "clients": {"client_id": "VARCHAR", "company_name": "VARCHAR", "total_seats": "INTEGER", "expected_office_days": "INTEGER", "booking_window_days": "INTEGER", "onboarding_date": "DATE"},
    "users": {"user_id": "VARCHAR", "client_id": "VARCHAR", "invited_date": "TIMESTAMP", "activated_date": "TIMESTAMP", "department": "VARCHAR"},
    "bookings": {"booking_id": "VARCHAR", "user_id": "VARCHAR", "client_id": "VARCHAR", "booking_date": "DATE", "created_at": "TIMESTAMP", "booking_status": "VARCHAR"},
    "checkins": {"checkin_id": "VARCHAR", "booking_id": "VARCHAR", "user_id": "VARCHAR", "client_id": "VARCHAR", "checkin_time": "TIMESTAMP"},
}


def connect_database(data_directory=DATA_DIRECTORY, frames=None):
    connection = duckdb.connect(":memory:")
    try:
        for table, columns in TABLE_TYPES.items():
            if frames is None:
                path = Path(data_directory) / f"{table}.csv"
                relation = connection.read_csv(str(path), header=True, columns=columns)
                relation.create_view(table)
            else:
                connection.register(f"input_{table}", frames[table])
                casts = ", ".join(f"CAST({column} AS {kind}) AS {column}" for column, kind in columns.items())
                connection.execute(f"CREATE TABLE {table} AS SELECT {casts} FROM input_{table}")
        connection.execute("""
            CREATE VIEW valid_bookings AS
            SELECT DISTINCT b.* FROM bookings b
            JOIN users u ON b.user_id = u.user_id AND b.client_id = u.client_id
            JOIN clients c ON b.client_id = c.client_id
            WHERE u.activated_date IS NOT NULL AND b.created_at >= u.activated_date
              AND CAST(b.created_at AS DATE) <= b.booking_date
              AND b.booking_status IN ('completed', 'cancelled', 'no_show');
            CREATE VIEW valid_checkins AS
            SELECT DISTINCT i.* FROM checkins i
            JOIN valid_bookings b ON i.booking_id = b.booking_id
              AND i.user_id = b.user_id AND i.client_id = b.client_id
            WHERE b.booking_status = 'completed' AND i.checkin_time >= b.created_at
              AND CAST(i.checkin_time AS DATE) = b.booking_date;
            CREATE VIEW user_activity AS
            SELECT client_id, user_id, created_at AS activity_time FROM valid_bookings
            UNION ALL
            SELECT client_id, user_id, checkin_time FROM valid_checkins
        """)
        return connection
    except Exception:
        connection.close()
        raise
