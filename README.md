# Client Adoption & Implementation Health Monitor

A local analytics workspace for Product and Customer Success teams to track employee onboarding, desk-booking adoption, attendance, and potential implementation gaps across five fictional workplace SaaS clients.

**All records are synthetic.** This is an independent portfolio simulation inspired by workplace SaaS adoption workflows, built for a Product Analyst Intern portfolio. It is not affiliated with, endorsed by, or based on private data from WorkInSync. No client interviews, support conversations, or feature requests are represented as evidence.

## Business problem

A successful implementation requires more than activated accounts. Employees must discover booking, return to it, and complete the office attendance workflow. Aggregate activation can conceal client-specific friction, while high booking counts can coexist with missed reservations or incomplete check-ins.

This project connects onboarding and usage signals to transparent investigation priorities. Sustained adoption matters in B2B SaaS because it helps clients realize value and helps Product teams understand where workflows may need improvement. The simulation does not measure retention, revenue, or causal effects.

## Technology stack

Python 3.12, Pandas, DuckDB SQL, Plotly, Streamlit, and pytest. DuckDB runs in memory against local CSV files; no database server, credentials, API, or paid service is required. Direct package versions are pinned in `requirements.txt`.

## Install and run on Windows

Open the project folder in VS Code and use its PowerShell terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m src.generate_data
python -m pytest -q
python -m streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`. Stop it with Ctrl+C. If PowerShell blocks activation, use the virtual environment's interpreter directly without changing execution policy:

```powershell
.\.venv\Scripts\python.exe
pip install -r requirements.txt
src.generate_data
pytest -q
streamlit run app.py
```

Run commands from the project root. Dataset and SQL paths resolve relative to their modules. Regeneration replaces the four synthetic CSV files with the same seed-42 data. A missing dataset produces an instruction in the dashboard; no data is silently generated. Header-only CSV tables are supported. Malformed input produces a visible loading error.

## Dataset

The fixed observation window is **1–30 October 2026**, with reservations on weekdays. The window is fixed so the portfolio findings remain reproducible regardless of the date on which the app runs. It is not a live operational feed.

| File | Grain | Fields |
| --- | --- | --- |
| `clients.csv` | One fictional client | client_id, company_name, total_seats, expected_office_days, booking_window_days, onboarding_date |
| `users.csv` | One invited employee | user_id, client_id, invited_date, activated_date, department |
| `bookings.csv` | One desk reservation | booking_id, user_id, client_id, booking_date, created_at, booking_status |
| `checkins.csv` | One recorded check-in | checkin_id, booking_id, user_id, client_id, checkin_time |

Clients have 50–100 invited users each. `activated_date` is blank for users who never activate. Booking statuses are `completed`, `cancelled`, and `no_show`. Here, `completed` means the reservation period elapsed without a cancellation or recorded no-show; an employee may still lack a recorded check-in. Thus missing check-ins and explicit no-shows are separate signals, and missing check-ins are not automatically classified as absences.

The generator uses different activation, first-use, repeat-use, no-show, and check-in probabilities. SQL derives all dashboard values from the resulting events. No final KPI or health score is manually assigned. Reservations follow activation, remain within the configured advance booking window, and have at most one generated check-in. IDs and client/user relationships are consistent. All timestamps are naive local simulation times, not UTC or mixed time zones.

## Architecture

```text
client-adoption-monitor/
├── .streamlit/config.toml
├── data/
│   ├── clients.csv
│   ├── users.csv
│   ├── bookings.csv
│   └── checkins.csv
├── src/
│   ├── __init__.py
│   ├── generate_data.py
│   ├── database.py
│   ├── analytics.py
│   ├── gap_detector.py
│   └── recommendations.py
├── sql/adoption_metrics.sql
├── tests/
│   ├── test_metrics.py
│   └── test_app.py
├── app.py
├── requirements.txt
├── pytest.ini
├── .gitignore
└── README.md
```

Data generator → local CSVs → typed DuckDB views → SQL client metrics and weekly activity → health scoring and detection rules → recommendations and Streamlit charts.

`database.py` owns connections, explicit CSV types, and event validation views. `adoption_metrics.sql` contains the main client aggregations; `analytics.py` contains the separate weekly activity SQL and transparent scoring. UI rendering stays in `app.py`. Streamlit caches analytical results using each CSV's path, modification timestamp, and size; file changes invalidate the cache. Filters and client selection operate on cached results. Connections close after analytical reads.

## KPI definitions

All percentages are multiplied by 100. Counts use distinct users or booking IDs as appropriate. Numerators and denominators use the entire observation window, rather than a rolling lookback or equal-duration user cohorts.

| KPI | Definition |
| --- | --- |
| Activation rate | Activated users / invited users |
| First booking conversion | Activated users with ≥1 valid booking / activated users |
| Repeat booking rate | Users with ≥2 distinct valid bookings / users with ≥1 valid booking |
| Check-in rate | Distinct eligible bookings with ≥1 valid check-in / eligible bookings |
| No-show rate | Distinct no-show bookings / distinct completed plus no-show bookings |
| Average time to first booking | Mean elapsed fractional days from activation to first reservation creation; excludes users without a booking |
| Weekly active users | Distinct users creating reservations or recording valid check-ins in each Monday-based calendar week |

A valid booking references a known activated employee in the same client, is created on or after activation and on or before its scheduled date, and uses a supported status. A valid check-in matches booking, user, and client; references a completed reservation; occurs on the scheduled day; and is not earlier than reservation creation. Multiple check-in records cannot inflate booking counts. Identical duplicate booking rows are removed, and analytical booking counts use distinct IDs. Conflicting duplicate IDs are unsupported input and should be resolved upstream.

Cancelled reservations count as booking intent in first-use, repeat-use, time-to-first-use, and weekly activity. They are excluded from check-in and no-show denominators. Both completed and no-show reservations are check-in eligible; consequently, high no-shows can also lower check-in rate. These signals can overlap and should not be treated as independent proof of two separate problems.

The nested funnel is invited → activated → first booking → repeat booking → checked in after repeat. Its final stage requires at least two distinct bookings plus a valid check-in at or after the second reservation's creation time. This intentional nesting differs from the check-in KPI, which covers all eligible reservations.

Zero denominators return missing values, displayed as `N/A`; a genuine zero numerator with an observed denominator displays 0%. Executive rates use total numerators / total denominators, not the mean of client percentages. Weekly charts include zero-activity weeks. The fixed window spans five calendar-week buckets; the first and last weeks are partial and are not directly comparable with full weeks. `expected_office_days`, `total_seats`, and `booking_window_days` are contextual configuration fields, not additional scoring inputs.

## Implementation gap detection

Rules in `src/gap_detector.py` return structured client IDs, names, issues, metric values, thresholds, severity, sample sizes, statuses, and recommended actions.

| Condition | Potential gap | Severity | Minimum denominator |
| --- | --- | --- | --- |
| Activation <50% | Onboarding gap | High | 10 invited users |
| Repeat booking <40% | Low engagement | Medium | 10 booking users |
| No-shows >30% | Booking policy or reminder issue | High | 10 eligible bookings |
| Check-in <60% | Check-in adoption gap | High | 10 eligible bookings |

Threshold comparisons are strict: exactly 50%, 40%, 30%, or 60% does not breach its corresponding rule. Thresholds are illustrative configurable constants, not industry benchmarks. Edit the constants and `RULES` in `gap_detector.py` to change policy; a custom rule tuple can also be supplied to `detect_gaps`. Minimum sample constants are in `analytics.py`.

Missing metrics or denominators below the minimum return **Insufficient Data** with **Unrated** severity and a data collection recommendation. They are excluded from recurring-issue counts. Sufficient metrics that do not breach a rule produce no alert. Passing a rule does not establish that a client has no problems.

## Client health methodology

```text
Health = 0.30 × activation rate
       + 0.25 × repeat booking rate
       + 0.25 × check-in rate
       + 0.20 × (100 − no-show rate)
