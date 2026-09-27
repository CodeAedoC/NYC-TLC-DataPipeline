"""
src/modeling/transform.py
Stage 3 — CLEAN + TRANSFORM (single pass, specs.md TRF-01 through TRF-11)

Execution order (per specs.md design rationale):
  1. Enrich ALL validated rows (TRF-01 to TRF-09)
  2. Route by validation_flag into 3 output sets (TRF-10 / TRF-11 / REF-02)

Returns dict with keys: 'clean', 'flagged', 'refunds'
All three DataFrames carry the full enriched schema.
"""
import os

import pandas as pd

from src.utils.logger import get_logger


def _get_project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Enrichment (TRF-01 to TRF-09) — applied to ALL rows
# ---------------------------------------------------------------------------

def _enrich(df: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    logger = get_logger()

    # TRF-01: join pickup borough & zone
    pu_map = zones.rename(columns={
        "LocationID": "PULocationID",
        "Borough": "pu_borough",
        "Zone": "pu_zone"
    })[["PULocationID", "pu_borough", "pu_zone"]]
    df = df.merge(pu_map, on="PULocationID", how="left")

    # TRF-02: join dropoff borough & zone
    do_map = zones.rename(columns={
        "LocationID": "DOLocationID",
        "Borough": "do_borough",
        "Zone": "do_zone"
    })[["DOLocationID", "do_borough", "do_zone"]]
    df = df.merge(do_map, on="DOLocationID", how="left")

    # TRF-03: trip_duration_min (only meaningful where dropoff > pickup)
    df["trip_duration_min"] = (
        (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).dt.total_seconds() / 60
    )

    # TRF-04: avg_speed_mph (only where duration > 0; else None)
    dur_hr = df["trip_duration_min"] / 60
    df["avg_speed_mph"] = (df["trip_distance"] / dur_hr.replace(0, float("nan"))).round(4)

    # TRF-05: reconciled_total
    df["reconciled_total"] = (
        df["fare_amount"]
        + df["extra"]
        + df["mta_tax"]
        + df["tip_amount"]
        + df["tolls_amount"]
        + df["improvement_surcharge"]
        + df["congestion_surcharge"].fillna(0)
        + df["Airport_fee"].fillna(0)
    ).round(2)

    # TRF-06: impute NULL congestion_surcharge — logged (not silent)
    null_cong = df["congestion_surcharge"].isna().sum()
    df["congestion_surcharge"] = df["congestion_surcharge"].fillna(0.0)
    logger.info(f"[TRANSFORM] Imputed NULL congestion_surcharge: {null_cong:,} rows -> 0.0")

    # TRF-07: impute NULL Airport_fee — logged (not silent)
    null_af = df["Airport_fee"].isna().sum()
    df["Airport_fee"] = df["Airport_fee"].fillna(0.0)
    logger.info(f"[TRANSFORM] Imputed NULL Airport_fee: {null_af:,} rows -> 0.0")

    # TRF-08: time features
    df["pickup_hour"] = df["tpep_pickup_datetime"].dt.hour
    df["pickup_dow"] = df["tpep_pickup_datetime"].dt.dayofweek  # 0=Monday

    # TRF-09: airport trip flag (JFK=132, LGA=138 per specs.md)
    df["is_airport_trip"] = df["PULocationID"].isin([132, 138])

    return df


# ---------------------------------------------------------------------------
# Routing (TRF-10 / TRF-11 / REF-02)
# ---------------------------------------------------------------------------

def _route(df: pd.DataFrame) -> dict:
    """
    TRF-10: VALID_OPERATIONAL rows -> clean
    TRF-11: flagged rows -> flagged
    REF-02: FLAG_NEGATIVE_FINANCIAL subset -> refunds
    """
    clean_mask = df["validation_flag"].str.contains("VALID_OPERATIONAL", na=False)
    clean = df[clean_mask].copy()
    flagged = df[~clean_mask].copy()
    refunds = flagged[
        flagged["validation_flag"].str.contains("FLAG_NEGATIVE_FINANCIAL", na=False)
    ].copy()
    return {"clean": clean, "flagged": flagged, "refunds": refunds}


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_outputs(datasets: dict) -> None:
    logger = get_logger()
    root = _get_project_root()
    processed = os.path.join(root, "data", "processed")
    audit = os.path.join(processed, "audit")
    os.makedirs(audit, exist_ok=True)

    # TRF-10 / OUT-01: clean trips sorted for idempotency
    clean_path = os.path.join(processed, "trips_clean.parquet")
    datasets["clean"].sort_values("tpep_pickup_datetime").to_parquet(clean_path, index=False)
    logger.info(f"[TRANSFORM] Wrote trips_clean.parquet: {len(datasets['clean']):,} rows")

    # TRF-11 / OUT-02: flagged trips
    flagged_path = os.path.join(audit, "trips_flagged.parquet")
    datasets["flagged"].to_parquet(flagged_path, index=False)
    logger.info(f"[TRANSFORM] Wrote trips_flagged.parquet: {len(datasets['flagged']):,} rows")

    # REF-02: refund subset
    refunds_path = os.path.join(audit, "trips_refunds.parquet")
    datasets["refunds"].to_parquet(refunds_path, index=False)
    logger.info(f"[TRANSFORM] Wrote trips_refunds.parquet: {len(datasets['refunds']):,} rows")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_transform(validated_df: pd.DataFrame, zone_csv_path: str) -> dict:
    """
    Enrich all validated rows, then route into clean / flagged / refunds.
    Returns dict: {'clean': DataFrame, 'flagged': DataFrame, 'refunds': DataFrame}
    """
    logger = get_logger()
    logger.info("=== STAGE 3: TRANSFORM + CLEAN ===")

    zones = pd.read_csv(zone_csv_path)

    # Step 1: enrich ALL rows (TRF-01 to TRF-09)
    enriched = _enrich(validated_df, zones)

    # Step 2: route by validation_flag (TRF-10 / TRF-11 / REF-02)
    datasets = _route(enriched)

    # Step 3: write output files
    _write_outputs(datasets)

    return datasets
