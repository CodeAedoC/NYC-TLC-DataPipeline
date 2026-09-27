# 📐 Pipeline Specification: NYC TLC Operational Data Pipeline

> **Derived from:** [`problem_statement.md`](./problem_statement.md), [`source_map.md`](./source_map.md), [`data_profiling_report.md`](./data_profiling_report.md)
> **Technology & tooling decisions:** see [`tech_requirements.md`](./tech_requirements.md)
> **Assignment Track:** B — NYC TLC (Class 4–8 Coverage)
> **Dataset Scope:** January 2024 Yellow Taxi Trips (repeatable monthly)

---

## 1. Pipeline Goal & Success Criteria

### Goal
Transform **3 raw, multi-mode source inputs** into a **trustworthy monthly operational dataset** and a **5-metric KPI summary table** that TLC leadership can act on.

### Success Criteria (non-negotiable)
| Criterion | Requirement |
| :--- | :--- |
| Raw immutability | All source files written once to `data/raw/` and never overwritten |
| No silent deletion | Every invalid row receives a `validation_flag` label; zero rows are quietly dropped |
| Auditable financials | Any trip where total != component sum (> $0.05) is isolated and labelled |
| Reproducibility | Re-running the pipeline on the same month produces byte-identical KPI outputs |
| Logging | Every stage emits timestamped log lines to `logs/pipeline.log` |
| Graceful failure | Any retrieval or assertion failure raises an exception with a clear human message; pipeline halts cleanly |

---

## 2. Data Sources (Inputs)

| # | Source ID | Type | URL / Location | Raw File Saved As | Format |
| :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | `yellow_trips` | Parquet File (HTTP) | `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{YYYY}-{MM}.parquet` | `data/raw/yellow_tripdata_{YYYY}-{MM}.parquet` | Parquet |
| S2 | `taxi_zones` | CSV File (HTTP) | `https://d37ci6vzurychx.cloudfront.net/misc/taxi+_zone_lookup.csv` | `data/raw/taxi_zone_lookup.csv` | CSV |
| S3 | `industry_indicators` | REST API (Socrata JSON) | `https://data.cityofnewyork.us/resource/v6kb-cqej.json` | `data/raw/tlc_industry_indicators.json` | JSON |

**Idempotency rule:** If a raw file already exists **and** its MD5 hash matches a stored manifest, skip re-download. Log the decision.

---

## 3. Pipeline Stages & Module Map

```
main.py
|
+-- Stage 1: INGEST          src/ingestion/download_data.py
|   +-- download_trip_parquet()
|   +-- download_taxi_zones_csv()
|   +-- fetch_industry_indicators_api()
|
+-- Stage 2: VALIDATE        src/validation/validate.py
|   +-- check_temporal_bounds()
|   +-- check_timestamp_order()
|   +-- check_financial_integrity()
|   +-- check_fare_math()
|   +-- check_telematics()
|   +-- check_location_ids()
|
+-- Stage 3: TRANSFORM       src/modeling/transform.py
|   +-- join_zone_names()
|   +-- compute_trip_duration_min()
|   +-- compute_avg_speed_mph()
|   +-- compute_reconciled_total()
|   +-- build_operational_dataset()
|
+-- Stage 4: METRICS         src/modeling/metrics.py
|   +-- metric_avg_fare_per_mile()
|   +-- metric_hourly_driver_revenue()
|   +-- metric_peak_demand_zones()
|   +-- metric_congestion_fee_capture_rate()
|   +-- metric_clean_operational_yield()
|
+-- Stage 5: OUTPUT          src/output/report.py
    +-- write_validated_dataset()     -> data/processed/
    +-- write_audit_table()           -> data/processed/audit/
    +-- write_kpi_summary_csv()       -> data/processed/kpi_summary.csv
    +-- write_known_unknown_md()      -> docs/known_unknown_assumptions.md
```

---

## 4. Stage Specifications

### Stage 1 — Ingest
**File:** `src/ingestion/download_data.py`

| Spec ID | Requirement |
| :--- | :--- |
| ING-01 | Ingest from **at least 2 distinct retrieval modes** (Parquet file, CSV file, REST API) |
| ING-02 | Compute and log MD5 hash of every downloaded file immediately after write |
| ING-03 | Store MD5 + file path + row count + timestamp in `data/raw/ingestion_manifest.json` |
| ING-04 | If a file already exists and MD5 matches manifest, skip download and log `[SKIP]` |
| ING-05 | If download fails, raise a `RuntimeError` with source URL, HTTP status code, and a descriptive message |
| ING-06 | Log each source as `[INGEST][SOURCE_ID] status: OK/SKIP/FAIL  rows: N  size_mb: X` |

