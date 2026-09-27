# ⚙️ Technology Requirements: NYC TLC Operational Data Pipeline

> **Pipeline functional specs:** see [`specs.md`](./specs.md)
> **Assignment Track:** B — NYC TLC (Class 4–8 Coverage)

---

## 1. Purpose of This Document

This file specifies **how** the pipeline is built — the tools, libraries, runtime environment, dependency constraints, and execution interface. It is intentionally kept separate from `specs.md` (which defines **what** the pipeline must do) to maintain separation of concerns.

---

## 2. Runtime Environment

| Requirement | Value |
| :--- | :--- |
| **Language** | Python 3.10+ |
| **OS Compatibility** | Windows (primary), Linux/macOS (secondary) |
| **Minimum RAM** | 4 GB (DuckDB streams Parquet; full in-memory load not required) |
| **Minimum Disk** | 2 GB free (raw + processed Parquet files) |
| **Network** | Required for Stage 1 (Ingest) only; all subsequent stages run offline |
| **Encoding** | All scripts must call `sys.stdout.reconfigure(encoding='utf-8')` on startup (Windows cp1252 safety) |

---

## 3. Python Dependencies

```
duckdb>=0.10.0
pandas>=2.0.0
pyarrow>=14.0.0
requests>=2.31.0
```

> `urllib.request` and `hashlib` are Python stdlib — no install needed.
> `logging` is Python stdlib — no install needed.

### Install Command
```bash
pip install duckdb pandas pyarrow requests
```

### Dependency Rationale

| Library | Version Floor | Used For | Why Not Alternative |
| :--- | :--- | :--- | :--- |
| `duckdb` | 0.10.0 | Reading Parquet files at scale without full RAM load; SQL-based profiling & aggregation | `polars` requires Rust toolchain; `spark` is overkill for single-machine |
| `pandas` | 2.0.0 | Row-level validation flag assignment; writing final CSVs | DuckDB lacks Python-native row mutation for flag columns |
| `pyarrow` | 14.0.0 | Parquet read/write backend for both duckdb and pandas | Required by both; no alternative needed |
| `requests` | 2.31.0 | REST API call to NYC OpenData Socrata endpoint (Stage 1, Mode 3) | `urllib.request` lacks `params={}` dict support cleanly for Socrata `$limit` |
| `urllib.request` | stdlib | Streaming large Parquet/CSV downloads with custom User-Agent header | `requests` buffers entire file in memory; `urllib` streams to disk chunk-by-chunk |

---

## 4. Module Dependency Graph

```
main.py
   |
   +-- src/utils/logger.py              [NEW — shared across all stages]
   |       uses: logging (stdlib), os, sys
   |       exports: setup_logger(), get_logger()
   |
   +-- src/ingestion/download_data.py
   |       uses: urllib.request, requests, hashlib, json, duckdb
   |       uses: src.utils.logger.get_logger()
   |
   +-- src/validation/validate.py
   |       uses: duckdb, pandas
   |       uses: src.utils.logger.get_logger()
   |       depends on: download_data.py output (manifest + raw parquet)
   |
   +-- src/modeling/transform.py
   |       uses: pandas
   |       uses: src.utils.logger.get_logger()
   |       depends on: validate.py output (validated DataFrame)
   |
   +-- src/modeling/metrics.py
   |       uses: pandas
   |       uses: src.utils.logger.get_logger()
   |       depends on: transform.py output (clean DataFrame)
   |
   +-- src/output/report.py
           uses: pandas, json
           uses: src.utils.logger.get_logger()
           depends on: metrics.py output (metrics list)
```

No circular dependencies. `utils/logger.py` is the only shared dependency — it is a leaf node (imports nothing from this project). All other stages are **decoupled via filesystem** (not in-memory chained calls).

### Python Package Markers (`__init__.py`)

The following empty `__init__.py` files are required so that cross-module imports (e.g. `from src.utils.logger import get_logger`) resolve correctly:

```
src/__init__.py
src/utils/__init__.py
src/ingestion/__init__.py
src/validation/__init__.py
src/modeling/__init__.py
src/output/__init__.py
```

---

## 5. Logging Specification

| Setting | Value |
| :--- | :--- |
| **Logger name** | `tlc_pipeline` |
| **Log file** | `logs/pipeline.log` (auto-created on first run) |
| **Log level** | `INFO` for normal operation; `WARNING` for flagged anomalies; `ERROR` for assertion failures |
| **Format** | `%(asctime)s [%(levelname)s] %(message)s` |
| **Console output** | Yes — mirror all log lines to stdout |
| **File mode** | `a` (append) — logs accumulate across runs; each run is identifiable by its timestamp block |