```

| Score | Status |
| --- | --- |
| ≥75 | Healthy |
| ≥50 and <75 | Needs Attention |
| <50 | At Risk |
| Missing or insufficient observations | Insufficient Data |

Inputs are percentages from 0–100, so the weighted sum is also 0–100 without an additional scale factor. Classification uses the unrounded score; display rounding does not change the class. The score requires at least 10 invited users, 10 booking users, and 10 eligible bookings. Missing components are not replaced with zero and weights are not redistributed.

The weighted score is a prioritization heuristic, not a validated churn predictor. Strong components can offset a serious single gap. Use the individual rules alongside the score: a high-severity issue may exist in a Healthy or Needs Attention client. Check-in and no-show components partly overlap; the formula intentionally follows the requested illustrative weights.

## Dashboard features

1. **Executive overview:** calculated client/user counts, weighted overall activation and check-in rates, at-risk client count, health chart, and supporting metric table.
2. **Client adoption:** client selector, nested adoption funnel, activation and conversion metrics, time to first reservation creation, check-in/no-show rates, and weekly active users.
3. **Implementation gaps:** client and severity filters, observed percentages, thresholds, sample sizes, evidence status, and specific recommendations. Empty filters include all values.
4. **Success recommendations:** selected-client health brief, observed risks, follow-up actions, selected-client and all-client CSV exports, and recurring issue categories ranked by affected clients for Product Managers.

All views contain calculated results. The simulation disclosure stays visible. The Product Manager summary explicitly labels findings as rule-based investigation topics rather than reported client feedback.

## Findings from the generated dataset

Default seed 42 produces **5 clients, 425 invited users, 1,796 reservations, and 984 recorded check-ins**. Overall activation is **85.18%** and the eligible-booking check-in rate is **59.10%**. These values were read from the generated CSVs through DuckDB.

| Fictional client | Activation | Repeat booking | Check-in | No-show | Health | Main finding |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Northstar Labs | 97.78% | 79.27% | 93.99% | 3.65% | 91.92 · Healthy | Strong adoption; no threshold breaches |
| CedarWorks | 92.50% | 8.20% | 92.50% | 5.00% | 71.92 · Needs Attention | Employees activate but rarely book again |
| Orbit Studio | 98.82% | 90.00% | 47.24% | 51.94% | 73.57 · Needs Attention | Excessive no-shows; overlapping check-in alert |
| MapleBridge | 34.67% | 77.27% | 86.61% | 6.30% | 70.11 · Needs Attention | Activation is the main observed drop-off |
| Harbor Collective | 94.74% | 88.10% | 26.04% | 4.77% | 76.00 · Healthy | High booking volume with weak check-in completion |

There are **five potential gaps across four clients**. Check-in adoption is the most recurring category, affecting Orbit Studio and Harbor Collective; the other categories each affect one client. Start by distinguishing Orbit's recorded no-shows from Harbor's missing check-in records before proposing a shared intervention.

No default client scores below 50, so the at-risk KPI correctly displays **0**. Harbor illustrates the score's compensatory behavior: strong activation, repeat booking, and attendance reliability offset its poor check-in rate. Its high-severity check-in finding remains visible and requires follow-up despite the Healthy label. The tests exercise At Risk and Insufficient Data with controlled fixtures, without changing the requested scoring formula to force those labels into the demo.

## Recommended client success actions

- For onboarding gaps, verify invitation delivery and activation instructions, then schedule an onboarding walkthrough.
- For low repeat booking, review the reservation workflow and conduct a follow-up session to understand barriers to returning.
- For no-show issues, review advance booking windows and investigate reminder opportunities before changing policy.
- For incomplete check-ins, validate employee instructions, access, and training; separately check whether the telemetry is complete.
- For a healthy client, maintain onboarding guidance and continue monitoring weekly activity.

These are proposed investigations generated from rules. The project does not claim these actions were performed or that any outcome improved.

## Testing and verification

Run `python -m pytest -q` from the activated environment. The equivalent `pytest -q` command also works: `pytest.ini` adds the project root to the test import path so the `src` package resolves with either invocation. Controlled fixtures cover exact activation, first-booking conversion, repeat booking, no-show and check-in rates, time to first booking, nested funnel behavior, duplicate reservations, invalid check-ins, empty tables, missing denominators, weekly event activity, health weights/boundaries, strict rule thresholds, and configurable rules.

Generator checks cover deterministic output, unique IDs, foreign keys, activation/invitation order, valid statuses, reservation windows, check-in order, and all five seeded scenarios. Export tests parse the generated recommendation CSV and verify client coverage. Streamlit AppTest renders all tabs, changes clients, combines client/severity filters, exercises an empty result, and checks download controls have generated media URLs. Source checks enforce no Python comments or docstrings.

Verified locally on Windows with Python 3.12.3: dependency installation succeeded, `pip check` reported no broken requirements, and **24 tests passed**. A running Streamlit server returned HTTP 200 at `/` and `ok` at `/_stcore/health`. Dashboard behavior was verified with AppTest; no browser screenshot or visual browser review is claimed, and the project has not been deployed.

The installed pytest/Python combination emits a non-failing `argparse` startup warning about `file_or_dir`. All tests complete successfully; no application or test failures remain.

## Limitations and future improvements

- Synthetic probabilities demonstrate contrasting workflows; they do not estimate real workplace behavior or WorkInSync product performance.
- Small samples, recently invited employees, and partial calendar weeks can distort comparisons. Minimum sample sizes reduce obvious errors without providing statistical confidence intervals.
- All clients share one observation period; there is no cohort-adjusted conversion, holiday calendar, business-hours latency, or timezone normalization.
- Missing check-in telemetry cannot distinguish employee behavior from instrumentation or device failures. Correlation does not establish root cause.
- CSV schemas and generated relationships are validated by tests. This is not a general-purpose ingestion pipeline; conflicting duplicate IDs, schema drift, or arbitrary corrupt source files need upstream validation.
- The application is local and has no authentication, live integrations, background refresh, or deployment. Direct dependencies are pinned; transitive dependencies are resolved by pip.
- Future work could add dated cohorts, event quality reporting, historical trend comparisons, and evaluations of threshold sensitivity using authorized real data.

## Resume bullets

- Built a Python, DuckDB SQL, and Streamlit analytics dashboard to monitor onboarding, booking adoption, attendance, and client health across five simulated B2B SaaS clients.
- Implemented configurable gap detection, weighted health scoring, Product Manager issue summaries, and downloadable client success recommendations, validated with SQL fixtures and dashboard interaction tests.
