WITH booking_order AS (
    SELECT client_id, user_id, created_at,
           ROW_NUMBER() OVER (PARTITION BY client_id, user_id ORDER BY created_at, booking_id) AS booking_number
    FROM (SELECT DISTINCT booking_id, client_id, user_id, created_at FROM valid_bookings)
), second_bookings AS (
    SELECT client_id, user_id, created_at AS second_booking_at FROM booking_order WHERE booking_number = 2
), per_user AS (
    SELECT u.client_id, u.user_id, u.activated_date,
           COUNT(DISTINCT b.booking_id) AS booking_count,
           MIN(b.created_at) AS first_booking_at,
           COUNT(DISTINCT i.booking_id) FILTER (WHERE i.checkin_time >= s.second_booking_at) AS checkin_count
    FROM users u
    LEFT JOIN valid_bookings b ON u.user_id = b.user_id AND u.client_id = b.client_id
    LEFT JOIN valid_checkins i ON b.booking_id = i.booking_id
    LEFT JOIN second_bookings s ON u.client_id = s.client_id AND u.user_id = s.user_id
    GROUP BY u.client_id, u.user_id, u.activated_date
), user_totals AS (
    SELECT client_id, COUNT(*) AS invited_users,
           COUNT(*) FILTER (WHERE activated_date IS NOT NULL) AS activated_users,
           COUNT(*) FILTER (WHERE booking_count >= 1) AS first_booking_users,
           COUNT(*) FILTER (WHERE booking_count >= 2) AS repeat_booking_users,
           COUNT(*) FILTER (WHERE booking_count >= 2 AND checkin_count >= 1) AS checked_in_users,
           AVG(date_diff('second', activated_date, first_booking_at) / 86400.0)
               FILTER (WHERE booking_count >= 1) AS avg_days_to_first_booking
    FROM per_user GROUP BY client_id
), booking_totals AS (
    SELECT b.client_id, COUNT(DISTINCT b.booking_id) AS total_bookings,
           COUNT(DISTINCT b.booking_id) FILTER (WHERE b.booking_status <> 'cancelled') AS eligible_bookings,
           COUNT(DISTINCT b.booking_id) FILTER (WHERE b.booking_status = 'no_show') AS no_show_bookings,
           COUNT(DISTINCT i.booking_id) AS checked_in_bookings
    FROM valid_bookings b
    LEFT JOIN valid_checkins i ON b.booking_id = i.booking_id
    GROUP BY b.client_id
), totals AS (
    SELECT c.*,
           COALESCE(u.invited_users, 0) AS invited_users,
           COALESCE(u.activated_users, 0) AS activated_users,
           COALESCE(u.first_booking_users, 0) AS first_booking_users,
           COALESCE(u.repeat_booking_users, 0) AS repeat_booking_users,
           COALESCE(u.checked_in_users, 0) AS checked_in_users,
           u.avg_days_to_first_booking,
           COALESCE(b.total_bookings, 0) AS total_bookings,
           COALESCE(b.eligible_bookings, 0) AS eligible_bookings,
           COALESCE(b.no_show_bookings, 0) AS no_show_bookings,
           COALESCE(b.checked_in_bookings, 0) AS checked_in_bookings
    FROM clients c
    LEFT JOIN user_totals u ON c.client_id = u.client_id
    LEFT JOIN booking_totals b ON c.client_id = b.client_id
)
SELECT *,
       100.0 * activated_users / NULLIF(invited_users, 0) AS activation_rate,
       100.0 * first_booking_users / NULLIF(activated_users, 0) AS first_booking_conversion,
       100.0 * repeat_booking_users / NULLIF(first_booking_users, 0) AS repeat_booking_rate,
       100.0 * checked_in_bookings / NULLIF(eligible_bookings, 0) AS checkin_rate,
       100.0 * no_show_bookings / NULLIF(eligible_bookings, 0) AS no_show_rate
FROM totals ORDER BY client_id
