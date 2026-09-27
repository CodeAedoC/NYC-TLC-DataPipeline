"""
src/ingestion/download_data.py
Stage 1 — EXTRACT
Covers specs.md ING-01 through ING-06.

Retrieval modes:
  Mode 1 — CSV file (HTTP):      taxi_zone_lookup.csv
  Mode 2 — Parquet file (HTTP):  yellow_tripdata_{YYYY}-{MM}.parquet
  Mode 3 — REST API (Socrata):   tlc_industry_indicators.json
"""
import os
import sys
import hashlib
import json
import urllib.request
from datetime import datetime, timezone

import requests
import duckdb

from src.utils.logger import get_logger

# URL templates
TAXI_ZONE_CSV_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi+_zone_lookup.csv"
TRIP_PARQUET_URL_TMPL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{month}.parquet"
NYC_OPENDATA_INDICATORS_API = "https://data.cityofnewyork.us/resource/v6kb-cqej.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _raw_dir() -> str:
    d = os.path.join(_get_project_root(), "data", "raw")
    os.makedirs(d, exist_ok=True)
    return d


def _manifest_path() -> str:
    return os.path.join(_raw_dir(), "ingestion_manifest.json")


def load_manifest() -> dict:
    """ING-03: Load existing manifest or return empty dict."""
    path = _manifest_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(manifest: dict) -> None:
    """ING-03: Persist manifest after each successful source write."""
    with open(_manifest_path(), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _md5(filepath: str) -> str:
    """ING-02: Compute MD5 hash of a local file."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _skip_if_cached(source_id: str, target_path: str, manifest: dict, force: bool) -> bool:
    """
    ING-04: Return True (skip) if file exists, MD5 matches manifest, and not forced.
    Logs [SKIP] when returning True.
    """
    logger = get_logger()
    if force or not os.path.exists(target_path):
        return False
    cached = manifest.get(source_id, {})
    if cached.get("md5") and _md5(target_path) == cached["md5"]:
        logger.info(
            f"[INGEST][{source_id}] status: SKIP  rows: {cached.get('rows', '?')}  "
            f"(MD5 match, re-download skipped)"
        )
        return True
    # MD5 mismatch — must re-download
    logger.info(f"[INGEST][{source_id}] status: OK  (MD5 mismatch -- re-downloading)")
    return False


# ---------------------------------------------------------------------------
# Source downloaders
# ---------------------------------------------------------------------------

def download_taxi_zones_csv(manifest: dict, force: bool = False) -> tuple[str, int]:
    """ING-01 Mode 1: CSV file via HTTP."""
    logger = get_logger()
    source_id = "taxi_zones"
    target_path = os.path.join(_raw_dir(), "taxi_zone_lookup.csv")

    if _skip_if_cached(source_id, target_path, manifest, force):
        return target_path, manifest[source_id]["rows"]

    try:
        req = urllib.request.Request(TAXI_ZONE_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(target_path, "wb") as out:
            out.write(resp.read())
    except Exception as e:
        raise RuntimeError(
            f"[INGEST][{source_id}] FAIL: {TAXI_ZONE_CSV_URL} — {e}"
        ) from e

    import pandas as pd
    row_count = len(pd.read_csv(target_path))
    md5 = _md5(target_path)
    size_kb = os.path.getsize(target_path) / 1024
    manifest[source_id] = {
        "md5": md5, "rows": row_count, "path": target_path,
        "ts": datetime.now(timezone.utc).isoformat()
    }
    _save_manifest(manifest)
    logger.info(
        f"[INGEST][{source_id}] status: OK  rows: {row_count}  "
        f"size_kb: {size_kb:.2f}  md5: {md5}"
    )
    return target_path, row_count


def download_trip_parquet(month: str, manifest: dict, force: bool = False) -> tuple[str, int]:
    """ING-01 Mode 2: Parquet file via HTTP."""
    logger = get_logger()
    source_id = "yellow_trips"
    url = TRIP_PARQUET_URL_TMPL.format(month=month)
    target_path = os.path.join(_raw_dir(), f"yellow_tripdata_{month}.parquet")

    if _skip_if_cached(source_id, target_path, manifest, force):
        return target_path, manifest[source_id]["rows"]

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(target_path, "wb") as out:
            out.write(resp.read())
    except Exception as e:
        raise RuntimeError(
            f"[INGEST][{source_id}] FAIL: {url} — {e}"
        ) from e

    con = duckdb.connect()
    row_count = con.execute(f"SELECT COUNT(*) FROM '{target_path}'").fetchone()[0]
    md5 = _md5(target_path)
    size_mb = os.path.getsize(target_path) / (1024 * 1024)
    manifest[source_id] = {
        "md5": md5, "rows": row_count, "path": target_path,
        "ts": datetime.now(timezone.utc).isoformat()
    }
    _save_manifest(manifest)
    logger.info(
        f"[INGEST][{source_id}] status: OK  rows: {row_count:,}  "
        f"size_mb: {size_mb:.2f}  md5: {md5}"
    )
    return target_path, row_count


def fetch_industry_indicators_api(manifest: dict, force: bool = False) -> tuple[str, int]:
    """ING-01 Mode 3: REST API (Socrata) — raw reference, not used in metrics."""
    logger = get_logger()
    source_id = "indicators_api"
    target_path = os.path.join(_raw_dir(), "tlc_industry_indicators.json")

    if _skip_if_cached(source_id, target_path, manifest, force):
        return target_path, manifest[source_id]["rows"]

    try:
        resp = requests.get(
            NYC_OPENDATA_INDICATORS_API,
            params={"$limit": 300},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"[INGEST][{source_id}] FAIL: {NYC_OPENDATA_INDICATORS_API} — {e}"
        ) from e

    data = resp.json()
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    record_count = len(data)
    md5 = _md5(target_path)
    manifest[source_id] = {
        "md5": md5, "rows": record_count, "path": target_path,
        "ts": datetime.now(timezone.utc).isoformat()
    }
    _save_manifest(manifest)
    logger.info(
        f"[INGEST][{source_id}] status: OK  records: {record_count}  md5: {md5}"
    )
    return target_path, record_count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ingestion(month: str, force: bool = False) -> dict:
    """
    Run all 3 ingestion modes. Returns the updated manifest dict.
    Called by main.py — manifest is passed downstream to validate.py (ASSERT-01).
    """
    logger = get_logger()
    logger.info("=== STAGE 1: INGEST ===")

    manifest = load_manifest()

    download_taxi_zones_csv(manifest, force)
    download_trip_parquet(month, manifest, force)
    fetch_industry_indicators_api(manifest, force)

    logger.info(f"[INGEST] Manifest written: {_manifest_path()}")
    return manifest
