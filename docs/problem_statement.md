# 🎯 Executive Problem Statement: NYC TLC Operational Data Pipeline

## 1. Context & Business Challenge
The **NYC Taxi and Limousine Commission (TLC)** oversees yellow taxi operations across New York City. Leadership relies on operational metrics to monitor fleet efficiency, driver earnings, congestion fee compliance, and borough-to-borough mobility.

However, raw trip telemetry and transaction data collected directly from in-cab meters and mobile payment systems are **fragmented, noisy, and mathematically inconsistent**.

---

## 2. Empirical Findings from Raw Data Analysis
A detailed profiling of the **January 2024 Yellow Taxi dataset (2,964,624 raw records)** revealed critical data quality issues:

| Data Quality Category | Issue Description | Contaminated Row Count | Impact on Raw Metrics |
| :--- | :--- | :--- | :--- |
| **Financial Integrity** | Negative fares & negative totals (< $0) | **37,448 trips** | Deflates total revenue and distorts average fare per trip |
| **Component Math Mismatch** | Total amount != sum of (fare + taxes + tips + fees) | **761,838 trips (25.7%)** | Destroys auditability; leadership cannot trust billing totals |
| **Missing Attributes** | Null passenger count, RatecodeID, fees | **140,162 trips (4.73%)** | Breaks passenger volume & tariff rate code analytics |
| **Telematics & GPS Errors** | 0-mile trips or physically impossible speeds (>100 mph) | **60,637 trips** | Skews trip speed and vehicle efficiency calculations |
| **Temporal Anomalies** | Pickup date outside Jan 2024 (e.g., year 2002) or dropoff < pickup | **74 trips** | Causes time-series aggregation corruption |
| **Spatial Gaps** | Unknown Pickup/Dropoff LocationIDs (264 / 265) | **40,101 trips** | Prevents borough-level origin-destination mapping |

**Summary Result:** **122,896 records (4.15%)** are severely contaminated, and **761,838 records (25.7%)** suffer from component fee math discrepancies.

---

## 3. Why a Dependable Data Pipeline is Mandatory
Directly querying raw client datasets yields **untrustworthy metrics** and risks flawed operational decisions (e.g., misallocating congestion fees or miscalculating driver hourly wages). 

A dependable, automated pipeline is required to:
1. **Preserve Raw Inputs:** Maintain immutable raw data ingested across multiple modes (Parquet files, CSV lookup maps, REST API indicators).
2. **Explicit Data Validation:** Apply business-oriented validation rules and flag anomalies transparently without silent data deletion.
3. **Reconcile Financials:** Standardize component fee calculations to establish auditable revenue figures.
4. **Compute Dependable KPIs:** Deliver trustworthy operational metrics (e.g., Effective Hourly Revenue, Peak Speed Index, Congestion Fee Capture Rate) to support leadership decisions.

---

## 4. Key Stakeholders & Project Goal
* **Primary Stakeholders:** TLC Operations Leadership, Transport Policy Analysts, Fleet Operations Managers.
* **Project KPI:** **Clean Operational Yield (COY)** & **Audited Hourly Driver Revenue (HDR)**.
* **Pipeline Output Goal:** Produce a repeatable monthly operational dataset and metric summary table from raw multi-mode inputs.
