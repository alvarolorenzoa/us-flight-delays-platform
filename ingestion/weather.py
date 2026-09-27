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


def _get_with_retries(params: dict, retries: int = 5) -> list[dict]:
    """GET with exponential back-off on timeouts, connection errors, 429 and 5xx."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(config.OPEN_METEO_URL, params=params, headers=config.HTTP_HEADERS, timeout=(10, 60))
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else [data]
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status < 500 and status != 429:
                raise  # 4xx other than rate limiting = our bug, do not retry
            wait = min(15 * 2 ** (attempt - 1), 120)
            log.warning("Open-Meteo attempt %d/%d failed (%s), retrying in %ds", attempt, retries, exc, wait)
            time.sleep(wait)
    raise RuntimeError("Open-Meteo: too many retries")


def fetch_open_meteo(hubs: pd.DataFrame, start: str, end: str, batch_size: int = 10) -> list[dict]:
    """Hourly weather for all hubs, requested in small batches of coordinates (large multi-location
    requests are slow and can time out). Returns one response per hub, in the same order."""
    out: list[dict] = []
    for i in range(0, len(hubs), batch_size):
        batch = hubs.iloc[i:i + batch_size]
        params = {
            "latitude": ",".join(f"{v:.4f}" for v in batch["latitude"]),
            "longitude": ",".join(f"{v:.4f}" for v in batch["longitude"]),
            "start_date": start, "end_date": end,
            "hourly": ",".join(HOURLY_VARS),
            "timezone": "auto", "wind_speed_unit": "kmh",
        }
        out.extend(_get_with_retries(params))
        if i + batch_size < len(hubs):
            time.sleep(5)  # be gentle with the free API
    return out


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
