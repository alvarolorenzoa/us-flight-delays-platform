"""Flights source: US Bureau of Transportation Statistics (BTS) - Reporting Carrier On-Time Performance.

One zip file per month with every domestic flight operated by the large US carriers
(~500-650k flights/month). We keep the columns needed downstream, normalise names to
snake_case and write them to the bronze layer as Parquet partitioned by year/month.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from ingestion import config

log = logging.getLogger(__name__)

# BTS column -> bronze column
COLUMNS = {
    "FlightDate": "flight_date",
    "Reporting_Airline": "carrier_code",
    "Flight_Number_Reporting_Airline": "flight_number",
    "Tail_Number": "tail_number",
    "Origin": "origin",
    "OriginCityName": "origin_city",
    "OriginState": "origin_state",
    "Dest": "dest",
    "DestCityName": "dest_city",
    "DestState": "dest_state",
    "CRSDepTime": "crs_dep_time",
    "DepTime": "dep_time",
    "DepDelay": "dep_delay",
    "DepDel15": "dep_del15",
    "TaxiOut": "taxi_out",
    "TaxiIn": "taxi_in",
    "CRSArrTime": "crs_arr_time",
    "ArrTime": "arr_time",
    "ArrDelay": "arr_delay",
    "ArrDel15": "arr_del15",
    "Cancelled": "cancelled",
    "CancellationCode": "cancellation_code",
    "Diverted": "diverted",
    "CRSElapsedTime": "crs_elapsed_time",
    "ActualElapsedTime": "actual_elapsed_time",
    "AirTime": "air_time",
    "Distance": "distance",
    "CarrierDelay": "carrier_delay",
    "WeatherDelay": "weather_delay",
    "NASDelay": "nas_delay",
    "SecurityDelay": "security_delay",
    "LateAircraftDelay": "late_aircraft_delay",
}
STRING_COLS = ["FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Tail_Number", "Origin",
               "OriginCityName", "OriginState", "Dest", "DestCityName", "DestState", "CancellationCode"]
DATE_PARTS = ["Year", "Month", "DayofMonth"]
HHMM_COLS = ["crs_dep_time", "dep_time", "crs_arr_time", "arr_time"]


def month_url(year: int, month: int) -> str:
    return config.BTS_URL.format(year=year, month=month)


def bronze_path(lake: Path, year: int, month: int) -> Path:
    return lake / "bronze" / "flights" / f"year={year}" / f"month={month:02d}" / "flights.parquet"


def is_published(year: int, month: int, session: requests.Session | None = None) -> bool:
    """BTS publishes each month with a ~2-3 month lag. A tiny ranged GET tells us if the file exists."""
    s = session or requests.Session()
    try:
        r = s.get(month_url(year, month), headers={**config.HTTP_HEADERS, "Range": "bytes=0-100"}, timeout=30)
        return r.status_code in (200, 206)
    except requests.RequestException:
        return False


def latest_published_month(today: dt.date | None = None, max_lookback: int = 8) -> tuple[int, int]:
    today = today or dt.date.today()
    y, m = today.year, today.month
    s = requests.Session()
    for _ in range(max_lookback):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        if is_published(y, m, s):
            return y, m
    raise RuntimeError("Could not find a published BTS month in the last %d months" % max_lookback)


def month_range(last: tuple[int, int], n: int) -> list[tuple[int, int]]:
    """The n months ending at `last` (inclusive), oldest first."""
    y, m = last
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def download_zip(year: int, month: int, source_dir: Path | None = None, retries: int = 3) -> bytes:
    """Download the monthly zip (or read it from `source_dir`, used by tests / offline runs)."""
    if source_dir is not None:
        return (source_dir / Path(month_url(year, month)).name).read_bytes()
    url = month_url(year, month)
    for attempt in range(1, retries + 1):
        try:
            log.info("Downloading BTS %d-%02d ...", year, month)
            r = requests.get(url, headers=config.HTTP_HEADERS, timeout=300)
            r.raise_for_status()
            return r.content
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed: %s", attempt, retries, exc)
            time.sleep(10 * attempt)
    raise RuntimeError(f"Could not download {url}")


def parse_zip(content: bytes) -> pd.DataFrame:
    """Read the CSV inside the zip keeping only the columns we need."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as fh:
            df = pd.read_csv(fh, usecols=list(COLUMNS) + DATE_PARTS, dtype={c: "string" for c in STRING_COLS},
                             encoding="latin-1", low_memory=False)
    # FlightDate's text format has changed over the years ("2025-01-31" vs "1/31/2025 12:00:00 AM"):
    # rebuild it from the numeric parts, which are stable.
    df["FlightDate"] = pd.to_datetime(dict(year=df["Year"], month=df["Month"], day=df["DayofMonth"])) \
        .dt.strftime("%Y-%m-%d")
    df = df[list(COLUMNS)].rename(columns=COLUMNS)  # stable column order regardless of file layout
    for col in HHMM_COLS:  # times come as hhmm numbers ("0005", "1932", "2400")
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int16")
    df["flight_number"] = df["flight_number"].str.strip()
    return df


def ingest_month(year: int, month: int, lake: Path = config.LAKE_PATH, source_dir: Path | None = None,
                 force: bool = False) -> int:
    """Idempotent: a month already in bronze is skipped unless force=True. Returns rows written."""
    target = bronze_path(lake, year, month)
    if target.exists() and not force:
        log.info("BTS %d-%02d already in bronze, skipping", year, month)
        return 0
    df = parse_zip(download_zip(year, month, source_dir))
    df["_ingested_at"] = pd.Timestamp.now(tz="UTC")
    df["_source_file"] = Path(month_url(year, month)).name
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target, index=False)
    log.info("BTS %d-%02d -> %s rows", year, month, f"{len(df):,}")
    return len(df)
