# 🗺️ Source Map & Business Grain Documentation (Class 4)

## 1. Business Question to Source System Mapping

| Business Question | Required Information | Source System | Source Data Format / File | Data Grain | Source Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **How much revenue is generated per trip after accounting for fees & tips?** | Pickup/dropoff timestamps, fare breakdown (base fare, extra, tip, tolls, surcharges) | Yellow Taxi Meter & Payment System (TPEP) | `yellow_tripdata_2024-01.parquet` | Individual completed trip transaction | Technology Provider (VTS / CMT) |
| **Which NYC boroughs and zones experience the highest trip demand & bottlenecks?** | Pickup Location ID (`PULocationID`), Dropoff Location ID (`DOLocationID`), Borough, Zone name | Taxi Zone Lookup System | `taxi_zone_lookup.csv` | Spatial Taxi Zone entity | NYC TLC GIS / Planning Dept |
| **How does current fleet performance compare against historical monthly benchmarks?** | Monthly average daily trips, active drivers, active vehicles, total revenue per day | NYC OpenData API (Socrata Portal) | `tlc_industry_indicators.json` (via REST API endpoint `v6kb-cqej`) | Monthly aggregated industry summary | NYC OpenData / TLC Analytics |

---

## 2. Source System Overview & Ingestion Modes

```
+-------------------------------------------------------+
|                 RAW DATA SOURCES                      |
+-------------------------------------------------------+
                           |
       +-------------------+-------------------+
       |                   |                   |
[Source 1: Parquet File] [Source 2: CSV File]  [Source 3: REST API]
 Yellow Taxi Trip Data   Taxi Zone Lookup Map  TLC Industry Indicators
 (2.96M Trip Records)    (265 Zone Entities)   (300 Monthly Records)
       |                   |                   |
       +-------------------+-------------------+
                           |
                           v
              +--------------------------+
              |     data/raw/ Storage    |
              | (Raw Input Immutability) |
              +--------------------------+
```

---

## 3. Data Grain & Identified Gaps

### Data Grain Definition:
* **Trip Records:** 1 row = 1 recorded taxi ride event (pickup to dropoff).
* **Zone Lookup:** 1 row = 1 unique TLC Taxi LocationID (IDs 1–265).
* **Industry Indicators:** 1 row = 1 month of industry-wide aggregate metrics (2010–Present).

### Critical Data Gaps Identified:
1. **Driver & Vehicle Identifiers Omitted:** Raw public TLC trip records omit specific `DriverID` and `MedallionID` for privacy reasons. Driver hourly earnings must be modeled using continuous trip operational windows.
2. **Missing Component Fees in Legacy Records:** 4.73% of raw trip records (140,162 rows) have `NULL` values for `congestion_surcharge`, `Airport_fee`, and `RatecodeID`.
3. **Location Unknown Markers:** LocationIDs `264` (NV) and `265` (Unknown) lack specific borough bounding coordinates, requiring fallback spatial grouping.
