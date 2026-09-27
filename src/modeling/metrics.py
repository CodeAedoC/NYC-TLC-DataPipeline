"""
src/modeling/metrics.py
Stage 4 — METRICS (specs.md M-01 through M-05)

All metrics computed on VALID_OPERATIONAL rows only (the 'clean' DataFrame).
M-05 (COY) requires raw_total from manifest to compute over full raw dataset.
Output: list of dicts, each matching kpi_summary.csv column schema:
  metric_id, metric_name, value, unit, scope, computed_at
"""
from datetime import datetime, timezone

import pandas as pd

from src.utils.logger import get_logger

# Peak hour windows per specs.md M-03
PEAK_HOURS = list(range(7, 11)) + list(range(16, 21))  # 7-10 AM, 4-8 PM


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Individual metrics
# ---------------------------------------------------------------------------

def _m01_avg_fare_per_mile(clean: pd.DataFrame) -> dict:
    """M-01: mean(fare_amount / trip_distance) where trip_distance > 0"""
    logger = get_logger()
    valid = clean[clean["trip_distance"] > 0]
    value = round(float((valid["fare_amount"] / valid["trip_distance"]).mean()), 4)
    logger.info(f"[METRICS] M-01 Avg Fare/Mile: ${value:.4f}")
    return {
        "metric_id": "M-01",
        "metric_name": "Average Fare per Mile",
        "value": value,
        "unit": "USD/mile",
        "scope": "VALID_OPERATIONAL  trip_distance > 0",
        "computed_at": _now_iso(),
    }


def _m02_peak_hourly_driver_revenue(clean: pd.DataFrame) -> dict:
    """
    M-02: sum(reconciled_total) / sum(trip_duration_min) * 60
    Grouped by pickup_hour; reports the peak hour value.
    Uses reconciled_total (TRF-05), never total_amount.
    """
    logger = get_logger()
    # Only rows with positive duration (avoid division by zero)
    valid = clean[clean["trip_duration_min"] > 0]
    grouped = valid.groupby("pickup_hour").apply(
        lambda g: g["reconciled_total"].sum() / (g["trip_duration_min"].sum() / 60)
    )
    peak_hour = int(grouped.idxmax())
    peak_value = round(float(grouped.max()), 2)
    logger.info(f"[METRICS] M-02 Peak HDR (hour {peak_hour}): ${peak_value:.2f}/hr")
    return {
        "metric_id": "M-02",
        "metric_name": "Estimated Hourly Driver Revenue (HDR) — Peak Hour",
        "value": peak_value,
        "unit": "USD/hr",
        "scope": f"pickup_hour={peak_hour}  (peak of 24-hr distribution)",
        "computed_at": _now_iso(),
    }


def _m03_peak_demand_zone_index(clean: pd.DataFrame) -> dict:
    """M-03: top-10 pu_zone by trip count during peak hours (7-10 AM, 4-8 PM)"""
    logger = get_logger()
    peak_df = clean[clean["pickup_hour"].isin(PEAK_HOURS)]
    top_zones = peak_df["pu_zone"].value_counts().head(10)
    top_name = str(top_zones.index[0])
    top_count = int(top_zones.iloc[0])
    logger.info(f"[METRICS] M-03 Top peak zone: {top_name} ({top_count:,} trips)")
    # Store top-10 as JSON string in value for full detail in CSV
    top_10_str = "; ".join([f"{z}:{c}" for z, c in top_zones.items()])
    return {
        "metric_id": "M-03",
        "metric_name": "Peak Demand Zone Index",
        "value": top_count,
        "unit": "trips",
        "scope": f"Top zone: {top_name}  |  Top 10: {top_10_str}",
        "computed_at": _now_iso(),
    }


def _m04_congestion_fee_capture_rate(clean: pd.DataFrame) -> dict:
    """
    M-04: COUNT(congestion_surcharge > 0) / COUNT(pu_borough='Manhattan' AND NOT is_airport_trip)
    """
    logger = get_logger()
    eligible = clean[
        (clean["pu_borough"] == "Manhattan") & (~clean["is_airport_trip"])
    ]
    n_eligible = len(eligible)
    n_captured = int((eligible["congestion_surcharge"] > 0).sum())
    cfcr = round(n_captured / max(n_eligible, 1) * 100, 2)
    logger.info(f"[METRICS] M-04 CFCR: {cfcr:.2f}%  ({n_captured:,} / {n_eligible:,} eligible trips)")
    return {
        "metric_id": "M-04",
        "metric_name": "Congestion Fee Capture Rate (CFCR)",
        "value": cfcr,
        "unit": "%",
        "scope": "Manhattan non-airport VALID_OPERATIONAL trips",
        "computed_at": _now_iso(),
    }


def _m05_clean_operational_yield(clean: pd.DataFrame, raw_total: int) -> dict:
    """M-05: COUNT(VALID_OPERATIONAL) / COUNT(*) * 100 over full raw dataset"""
    logger = get_logger()
    coy = round(len(clean) / raw_total * 100, 2)
    logger.info(f"[METRICS] M-05 COY: {coy:.2f}%  ({len(clean):,} / {raw_total:,})")
    return {
        "metric_id": "M-05",
        "metric_name": "Clean Operational Yield (COY)",
        "value": coy,
        "unit": "%",
        "scope": "VALID_OPERATIONAL / full raw dataset",
        "computed_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_metrics(clean: pd.DataFrame, raw_total: int) -> list[dict]:
    """
    Compute all 5 KPIs on the clean DataFrame.
    Returns list of 5 metric dicts for kpi_summary.csv.
    """
    logger = get_logger()
    logger.info("=== STAGE 4: METRICS ===")

    return [
        _m01_avg_fare_per_mile(clean),
        _m02_peak_hourly_driver_revenue(clean),
        _m03_peak_demand_zone_index(clean),
        _m04_congestion_fee_capture_rate(clean),
        _m05_clean_operational_yield(clean, raw_total),
    ]