---

### Stage 2 — Validate
**File:** `src/validation/validate.py`

Validation produces a single column `validation_flag` appended to every trip record. A trip may carry **multiple flags**, stored as a pipe-delimited string (e.g., `FLAG_NEGATIVE_FINANCIAL|FLAG_TELEMATICS_ERROR`). Rows with no flags receive `VALID_OPERATIONAL`.

#### Temporal Anomaly Rules

The raw data contains **4 distinct temporal failure modes**, each with a different business cause and pipeline response:

| Spec ID | Rule Name | Logic | Count (Jan 2024) | Root Cause | Flag Applied |
| :--- | :--- | :--- | :--- | :--- | :--- |
| VAL-01a | Out-of-Scope Pickup (Past) | `tpep_pickup_datetime < '2024-01-01'` | **15 trips** | Meter clock not reset after Dec 2023; oldest record is `2002-12-31` | `FLAG_OUT_OF_BOUND_DATE` |
| VAL-01b | Out-of-Scope Pickup (Future) | `tpep_pickup_datetime >= '2024-02-01'` | **3 trips** | Meter clock drift or premature Feb data bleed | `FLAG_OUT_OF_BOUND_DATE` |
| VAL-02a | Impossible Timestamp Order | `tpep_dropoff_datetime <= tpep_pickup_datetime` | **870 trips** | GPS/meter desync — clock resets mid-trip causing dropoff to appear before pickup | `FLAG_INVALID_TIMESTAMPS` |
| VAL-02b | Unrealistic Trip Duration | `trip_duration_min > 1440` (i.e., > 24 hours) | **16 trips** | Meter left running overnight; driver forgot to end trip | `FLAG_DURATION_ANOMALY` |

> **Note:** VAL-02a count was revised from an initial estimate of 56 to **870** after full dataset scan (the original profiling script used a narrower date filter). The corrected figure is empirically confirmed.

#### All Validation Rules

| Spec ID | Rule Name | Logic | Flag Applied |
| :--- | :--- | :--- | :--- |
| VAL-01a | Out-of-Scope Pickup (Past) | `tpep_pickup_datetime < '2024-01-01'` | `FLAG_OUT_OF_BOUND_DATE` |
| VAL-01b | Out-of-Scope Pickup (Future) | `tpep_pickup_datetime >= '2024-02-01'` | `FLAG_OUT_OF_BOUND_DATE` |
| VAL-02a | Impossible Timestamp Order | `tpep_dropoff_datetime <= tpep_pickup_datetime` | `FLAG_INVALID_TIMESTAMPS` |
| VAL-02b | Unrealistic Trip Duration | `trip_duration_min > 1440` (> 24 hrs, valid order) | `FLAG_DURATION_ANOMALY` |
| VAL-03 | Negative Financials | `fare_amount < 0` OR `total_amount < 0` | `FLAG_NEGATIVE_FINANCIAL` |
| VAL-04 | Fare Math | `abs(total_amount - computed_sum) > 0.05` | `FLAG_MATH_DISCREPANCY` |
| VAL-05 | Zero Distance | `trip_distance = 0` | `FLAG_TELEMATICS_ERROR` |
| VAL-06 | Speed Impossibility | Derived `avg_speed_mph > 100` | `FLAG_TELEMATICS_ERROR` |
| VAL-07 | Unknown Location | `PULocationID IN (264, 265)` OR `DOLocationID IN (264, 265)` | `FLAG_UNKNOWN_LOCATION` |
| VAL-08 | Null Critical Fields | `passenger_count IS NULL` OR `RatecodeID IS NULL` | `FLAG_MISSING_ATTRIBUTES` |
| VAL-09 | Invalid Payment Type | `payment_type NOT IN (1, 2, 3, 4)` | `FLAG_INVALID_PAYMENT_TYPE` |
| VAL-10 | Cash Tip Anomaly | `payment_type = 2` AND `tip_amount > 0` | `FLAG_CASH_TIP_ANOMALY` |

**Hard Assertion Checks** (pipeline halts if any fail):

| Assert ID | Assertion | Threshold |
| :--- | :--- | :--- |
| ASSERT-01 | Total raw rows read from parquet equals manifest row count | Must match exactly |
| ASSERT-02 | Percentage of `VALID_OPERATIONAL` rows >= 90% of raw total | Fail if < 90% |
| ASSERT-03 | `taxi_zone_lookup.csv` contains LocationIDs 1 through 263 at minimum | All valid IDs must resolve |

---

### Stage 3 — Transform
**File:** `src/modeling/transform.py`

