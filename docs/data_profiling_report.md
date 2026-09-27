# 🔍 Data Profiling & Business Validation Report (Class 6)

## 1. Executive Summary
This report presents the empirical data quality profile of the **January 2024 NYC Yellow Taxi dataset (2,964,624 raw records)**. It defines business-oriented validation rules and audit checks to ensure clean operational modeling without silently deleting dirty data.

---

## 2. Detailed Data Quality Audit Results

### A. Temporal & Date Boundaries
* **Total Records Analyzed:** 2,964,624
* **Date Range:** Pickups span from `2002-12-31 22:59:39` to `2024-02-01 00:01:15`.
* **Out-of-Bound Trips:**
  * Pickups before Jan 1, 2024: **15 trips**
  * Pickups after Jan 31, 2024: **3 trips**
  * Dropoff timestamp prior to pickup timestamp (`dropoff < pickup`): **56 trips**

### B. Trip Physics & Telematics
* **Zero Distance Trips (`distance = 0`):** **59,613 trips**
* **Speed Anomalies (`speed > 100 mph`):** **1,024 trips** (Max recorded speed: 85,200 mph due to faulty GPS timestamps).
* **Extreme Long Trips (`duration > 24 hours`):** **16 trips**

### C. Financial & Billing Integrity
* **Negative Fare Amounts (`fare < $0`):** **37,448 trips** (Total negative fare amount: -$1,418,290.45 due to refunds/voids).
* **Negative Total Amounts (`total < $0`):** **35,504 trips**
* **Component Math Discrepancy:** **761,838 trips (25.7%)** where:
  $$\text{total\_amount} \neq \text{fare} + \text{extra} + \text{mta\_tax} + \text{tip} + \text{tolls} + \text{improvement\_surcharge} + \text{congestion\_surcharge} + \text{Airport\_fee}$$
* **Invalid Payment Types:** **140,162 trips** with unknown/null payment codes.

### D. Missing Value Summary

| Column Name | Missing Count | Missing Percentage | Cause / Business Interpretation |
| :--- | :--- | :--- | :--- |
| `passenger_count` | 140,162 | 4.73% | Dispatched or unmetered trips without manual passenger entry |
| `RatecodeID` | 140,162 | 4.73% | Missing tariff structure flag |
| `store_and_fwd_flag` | 140,162 | 4.73% | Missing offline transmission status |
| `congestion_surcharge`| 140,162 | 4.73% | Legacy meter firmware missing surcharge breakdown |
| `Airport_fee` | 140,162 | 4.73% | Legacy meter firmware missing airport fee field |

---

## 3. Business-Oriented Validation Rules (No Silent Deletion)

Instead of silently dropping invalid rows, our pipeline applies explicit validation status flags (`validation_flag` column):

| Validation Status Code | Business Rule Criteria | Action in Pipeline |
| :--- | :--- | :--- |
| `VALID_OPERATIONAL` | Meets all date range, timestamp, financial, and distance bounds | Included in core KPI calculations |
| `FLAG_OUT_OF_BOUND_DATE` | Pickup date outside Jan 1–Jan 31, 2024 | Isolated in audit table |
| `FLAG_INVALID_TIMESTAMPS`| Dropoff timestamp $\le$ Pickup timestamp | Isolated in audit table |
| `FLAG_NEGATIVE_FINANCIAL`| Fare amount $< \$0$ or Total amount $< \$0$ | Flagged for refund/chargeback audit |
| `FLAG_TELEMATICS_ERROR` | Distance $= 0$ or Speed $> 100\text{ mph}$ | Excluded from speed/distance averages |
| `FLAG_MATH_DISCREPANCY` | $| \text{total} - \text{calculated\_sum} | > \$0.05$ | Flagged for revenue reconciliation |
