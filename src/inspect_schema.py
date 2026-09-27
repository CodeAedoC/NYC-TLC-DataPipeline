import duckdb
import pandas as pd

con = duckdb.connect()
print("=== YELLOW TRIP DATA SCHEMA ===")
for r in con.execute("DESCRIBE SELECT * FROM 'data/raw/yellow_tripdata_2024-01.parquet'").fetchall():
    print(f"  {r[0]:<25} : {r[1]}")

print("\n=== TAXI ZONE LOOKUP SCHEMA ===")
df_zone = pd.read_csv("data/raw/taxi_zone_lookup.csv")
print(df_zone.info())

print("\n=== SAMPLE TRIP RECORD ===")
print(con.execute("SELECT * FROM 'data/raw/yellow_tripdata_2024-01.parquet' LIMIT 2").df())