| Spec ID | Transformation | Output Column(s) |
| :--- | :--- | :--- |
| TRF-01 | Join `PULocationID` to zone lookup; add borough & zone name | `pu_borough`, `pu_zone` |
| TRF-02 | Join `DOLocationID` to zone lookup; add borough & zone name | `do_borough`, `do_zone` |
| TRF-03 | Compute trip duration in minutes from timestamps | `trip_duration_min` |
| TRF-04 | Compute average speed (mph) where duration > 0 only | `avg_speed_mph` |
| TRF-05 | Compute reconciled total: fare + extra + mta_tax + tip + tolls + improvement + COALESCE(congestion, 0) + COALESCE(airport_fee, 0) | `reconciled_total` |
| TRF-06 | Impute NULL `congestion_surcharge` as 0.0 — log count of imputed rows (NOT silent) | `congestion_surcharge` |
| TRF-07 | Impute NULL `Airport_fee` as 0.0 — log count of imputed rows (NOT silent) | `Airport_fee` |
| TRF-08 | Extract `pickup_hour` (0-23) and `pickup_dow` (0=Mon) from pickup timestamp | `pickup_hour`, `pickup_dow` |
| TRF-09 | Add `is_airport_trip` boolean flag where `PULocationID IN (132, 138)` (JFK=132, LGA=138) | `is_airport_trip` |
| TRF-10 | Write only `VALID_OPERATIONAL` rows to `data/processed/trips_clean.parquet` | — |
| TRF-11 | Write all flagged rows to `data/processed/audit/trips_flagged.parquet` | — |

---

### Stage 4 — Metrics
**File:** `src/modeling/metrics.py`

All metrics computed on `VALID_OPERATIONAL` rows unless stated otherwise.

| Metric ID | Metric Name | Business Question Answered | Formula / Logic |
| :--- | :--- | :--- | :--- |
| M-01 | **Average Fare per Mile** | What does a clean trip earn per mile? | `mean(fare_amount / trip_distance)` where `trip_distance > 0` |
| M-02 | **Estimated Hourly Driver Revenue (HDR)** | How much does a driver earn per operational hour? | `sum(reconciled_total) / sum(trip_duration_min) * 60`, grouped by `pickup_hour` |
| M-03 | **Peak Demand Zone Index** | Which zones are most congested at peak hours? | Top-10 `pu_zone` by trip count during peak hours (7–10 AM, 4–8 PM) |
| M-04 | **Congestion Fee Capture Rate (CFCR)** | What % of eligible trips correctly captured the congestion surcharge? | `COUNT(congestion_surcharge > 0) / COUNT(pu_borough='Manhattan' AND is_airport_trip=False) * 100` |
| M-05 | **Clean Operational Yield (COY)** | What % of raw records are operationally valid? | `COUNT(VALID_OPERATIONAL) / COUNT(*) * 100` over full raw dataset |

**Output:** All 5 metrics written to `data/processed/kpi_summary.csv` with columns:
`metric_id, metric_name, value, unit, scope, computed_at`

---

### Stage 5 — Output & Reporting
**File:** `src/output/report.py`

| Spec ID | Output | Location | Format |
| :--- | :--- | :--- | :--- |
| OUT-01 | Clean operational trip dataset | `data/processed/trips_clean.parquet` | Parquet |
| OUT-02 | Audit / flagged trip dataset | `data/processed/audit/trips_flagged.parquet` | Parquet |
| OUT-03 | KPI Summary table | `data/processed/kpi_summary.csv` | CSV |
| OUT-04 | Pipeline execution log | `logs/pipeline.log` | Plain text |
| OUT-05 | Known / Unknown / Assumptions / Limitations doc | `docs/known_unknown_assumptions.md` | Markdown |

---

## 5. Known / Unknown / Assumptions / Limitations

| Category | Item |
| :--- | :--- |
| **Known** | 140,162 trips (4.73%) have NULL `RatecodeID`, `passenger_count`, and fee fields — legacy meter firmware gap |
| **Known** | 761,838 trips (25.7%) have billing component math discrepancies > $0.05 |
| **Known** | LocationIDs 264/265 exist in raw data and are not mapped to any borough |
| **Known** | 37,448 trips have negative fare amounts (total -$1,418,290.45) — assumed refunds or voids |
| **Unknown** | Whether negative fares are intentional refunds or meter malfunctions — cannot confirm without TLC chargeback ledger |
| **Unknown** | The true driver or medallion identity behind any trip — omitted from public data for privacy |
| **Assumption** | NULL `congestion_surcharge` is treated as $0.00 (trip pre-dates or is exempt from June 2019 law) |
| **Assumption** | Speed > 100 mph indicates a GPS/timestamp error, not actual vehicle speed |
| **Assumption** | Trips with same `PULocationID` and `DOLocationID` are legitimate short intra-zone rides, not duplicates |
| **Limitation** | Metric M-02 (Hourly Driver Revenue) is an approximation — no real shift start/end data exists in public records |
| **Limitation** | CFCR (M-04) cannot distinguish Manhattan trips legally exempt from congestion pricing |

