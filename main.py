"""
main.py
Entry point for the NYC TLC Operational Data Pipeline.
Wires all 5 stages together with CLI args per tech_requirements.md §6.
"""
import argparse
import sys
import time

from src.utils.logger import setup_logger, get_logger
from src.ingestion.download_data import run_ingestion
from src.validation.validate import run_validation
from src.modeling.transform import run_transform
from src.modeling.metrics import run_metrics
from src.output.report import run_output

# Ensure Windows cp1252 doesn't crash on print characters (per tech_requirements.md §2)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="NYC TLC Operational Data Pipeline")
    parser.add_argument("--month", required=True, help="Month to process, e.g. 2024-01")
    parser.add_argument("--force-ingest", action="store_true", help="Force re-download of all source files")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"], help="Set logging verbosity")
    args = parser.parse_args()

    # 0. Setup logging
    setup_logger(args.log_level)
    logger = get_logger()
    
    start_time = time.time()
    logger.info(f"=== NYC TLC Pipeline START — month: {args.month} ===")

    try:
        # ① EXTRACT
        manifest = run_ingestion(month=args.month, force=args.force_ingest)

        # ② VALIDATE
        parquet_path = manifest.get("yellow_trips", {}).get("path", f"data/raw/yellow_tripdata_{args.month}.parquet")
        zone_csv_path = manifest.get("taxi_zones", {}).get("path", "data/raw/taxi_zone_lookup.csv")
        
        validated_df = run_validation(
            parquet_path=parquet_path,
            zone_csv_path=zone_csv_path,
            manifest=manifest
        )

        # ③ CLEAN + ④ TRANSFORM
        datasets = run_transform(
            validated_df=validated_df,
            zone_csv_path=zone_csv_path
        )

        # ⑤ SAVE (metrics + output)
        raw_total = manifest.get("yellow_trips", {}).get("rows", len(validated_df))
        metrics = run_metrics(
            clean=datasets["clean"],
            raw_total=raw_total
        )
        
        run_output(
            datasets=datasets,
            metrics=metrics,
            month=args.month
        )

        duration = time.time() - start_time
        logger.info(f"=== NYC TLC Pipeline COMPLETE — month: {args.month} (Duration: {duration:.1f}s) ===")

    except AssertionError as ae:
        logger.error(f"PIPELINE HALTED BY ASSERTION: {ae}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"PIPELINE FAILED: {e}", exc_info=(args.log_level == "DEBUG"))
        sys.exit(1)


if __name__ == "__main__":
    main()
