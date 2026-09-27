# Forward Deployed Engineer (FDE) Journey: NYC TLC Pipeline

This document captures the strategic decision-making and execution flow driven by the FDE during the development of the NYC TLC Operational Data Pipeline. 

From initial data discovery to the final pipeline execution, this chronicles the shift from raw, messy domain data to a hardened, auditable data product.

---

## 1. Requirements Gathering & Domain Discovery
* **Target Identification:** Recognized that the primary objective was building a robust data pipeline on top of the NYC Taxi & Limousine Commission (TLC) dataset.
* **Problem Definition:** Initiated the effort by requesting raw data ingestion from the TLC portal to figure out the exact business problems and anomalies hidden within the data.
* **Separation of Concerns:** Made the crucial architectural decision to split functional logic from implementation mechanics. Dictated that `specs.md` would be the absolute "source of truth" (the Bible) for business rules, while `tech_requirements.md` would house the engineering constraints.

## 2. Deep Data Profiling
* **Diagnostic Scripting:** Rather than blindly writing pipeline code, directed the creation of temporary diagnostic scripts (e.g., `scratch/analyze_business_data.py`). 
* **Anomaly Detection:** This investigative phase exposed massive data quality issues:
  * Over 760,000 rows (25.7%) suffered from math discrepancies where `fare + taxes` did not equal `total_amount` (later traced to a consistent -$2.50 vendor encoding error).
  * Found extensive negative financials (voids and chargebacks) and severe temporal anomalies (e.g., trips lasting > 24 hours or logging impossibly high speeds).

## 3. Authoring the Blueprint (`specs.md`)
* **Rule Taxonomy:** Established a strict taxonomy for validation rules (`VAL-01` to `VAL-10`) and refund handling (`REF-01` to `REF-04`).
* **Meticulous Review:** Caught logical inconsistencies in the drafted specs—specifically calling out duplicate rule IDs (e.g., `VAL-01a` named similarly across different tables) which could have caused dangerous flagging ambiguities downstream. Ensured the specs were flawless before any code was written.
* **Workflow Clarification:** Asked incisive questions regarding the design of Stage 3 ("Why does specs.md place filtering and enrichment in the same stage file?"). This forced the pipeline architecture to adopt a single-pass "enrich-then-route" model, ensuring that audit tables retained full contextual columns.

## 4. Architectural Planning
* **Pipeline Directive:** Issued a strict, 6-stage operational plan using the `/plan` command:
  ```
  EXTRACT → VALIDATE → CLEAN → TRANSFORM → SAVE → LOG
  ```
* **Enforcing Assertions:** Advocated for hard assertions (`ASSERT-01` through `ASSERT-03`) to ensure the pipeline would halt gracefully if raw data integrity or minimum valid row thresholds (< 90%) were compromised.

## 5. QA, Debugging, and Execution
* **Approving the Plan:** Reviewed the generated `pipeline_implementation_plan.md` and authorized its execution only after all open questions (such as how to handle `FLAG_MATH_DISCREPANCY` in KPI metrics) were resolved directly against the `specs.md`.
* **Supervising the Build:** Commanded the translation of the plan into the actual Python modules (`validate.py`, `transform.py`, `metrics.py`, `logger.py`, `main.py`).
* **Live Troubleshooting:** During the first end-to-end run, the pipeline correctly halted because `ASSERT-02` failed (Valid Operational yield dropped to 71% instead of 90%). 
* **The Fix:** Recognised that the `FLAG_MATH_DISCREPANCY` (25% of data) was overly penalising rows that were otherwise completely operational. Supervised the logic fix in `validate.py` and `transform.py` to decouple math discrepancies from operational validity.
* **Final Success:** Triggered the final run, watching the Valid Operational Yield jump to **91.97%**, successfully generating all KPIs, output parquets, and the `known_unknown_assumptions.md` report in a blistering 18.4 seconds.

---
*This journey demonstrates the core FDE mindset: investigating the unknown, cementing business logic before writing code, enforcing strict data quality guardrails, and aggressively debugging to achieve a production-ready system.*