---

## 6. Refund & Negative Fare Management

### Why This Needs Explicit Handling
The raw dataset contains **37,448 trips with negative `fare_amount`** and **35,504 with negative `total_amount`** (-$1,418,290.45 combined). These are **not noise** — they represent real business events (chargebacks, meter voids, payment reversals) that must be tracked separately from operational revenue, not silently excluded.

### Negative Fare Taxonomy

| Category | Detection Logic | Business Interpretation | Pipeline Action |
| :--- | :--- | :--- | :--- |
| **Meter Void / Cancellation** | `fare_amount < 0` AND `trip_distance = 0` AND `total_amount < 0` | Fare entered and reversed before trip completed — meter was voided | Tag `FLAG_NEGATIVE_FINANCIAL\|FLAG_TELEMATICS_ERROR`; route to refund audit table |
| **Payment Chargeback / Reversal** | `fare_amount < 0` AND `trip_distance > 0` AND `total_amount < 0` | Trip completed but payment was reversed after the fact | Tag `FLAG_NEGATIVE_FINANCIAL`; record in chargeback sub-table with `reconciled_total` shown as negative |
| **Partial Adjustment** | `fare_amount < 0` AND `total_amount >= 0` | Downward correction applied to base fare while surcharges remain positive | Tag `FLAG_NEGATIVE_FINANCIAL`; keep in audit table; do NOT include in revenue metrics |

### Isolation Strategy (Spec IDs: REF-01 to REF-04)

| Spec ID | Requirement |
| :--- | :--- |
| REF-01 | All trips with `fare_amount < 0` OR `total_amount < 0` receive `FLAG_NEGATIVE_FINANCIAL` and are **never included** in KPI metric calculations (M-01 through M-05) |
| REF-02 | Negative-fare trips are written to a dedicated table: `data/processed/audit/trips_refunds.parquet` with their full row data intact |
| REF-03 | Pipeline logs total count and total absolute dollar value of negative-fare trips at the end of Stage 2: `[VALIDATE] Negative-fare trips: N  Total value: -$X` |
| REF-04 | The `known_unknown_assumptions.md` output (OUT-05) includes a **Refund Summary** row: count, total value, and % of raw dataset |

### What We Cannot Determine (Limitation)
Without access to TLC's internal chargeback ledger or payment processor records, we **cannot confirm** whether a negative fare is an authorised reversal or a meter malfunction. This is documented as an explicit **Unknown** in section 5 and in the final `known_unknown_assumptions.md`.

---

## 7. Directory Layout (Final Expected State)

```
FDEProject2v2/
├── data/
│   ├── raw/
│   │   ├── yellow_tripdata_2024-01.parquet    <- immutable raw input (S1)
│   │   ├── taxi_zone_lookup.csv               <- immutable raw input (S2)
│   │   ├── tlc_industry_indicators.json       <- immutable raw input (S3)
│   │   └── ingestion_manifest.json            <- MD5 + row count + timestamp per source
│   └── processed/
│       ├── trips_clean.parquet                <- VALID_OPERATIONAL trips only
│       ├── kpi_summary.csv                    <- 5 core metrics
│       └── audit/
│           └── trips_flagged.parquet          <- all flagged rows with validation_flag
├── docs/
│   ├── problem_statement.md
│   ├── source_map.md
│   ├── data_profiling_report.md
│   ├── specs.md                               <- this file
│   └── known_unknown_assumptions.md           <- auto-generated by Stage 5
├── src/
│   ├── ingestion/
│   │   └── download_data.py                   <- Stage 1
│   ├── validation/
│   │   └── validate.py                        <- Stage 2
│   ├── modeling/
│   │   ├── transform.py                       <- Stage 3
│   │   └── metrics.py                         <- Stage 4
│   └── output/
│       └── report.py                          <- Stage 5
├── scratch/
│   └── analyze_business_data.py               <- temporary profiling (not part of pipeline)
├── logs/
│   └── pipeline.log                           <- auto-generated at runtime
├── main.py                                    <- pipeline orchestrator entry point
└── README.md
```

> **Technology stack, dependencies, and CLI execution commands are documented in [`tech_requirements.md`](./tech_requirements.md).**
