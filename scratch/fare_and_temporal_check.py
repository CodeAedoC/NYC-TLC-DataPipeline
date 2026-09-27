import duckdb, sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect()
PARQUET = "data/raw/yellow_tripdata_2024-01.parquet"

print("=== FARE vs TOTAL — COMPONENT BREAKDOWN (5 clean sample trips) ===")
df = con.execute(f"""
    SELECT
        fare_amount,
        extra,
        mta_tax,
        tip_amount,
        tolls_amount,
        improvement_surcharge                            as imp_surch,
        COALESCE(congestion_surcharge, 0)                as cong_surch,
        COALESCE(Airport_fee, 0)                         as airport_fee,
        total_amount,
        ROUND(
            fare_amount + extra + mta_tax + tip_amount + tolls_amount
            + improvement_surcharge
            + COALESCE(congestion_surcharge, 0)
            + COALESCE(Airport_fee, 0), 2
        )                                                as calculated_total,
        ROUND(
            total_amount - (
                fare_amount + extra + mta_tax + tip_amount + tolls_amount
                + improvement_surcharge
                + COALESCE(congestion_surcharge, 0)
                + COALESCE(Airport_fee, 0)
            ), 2
        )                                                as discrepancy
    FROM (SELECT * FROM '{PARQUET}' WHERE fare_amount > 5 LIMIT 5)
""").df()
print(df.to_string(index=False))

print()
print("=== TEMPORAL ANOMALY FULL BREAKDOWN ===")
result = con.execute(f"""
    SELECT
        COUNT(*) FILTER (WHERE tpep_pickup_datetime < '2024-01-01')                        AS before_scope,
        COUNT(*) FILTER (WHERE tpep_pickup_datetime >= '2024-02-01')                       AS after_scope,
        COUNT(*) FILTER (WHERE tpep_dropoff_datetime <= tpep_pickup_datetime)               AS impossible_order,
        COUNT(*) FILTER (WHERE epoch(tpep_dropoff_datetime - tpep_pickup_datetime)/60.0 > 1440
                         AND tpep_dropoff_datetime > tpep_pickup_datetime)                  AS over_24hr,
        MIN(tpep_pickup_datetime) FILTER (WHERE tpep_pickup_datetime < '2024-01-01')        AS oldest_outlier,
        MAX(tpep_pickup_datetime) FILTER (WHERE tpep_pickup_datetime >= '2024-02-01')       AS latest_outlier
    FROM '{PARQUET}'
""").df()
for col in result.columns:
    print(f"  {col}: {result[col].values[0]}")
