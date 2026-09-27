"""
src/validation/validate.py
Stage 2 — VALIDATE
Covers specs.md VAL-01a through VAL-10, REF taxonomy, and ASSERT-01 through ASSERT-03.

Produces a `validation_flag` column on every row.
Flags are pipe-delimited (e.g. FLAG_NEGATIVE_FINANCIAL|FLAG_TELEMATICS_ERROR).
Rows with no flags receive VALID_OPERATIONAL.
No rows are dropped.
"""
import os

import duckdb
import pandas as pd

from src.utils.logger import get_logger


# ---------------------------------------------------------------------------
# Internal flag helpers
# ---------------------------------------------------------------------------

def _append_flag(series: pd.Series, mask: pd.Series, flag: str) -> pd.Series:
    """Append `flag` to rows where mask is True, pipe-separated."""
    series = series.copy()
    series[mask] = series[mask].apply(
        lambda v: flag if v == "" else f"{v}|{flag}"
    )
    return series


# ---------------------------------------------------------------------------
# Rule groups
# ---------------------------------------------------------------------------

def _temporal_rules(df: pd.DataFrame) -> pd.DataFrame:
    """VAL-01a, VAL-01b, VAL-02a, VAL-02b"""
    # VAL-01a: pickup before scope start
    mask = df["tpep_pickup_datetime"] < pd.Timestamp("2024-01-01")
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_OUT_OF_BOUND_DATE")

    # VAL-01b: pickup at or after scope end
    mask = df["tpep_pickup_datetime"] >= pd.Timestamp("2024-02-01")
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_OUT_OF_BOUND_DATE")

    # VAL-02a: dropoff <= pickup (impossible order)
    mask = df["tpep_dropoff_datetime"] <= df["tpep_pickup_datetime"]
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_INVALID_TIMESTAMPS")

    # VAL-02b: trip_duration_min > 1440 (>24 hrs, valid timestamp order)
    valid_order = df["tpep_dropoff_datetime"] > df["tpep_pickup_datetime"]
    dur_min = (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).dt.total_seconds() / 60
    mask = valid_order & (dur_min > 1440)
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_DURATION_ANOMALY")

    return df