**Log line conventions per stage:**

```
# Ingest
[INGEST][yellow_trips]   status: OK    rows: 2,964,624   size_mb: 47.65   md5: 10dff36f...
[INGEST][taxi_zones]     status: SKIP  rows: 265         (MD5 match, re-download skipped)
[INGEST][taxi_zones]     status: OK    rows: 265         (MD5 mismatch -- re-downloading)
[INGEST][indicators_api] status: OK    records: 300

# Validate
[VALIDATE] Total rows: 2,964,624
[VALIDATE] VALID_OPERATIONAL: 2,841,728  (95.85%)
[VALIDATE] Flagged rows:        122,896   (4.15%)
[VALIDATE] Negative-fare trips:  37,448   Total value: -$1,418,290.45
[VALIDATE] ASSERT-01: PASS (row count matches manifest)
[VALIDATE] ASSERT-02: PASS (95.85% >= 90% threshold)
[VALIDATE] ASSERT-03: PASS (265 zones resolved)

# Transform
[TRANSFORM] Imputed NULL congestion_surcharge: 140,162 rows -> 0.0
[TRANSFORM] Imputed NULL Airport_fee: 140,162 rows -> 0.0
[TRANSFORM] Wrote trips_clean.parquet: 2,841,728 rows
[TRANSFORM] Wrote trips_flagged.parquet: 122,896 rows
[TRANSFORM] Wrote trips_refunds.parquet: 37,448 rows

# Metrics
[METRICS] M-01 Avg Fare/Mile: $X.XX
[METRICS] M-02 Peak HDR (hour 18): $XX.XX/hr
[METRICS] M-03 Top zone: Midtown Center (N trips at peak)
[METRICS] M-04 CFCR: XX.X%
[METRICS] M-05 COY: 95.85%

# Output
[OUTPUT] Wrote kpi_summary.csv
[OUTPUT] Wrote known_unknown_assumptions.md
[OUTPUT] Pipeline complete. Duration: Xs
```

---

## 6. CLI Interface

`main.py` is the single entry point. It accepts the following arguments:

```bash
python main.py --month YYYY-MM [--force-ingest] [--log-level {DEBUG,INFO,WARNING}]
```

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--month` | `str` | *(required)* | Month to process, e.g. `2024-01`. Controls which Parquet file URL is constructed for S1. |
| `--force-ingest` | `flag` | `False` | Forces Stage 1 to re-download all source files even if MD5 matches the manifest. |
| `--log-level` | `str` | `INFO` | Sets logging verbosity. `DEBUG` emits per-row validation stats. |

### Example Runs

```bash
# Standard first run
python main.py --month 2024-01

# Re-run on same month (skips download, re-computes all metrics)
python main.py --month 2024-01

# Force fresh download of all sources
python main.py --month 2024-01 --force-ingest

# Debug run with verbose row-level output
python main.py --month 2024-01 --log-level DEBUG

# Process a different month (February 2024)
python main.py --month 2024-02
```

---

## 7. Idempotency Contract

Re-running the pipeline on the same `--month` value must produce **byte-identical output files** in `data/processed/`:

| Guarantee | Mechanism |
| :--- | :--- |
| Same raw data | MD5 manifest check in Stage 1 prevents re-download of changed files |
| Same validation flags | All validation logic is deterministic (no random seeds, no timestamp-dependent logic) |
| Same KPI values | All metrics are pure aggregations over deterministic filtered sets |
| Same output file sizes | Parquet written with fixed sort order (`tpep_pickup_datetime ASC`) |

> **Breaking the contract:** If a Parquet file is updated upstream (new MD5), the pipeline will re-download, log `[INGEST] MD5 mismatch — re-downloading`, and reprocess.

---

## 8. Error Handling Contract

| Failure Scenario | Response |
| :--- | :--- |
| Network timeout / HTTP error during download | `RuntimeError` raised with URL + status code; pipeline halts; log `[ERROR]` |
| Downloaded file MD5 doesn't match manifest on re-run | Log `[INGEST] MD5 mismatch -- re-downloading`; re-download; continue |
| ASSERT-01 fails (row count mismatch) | `AssertionError` with message; pipeline halts at Stage 2 |
| ASSERT-02 fails (< 90% clean rows) | `AssertionError` with actual %; pipeline halts |
| ASSERT-03 fails (zone CSV missing critical LocationIDs) | `AssertionError` with missing IDs listed; pipeline halts |
| Zone join produces unresolved IDs at row level | Log warning; those rows receive `FLAG_UNKNOWN_LOCATION`; pipeline continues |
| Output directory not writable | `OSError` raised with path; pipeline halts; log `[ERROR]` |
