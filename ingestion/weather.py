"""Weather source: Open-Meteo historical weather API (ERA5 reanalysis, free, no API key).

Hourly observations for every hub airport, in the airport's local time so they can be
joined to the scheduled departure hour of each flight (BTS times are local too).
"""
from __future__ import annotations

import calendar
import logging
import time
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from ingestion import config

log = logging.getLogger(__name__)

HOURLY_VARS = ["temperature_2m", "precipitation", "snowfall", "wind_speed_10m", "wind_gusts_10m",
               "cloud_cover", "weather_code"]


def load_hubs(path: Path = config.HUBS_SEED) -> pd.DataFrame:
    return pd.read_csv(path)


def bronze_path(lake: Path, year: int, month: int) -> Path:
    return lake / "bronze" / "weather" / f"year={year}" / f"month={month:02d}" / "weather.parquet"


def fetch_open_meteo(hubs: pd.DataFrame, start: str, end: str, retries: int = 4) -> list[dict]:
    """One request for all hubs (Open-Meteo accepts comma-separated coordinates)."""
    params = {
        "latitude": ",".join(f"{v:.4f}" for v in hubs["latitude"]),
        "longitude": ",".join(f"{v:.4f}" for v in hubs["longitude"]),
        "start_date": start, "end_date": end,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "auto", "wind_speed_unit": "kmh",
    }
    for attempt in range(1, retries + 1):
        r = requests.get(config.OPEN_METEO_URL, params=params, headers=config.HTTP_HEADERS, timeout=120)
        if r.status_code == 429:  # rate limited: back off and retry
            wait = 30 * attempt
            log.warning("Open-Meteo rate limit, waiting %ds", wait)
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]
    raise RuntimeError("Open-Meteo: too many retries")


def to_frame(responses: list[dict], hubs: pd.DataFrame) -> pd.DataFrame:
    """Flatten the API response (one element per hub, same order as requested)."""
    frames = []
    for code, resp in zip(hubs["airport_code"], responses):
        h = resp["hourly"]
        f = pd.DataFrame({v: h[v] for v in HOURLY_VARS})
        f.insert(0, "weather_time", pd.to_datetime(h["time"]))
        f.insert(0, "airport_code", code)
        f["timezone"] = resp.get("timezone")
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def ingest_month(year: int, month: int, lake: Path = config.LAKE_PATH, hubs: pd.DataFrame | None = None,
                 fetch: Callable = fetch_open_meteo, force: bool = False) -> int:
    target = bronze_path(lake, year, month)
    if target.exists() and not force:
        log.info("Weather %d-%02d already in bronze, skipping", year, month)
        return 0
    hubs = load_hubs() if hubs is None else hubs
    last_day = calendar.monthrange(year, month)[1]
    responses = fetch(hubs, f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}")
    df = to_frame(responses, hubs)
    df["_ingested_at"] = pd.Timestamp.now(tz="UTC")
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target, index=False)
    log.info("Weather %d-%02d -> %s hourly rows (%d hubs)", year, month, f"{len(df):,}", len(hubs))
    return len(df)
