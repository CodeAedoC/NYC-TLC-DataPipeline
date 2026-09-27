import duckdb
import pandas as pd
from src.validation.validate import _temporal_rules, _financial_rules, _telematics_rules, _location_rules, _attribute_rules

print("Loading data...")
con = duckdb.connect()
df = con.execute("SELECT * FROM 'data/raw/yellow_tripdata_2024-01.parquet'").df()

df['validation_flag'] = ''
print("Applying rules...")
df = _temporal_rules(df)
df = _financial_rules(df)
df = _telematics_rules(df)
df = _location_rules(df)
df = _attribute_rules(df)

print("Flag counts:")
print(df['validation_flag'].value_counts().head(20))
