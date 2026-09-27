import os
import sys
import duckdb
import pandas as pd
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_TRIP_PARQUET = os.path.join(PROJECT_ROOT, "data", "raw", "yellow_tripdata_2024-01.parquet")
RAW_ZONE_CSV = os.path.join(PROJECT_ROOT, "data", "raw", "taxi_zone_lookup.csv")
RAW_INDICATORS_JSON = os.path.join(PROJECT_ROOT, "data", "raw", "tlc_industry_indicators.json")

def analyze_raw_data():
    con = duckdb.connect()
    
    print("=" * 80)
    print("FDE BUSINESS DATA PROFILING & PROBLEM IDENTIFICATION ANALYSIS")
    print("=" * 80)
    
    # 1. Total Volume & Grain
    total_trips = con.execute(f"SELECT COUNT(*) FROM '{RAW_TRIP_PARQUET}'").fetchone()[0]
    print(f"\n[1. RAW DATA VOLUME & GRAIN]")
    print(f"  - Total Raw Trip Records: {total_trips:,}")
    
    # 2. Date Range Anomalies
    date_anomalies = con.execute(f"""
        SELECT 
            COUNT(*) FILTER (WHERE tpep_pickup_datetime < '2024-01-01 00:00:00') as before_jan_2024,
            COUNT(*) FILTER (WHERE tpep_pickup_datetime >= '2024-02-01 00:00:00') as after_jan_2024,
            COUNT(*) FILTER (WHERE tpep_dropoff_datetime < tpep_pickup_datetime) as dropoff_before_pickup,
            MIN(tpep_pickup_datetime) as min_pickup,
            MAX(tpep_pickup_datetime) as max_pickup
        FROM '{RAW_TRIP_PARQUET}'
    """).df()
    print(f"\n[2. TIMESTAMP & DATE RANGE ANOMALIES]")
    print(f"  - Min Pickup Date: {date_anomalies['min_pickup'].values[0]}")
    print(f"  - Max Pickup Date: {date_anomalies['max_pickup'].values[0]}")
    print(f"  - Trips BEFORE Jan 1, 2024 (Out of scope): {date_anomalies['before_jan_2024'].values[0]:,}")
    print(f"  - Trips AFTER Jan 31, 2024 (Out of scope): {date_anomalies['after_jan_2024'].values[0]:,}")
    print(f"  - Impossible Trips (Dropoff < Pickup): {date_anomalies['dropoff_before_pickup'].values[0]:,}")

    # 3. Trip Duration & Speed Anomalies
    duration_speed = con.execute(f"""
        WITH duration_calc AS (
            SELECT 
                tpep_pickup_datetime,
                tpep_dropoff_datetime,
                trip_distance,
                epoch(tpep_dropoff_datetime - tpep_pickup_datetime) / 60.0 as duration_minutes,
                (trip_distance / (epoch(tpep_dropoff_datetime - tpep_pickup_datetime) / 3600.0)) as avg_speed_mph
            FROM '{RAW_TRIP_PARQUET}'
            WHERE tpep_dropoff_datetime > tpep_pickup_datetime
        )
        SELECT
            COUNT(*) FILTER (WHERE duration_minutes = 0) as zero_duration,
            COUNT(*) FILTER (WHERE duration_minutes < 1 AND trip_distance > 5) as high_speed_anomaly,
            COUNT(*) FILTER (WHERE duration_minutes > 1440) as over_24hr_trips,
            COUNT(*) FILTER (WHERE avg_speed_mph > 100) as speed_over_100mph,
            COUNT(*) FILTER (WHERE trip_distance = 0) as zero_distance_trips,
            COUNT(*) FILTER (WHERE trip_distance > 300) as extreme_distance_trips
        FROM duration_calc
    """).df()
    print(f"\n[3. TRIP DURATION & SPEED ANOMALIES]")
    print(f"  - Zero Duration Trips (0 mins): {duration_speed['zero_duration'].values[0]:,}")
    print(f"  - Extremely Long Trips (>24 Hours): {duration_speed['over_24hr_trips'].values[0]:,}")
    print(f"  - Physically Impossible Speeds (>100 mph): {duration_speed['speed_over_100mph'].values[0]:,}")
    print(f"  - Zero Distance Trips (0 miles): {duration_speed['zero_distance_trips'].values[0]:,}")
    print(f"  - Extreme Distance Trips (>300 miles): {duration_speed['extreme_distance_trips'].values[0]:,}")

    # 4. Financial & Fare Integrity Anomalies
    financial_anomalies = con.execute(f"""
        WITH fare_check AS (
            SELECT 
                fare_amount,
                extra,
                mta_tax,
                tip_amount,
                tolls_amount,
                improvement_surcharge,
                congestion_surcharge,
                Airport_fee,
                total_amount,
                (fare_amount + extra + mta_tax + tip_amount + tolls_amount + improvement_surcharge + COALESCE(congestion_surcharge, 0) + COALESCE(Airport_fee, 0)) as calculated_total,
                payment_type,
                trip_distance
            FROM '{RAW_TRIP_PARQUET}'
        )
        SELECT
            COUNT(*) FILTER (WHERE fare_amount < 0) as negative_fare,
            COUNT(*) FILTER (WHERE total_amount < 0) as negative_total,
            COUNT(*) FILTER (WHERE fare_amount = 0 AND trip_distance > 2) as free_long_trips,
            COUNT(*) FILTER (WHERE abs(total_amount - calculated_total) > 0.05) as math_discrepancies,
            COUNT(*) FILTER (WHERE payment_type NOT IN (1, 2, 3, 4)) as invalid_payment_type,
            COUNT(*) FILTER (WHERE payment_type = 2 AND tip_amount > 0) as cash_tip_recorded
        FROM fare_check
    """).df()
    print(f"\n[4. FINANCIAL & FARE INTEGRITY ANOMALIES]")
    print(f"  - Negative Fare Amounts (< $0): {financial_anomalies['negative_fare'].values[0]:,}")
    print(f"  - Negative Total Amounts (< $0): {financial_anomalies['negative_total'].values[0]:,}")
    print(f"  - Free Long Trips (Fare = $0, Distance > 2 miles): {financial_anomalies['free_long_trips'].values[0]:,}")
    print(f"  - Total Amount Math Discrepancies (> $0.05 mismatch): {financial_anomalies['math_discrepancies'].values[0]:,}")
    print(f"  - Invalid/Unknown Payment Type Codes: {financial_anomalies['invalid_payment_type'].values[0]:,}")
    print(f"  - Cash Tips Recorded (Payment Type = Cash): {financial_anomalies['cash_tip_recorded'].values[0]:,}")

    # 5. Spatial & Location ID Mapping Anomalies
    location_anomalies = con.execute(f"""
        WITH zones AS (SELECT LocationID FROM '{RAW_ZONE_CSV}')
        SELECT
            COUNT(*) FILTER (WHERE PULocationID NOT IN (SELECT LocationID FROM zones)) as invalid_pu_id,
            COUNT(*) FILTER (WHERE DOLocationID NOT IN (SELECT LocationID FROM zones)) as invalid_do_id,
            COUNT(*) FILTER (WHERE PULocationID IN (264, 265)) as unknown_pu_zone,
            COUNT(*) FILTER (WHERE DOLocationID IN (264, 265)) as unknown_do_zone,
            COUNT(*) FILTER (WHERE PULocationID = DOLocationID) as same_pickup_dropoff_zone
        FROM '{RAW_TRIP_PARQUET}'
    """).df()
    print(f"\n[5. SPATIAL & ZONE MAPPING ANOMALIES]")
    print(f"  - Invalid PU Location IDs (not in zone table): {location_anomalies['invalid_pu_id'].values[0]:,}")
    print(f"  - Invalid DO Location IDs (not in zone table): {location_anomalies['invalid_do_id'].values[0]:,}")
    print(f"  - Unknown PU Location (ID 264/265 = N/A / Unknown): {location_anomalies['unknown_pu_zone'].values[0]:,}")
    print(f"  - Unknown DO Location (ID 264/265 = N/A / Unknown): {location_anomalies['unknown_do_zone'].values[0]:,}")
    print(f"  - Same Pickup & Dropoff Zone: {location_anomalies['same_pickup_dropoff_zone'].values[0]:,}")

    # 6. Null & Missing Value Profiling
    null_counts = con.execute(f"""
        SELECT 
            COUNT(*) FILTER (WHERE passenger_count IS NULL) as null_passenger_count,
            COUNT(*) FILTER (WHERE RatecodeID IS NULL) as null_ratecode,
            COUNT(*) FILTER (WHERE store_and_fwd_flag IS NULL) as null_store_fwd,
            COUNT(*) FILTER (WHERE congestion_surcharge IS NULL) as null_congestion,
            COUNT(*) FILTER (WHERE Airport_fee IS NULL) as null_airport_fee
        FROM '{RAW_TRIP_PARQUET}'
    """).df()
    print(f"\n[6. MISSING & NULL VALUE PROFILING]")
    print(f"  - Null Passenger Counts: {null_counts['null_passenger_count'].values[0]:,} ({null_counts['null_passenger_count'].values[0]/total_trips*100:.2f}%)")
    print(f"  - Null RatecodeIDs: {null_counts['null_ratecode'].values[0]:,} ({null_counts['null_ratecode'].values[0]/total_trips*100:.2f}%)")
    print(f"  - Null Store & Fwd Flag: {null_counts['null_store_fwd'].values[0]:,} ({null_counts['null_store_fwd'].values[0]/total_trips*100:.2f}%)")
    print(f"  - Null Congestion Surcharge: {null_counts['null_congestion'].values[0]:,} ({null_counts['null_congestion'].values[0]/total_trips*100:.2f}%)")
    print(f"  - Null Airport Fee: {null_counts['null_airport_fee'].values[0]:,} ({null_counts['null_airport_fee'].values[0]/total_trips*100:.2f}%)")

    # 7. Summary Impact Metrics Calculation
    print("\n" + "=" * 80)
    print("SUMMARY OF BUSINESS DATA ISSUES")
    print("=" * 80)
    
    clean_trips = con.execute(f"""
        SELECT COUNT(*) FROM '{RAW_TRIP_PARQUET}'
        WHERE tpep_pickup_datetime >= '2024-01-01' 
          AND tpep_pickup_datetime < '2024-02-01'
          AND tpep_dropoff_datetime > tpep_pickup_datetime
          AND fare_amount >= 0
          AND total_amount >= 0
          AND trip_distance > 0
          AND PULocationID NOT IN (264, 265)
          AND DOLocationID NOT IN (264, 265)
    """).fetchone()[0]
    
    invalid_trips = total_trips - clean_trips
    print(f"  Total Raw Records:           {total_trips:,}")
    print(f"  Clean Operational Records:   {clean_trips:,} ({clean_trips/total_trips*100:.2f}%)")
    print(f"  Contaminated/Invalid Records: {invalid_trips:,} ({invalid_trips/total_trips*100:.2f}%)")
    print("=" * 80)

if __name__ == "__main__":
    analyze_raw_data()
