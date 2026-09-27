# NYC TLC Operational Data Pipeline

A production-grade data engineering pipeline designed to ingest, validate, clean, enrich, and aggregate New York City Taxi and Limousine Commission (TLC) trip data. 

Built to handle raw, multi-modal ingestion while maintaining strict financial and operational data integrity, this pipeline produces highly auditable Key Performance Indicators (KPIs) for downstream business use.

> 📄 **[Project Report (PDF)](./FDE_Assignment2_Report.pdf)** — 2-page summary covering architecture, validation rules, KPI results, known/unknowns, assumptions, and evidence-backed conclusions.

---

## 🏗️ Architecture (6-Stage Flow)

The pipeline is entirely decoupled via the filesystem (using Parquet as the handoff medium), meaning it can process large datasets gracefully without requiring full-scale in-memory clusters.

1. **EXTRACT:** Pulls raw Parquet data, taxonomic CSVs, and REST API metadata. Hashes incoming files via MD5 and manages state via `ingestion_manifest.json` to guarantee idempotency.
2. **VALIDATE:** Streams raw data via DuckDB to avoid RAM bloat. Subjects the data to 10 strict Validation Rules (VAL-01 to VAL-10) checking temporal bounds, telematics, and financial anomalies. Implements rigorous `ASSERT` breakpoints that halt the pipeline if data integrity is compromised.
3. **CLEAN & TRANSFORM:** Enriches all rows (Zone names, durations, speeds, and reconciled totals). Routes rows dynamically based on the Validation flag:
   - Clean data proceeds to KPI computation.
   - Flagged anomalies are isolated in audit tables.
   - Refunds and chargebacks are quarantined.
4. **SAVE:** Computes 5 critical KPIs (M-01 to M-05) focusing on Driver Revenue, Zone Demand, and Congestion Fee Capture.
5. **LOG:** A cross-cutting `tlc_pipeline` logger captures every state change, anomaly count, and runtime error, persisting to `logs/pipeline.log`.
6. **REPORT:** Auto-generates `docs/known_unknown_assumptions.md` summarizing the run, exposing known limitations, and proving the math behind the metrics.

---

## 💻 Tech Stack

* **Language:** Python 3.10+
* **Data Processing:** DuckDB (fast SQL on Parquet), Pandas (row-level flagging and aggregations)
* **File Formats:** Parquet, CSV, JSON
* **Core Libraries:** `duckdb`, `pandas`, `pyarrow`, `requests`

---

## 🚀 How to Run

The pipeline uses a single CLI entry point:

**Standard Run:**
```bash
python main.py --month 2024-01
```
*(If the raw data is already cached and the MD5 matches, ingestion is intelligently skipped).*

**Force Fresh Download:**
```bash
python main.py --month 2024-01 --force-ingest
```

**Debug Mode:**
```bash
python main.py --month 2024-01 --log-level DEBUG
```

---

## 📂 Project Structure

```
├── main.py                     # Pipeline orchestrator and CLI entry point
├── data/
│   ├── raw/                    # Immutable source data and manifest
│   └── processed/              # trips_clean.parquet, kpi_summary.csv
│       └── audit/              # trips_flagged.parquet, trips_refunds.parquet
├── docs/
│   ├── specs.md                # The definitive business logic "Bible"
│   ├── tech_requirements.md    # Technical execution & constraints
│   ├── data_profiling_report.md# Deep dive into raw data anomalies
│   ├── source_map.md           # Schema and ingestion source reference
│   ├── FDE_journey.md          # Log of strategic decisions and methodology
│   └── known_unknown_assumptions.md # Auto-generated report per run
├── src/
│   ├── ingestion/              # HTTP, API extraction & MD5 caching
│   ├── validation/             # VAL rules & assertions (DuckDB/Pandas)
│   ├── modeling/               # transform.py (enrich/route) & metrics.py (KPIs)
│   ├── output/                 # CSV/Markdown writers
│   └── utils/                  # Centralised logging
└── logs/                       # Persistent pipeline.log
```

---

## 📊 Pipeline Outputs

After a successful run, the following artifacts are generated:
1. `data/processed/trips_clean.parquet`: The `VALID_OPERATIONAL` dataset.
2. `data/processed/audit/trips_flagged.parquet`: Rows violating any validation rule.
3. `data/processed/audit/trips_refunds.parquet`: Quarantined negative-fare trips.
4. `data/processed/kpi_summary.csv`: The final computed KPIs (M-01 through M-05).
5. `docs/known_unknown_assumptions.md`: Detailed breakdown of flagged rows, refund totals, and assumptions applied during the run.

### 🚩 Where are the flags logged?
To avoid bloating the console logs, the exact flags are **not** printed line-by-line in `pipeline.log`. Instead, they are recorded in two places:
* **Row-level:** Every flagged row is saved to `data/processed/audit/trips_flagged.parquet` with its specific pipe-delimited flags appended in the `validation_flag` column.
* **Summary-level:** The `docs/known_unknown_assumptions.md` report auto-generates a **Validation Flag Summary** table showing the exact counts of how many times each flag was triggered during the run.