def _financial_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    VAL-03: negative financials + REF taxonomy (Meter Void / Chargeback / Partial Adjustment)
    VAL-04: fare math discrepancy
    """
    # REF: Meter Void — fare<0, distance=0, total<0
    void_mask = (df["fare_amount"] < 0) & (df["trip_distance"] == 0) & (df["total_amount"] < 0)
    df["validation_flag"] = _append_flag(df["validation_flag"], void_mask, "FLAG_NEGATIVE_FINANCIAL")
    df["validation_flag"] = _append_flag(df["validation_flag"], void_mask, "FLAG_TELEMATICS_ERROR")

    # REF: Payment Chargeback — fare<0, distance>0, total<0
    chargeback_mask = (df["fare_amount"] < 0) & (df["trip_distance"] > 0) & (df["total_amount"] < 0)
    df["validation_flag"] = _append_flag(df["validation_flag"], chargeback_mask, "FLAG_NEGATIVE_FINANCIAL")

    # REF: Partial Adjustment — fare<0, total>=0
    partial_mask = (df["fare_amount"] < 0) & (df["total_amount"] >= 0)
    df["validation_flag"] = _append_flag(df["validation_flag"], partial_mask, "FLAG_NEGATIVE_FINANCIAL")

    # VAL-04: fare math discrepancy (does NOT prevent VALID_OPERATIONAL on its own)
    computed = (
        df["fare_amount"]
        + df["extra"]
        + df["mta_tax"]
        + df["tip_amount"]
        + df["tolls_amount"]
        + df["improvement_surcharge"]
        + df["congestion_surcharge"].fillna(0)
        + df["Airport_fee"].fillna(0)
    )
    math_mask = (df["total_amount"] - computed).abs() > 0.05
    df["validation_flag"] = _append_flag(df["validation_flag"], math_mask, "FLAG_MATH_DISCREPANCY")

    return df


def _telematics_rules(df: pd.DataFrame) -> pd.DataFrame:
    """VAL-05: zero distance. VAL-06: impossible speed."""
    # VAL-05: zero distance
    mask = df["trip_distance"] == 0
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_TELEMATICS_ERROR")

    # VAL-06: avg_speed_mph > 100 (compute inline — only where duration > 0)
    valid_order = df["tpep_dropoff_datetime"] > df["tpep_pickup_datetime"]
    dur_hr = (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).dt.total_seconds() / 3600
    speed = df["trip_distance"] / dur_hr.replace(0, float("nan"))
    speed_mask = valid_order & (speed > 100)
    df["validation_flag"] = _append_flag(df["validation_flag"], speed_mask, "FLAG_TELEMATICS_ERROR")

    return df


def _location_rules(df: pd.DataFrame) -> pd.DataFrame:
    """VAL-07: unknown location IDs 264/265."""
    mask = df["PULocationID"].isin([264, 265]) | df["DOLocationID"].isin([264, 265])
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_UNKNOWN_LOCATION")
    return df


def _attribute_rules(df: pd.DataFrame) -> pd.DataFrame:
    """VAL-08: null critical fields. VAL-09: invalid payment type. VAL-10: cash tip anomaly."""
    # VAL-08: null passenger count or RatecodeID
    mask = df["passenger_count"].isna() | df["RatecodeID"].isna()
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_MISSING_ATTRIBUTES")

    # VAL-09: payment type not in (1,2,3,4)
    mask = ~df["payment_type"].isin([1, 2, 3, 4])
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_INVALID_PAYMENT_TYPE")

    # VAL-10: cash payment with tip recorded
    mask = (df["payment_type"] == 2) & (df["tip_amount"] > 0)
    df["validation_flag"] = _append_flag(df["validation_flag"], mask, "FLAG_CASH_TIP_ANOMALY")

    return df


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def _assert_row_count(df: pd.DataFrame, manifest: dict) -> None:
    """ASSERT-01: row count read from parquet must match manifest."""
    expected = manifest.get("yellow_trips", {}).get("rows")
    if expected is None:
        raise AssertionError("ASSERT-01 FAILED: 'yellow_trips' not found in manifest.")
    actual = len(df)
    if actual != expected:
        raise AssertionError(
            f"ASSERT-01 FAILED: parquet has {actual:,} rows but manifest records {expected:,}."
        )
    get_logger().info(f"[VALIDATE] ASSERT-01: PASS (row count matches manifest: {actual:,})")


def _assert_clean_ratio(df: pd.DataFrame) -> None:
    """ASSERT-02: >= 90% of rows must be VALID_OPERATIONAL."""
    clean = df["validation_flag"].str.contains("VALID_OPERATIONAL", na=False).sum()
    total = len(df)
    pct = clean / total * 100
    if pct < 90.0:
        raise AssertionError(
            f"ASSERT-02 FAILED: only {pct:.2f}% VALID_OPERATIONAL (threshold: 90%)."
        )
    get_logger().info(f"[VALIDATE] ASSERT-02: PASS ({pct:.2f}% >= 90% threshold)")


def _assert_zones_complete(zone_csv_path: str) -> None:
    """ASSERT-03: taxi_zone_lookup.csv must contain LocationIDs 1 through 263 at minimum."""
    import pandas as pd
    zones = pd.read_csv(zone_csv_path)
    present = set(zones["LocationID"].tolist())
    required = set(range(1, 264))
    missing = required - present
    if missing:
        raise AssertionError(
            f"ASSERT-03 FAILED: {len(missing)} required zone IDs missing: {sorted(missing)[:10]}..."
        )
    get_logger().info(f"[VALIDATE] ASSERT-03: PASS ({len(present)} zones resolved)")


# ---------------------------------------------------------------------------
# Summary logging
# ---------------------------------------------------------------------------

def _log_summary(df: pd.DataFrame) -> None:
    logger = get_logger()
    total = len(df)
    n_clean = df["validation_flag"].str.contains("VALID_OPERATIONAL", na=False).sum()
    n_flagged = total - n_clean

    logger.info(f"[VALIDATE] Total rows: {total:,}")
    logger.info(f"[VALIDATE] VALID_OPERATIONAL: {n_clean:,}  ({n_clean/total*100:.2f}%)")
    logger.info(f"[VALIDATE] Flagged rows:       {n_flagged:,}  ({n_flagged/total*100:.2f}%)")

    # REF-03: negative-fare summary (specs.md §6)
    neg_mask = df["validation_flag"].str.contains("FLAG_NEGATIVE_FINANCIAL", na=False)
    n_neg = neg_mask.sum()
    total_neg_value = df.loc[neg_mask, "total_amount"].sum()
    logger.info(
        f"[VALIDATE] Negative-fare trips: {n_neg:,}  Total value: ${total_neg_value:,.2f}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_validation(parquet_path: str, zone_csv_path: str, manifest: dict) -> pd.DataFrame:
    """
    Load raw parquet, apply all VAL rules + REF taxonomy, run ASSERTs.
    Returns DataFrame with `validation_flag` column on every row.
    Raises AssertionError (halts pipeline) if any ASSERT fails.
    """
    logger = get_logger()
    logger.info("=== STAGE 2: VALIDATE ===")

    # Load via DuckDB — avoids full RAM load
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM '{parquet_path}'").df()

    # ASSERT-01 first — before doing anything else
    _assert_row_count(df, manifest)

    # Initialise empty flag column
    df["validation_flag"] = ""

    # Apply all rule groups
    df = _temporal_rules(df)
    df = _financial_rules(df)
    df = _telematics_rules(df)
    df = _location_rules(df)
    df = _attribute_rules(df)

    # Mark remaining clean rows (those with no flags OR only FLAG_MATH_DISCREPANCY)
    clean_mask = df["validation_flag"].isin(["", "FLAG_MATH_DISCREPANCY"])
    df["validation_flag"] = _append_flag(df["validation_flag"], clean_mask, "VALID_OPERATIONAL")

    # Post-flagging assertions
    _assert_clean_ratio(df)
    _assert_zones_complete(zone_csv_path)

    # Log summary (REF-03 included)
    _log_summary(df)

    return df
