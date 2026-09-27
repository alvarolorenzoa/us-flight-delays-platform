"""Configuration read from environment variables (with sensible local defaults)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Local copy of the data lake (bronze / gold). Synced to Azure when a connection string is set.
LAKE_PATH = Path(os.getenv("LAKE_PATH", ROOT / "data" / "lake")).resolve()
DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", ROOT / "data" / "warehouse.duckdb")).resolve()
DBT_DIR = ROOT / "dbt"

# Azure Data Lake / Blob Storage (optional: the pipeline also runs 100% locally)
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_CONTAINER = os.getenv("AZURE_CONTAINER", "flights-lake")

# How many months of flights to keep in the lake (most recent published months)
MONTHS = int(os.getenv("MONTHS", "12"))

# Hub airports with coordinates (used for weather and maps) live in the dbt seed
HUBS_SEED = DBT_DIR / "seeds" / "hub_airports.csv"

# Sources
BTS_URL = ("https://transtats.bts.gov/PREZIP/"
           "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip")
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
HTTP_HEADERS = {"User-Agent": "flight-delay-platform/1.0 (portfolio project; github.com/alvarolorenzoa)"}
