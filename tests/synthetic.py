"""Synthetic data in the exact source formats (BTS zip + Open-Meteo JSON).

Used by the unit tests and CI so the whole pipeline (ingestion -> dbt -> marts) can be
tested offline and deterministically. The generator plants realistic patterns
(weather-driven delays, delays snowballing during the day, carrier differences).
"""
from __future__ import annotations

import calendar
import io
import zipfile

import numpy as np
import pandas as pd

HUBS = pd.read_csv(__import__("pathlib").Path(__file__).resolve().parents[1] / "dbt/seeds/hub_airports.csv")
SMALL = [("ASE", "Aspen, CO", "CO"), ("BZN", "Bozeman, MT", "MT"), ("SAV", "Savannah, GA", "GA"),
         ("PSP", "Palm Springs, CA", "CA"), ("BTV", "Burlington, VT", "VT")]
CARRIERS = {"WN": 0.05, "DL": -0.04, "AA": 0.02, "UA": 0.0, "B6": 0.07, "AS": -0.03, "NK": 0.06, "OO": 0.01}

# Full BTS header order is long; we include the used columns plus a few unused ones to test `usecols`.
EXTRA_COLS = ["Year", "Quarter", "Month", "DayofMonth", "DayOfWeek", "DOT_ID_Reporting_Airline",
              "OriginAirportID", "DestAirportID", "DepTimeBlk", "ArrTimeBlk", "Flights", "DistanceGroup"]


def _airports():
    hubs = [(r.airport_code, f"{r.city}, {r.state}", r.state) for r in HUBS.itertuples()]
    return hubs + SMALL


def weather_for(year: int, month: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed + year * 100 + month)
    days = calendar.monthrange(year, month)[1]
    hours = pd.date_range(f"{year}-{month:02d}-01", periods=days * 24, freq="h")
    rows = []
    for code in HUBS["airport_code"]:
        storm = rng.random(days * 24) < 0.06
        cold = month in (12, 1, 2) and code in {"ORD", "DEN", "MSP", "DTW", "BOS", "EWR", "JFK", "LGA", "SLC", "MDW"}
        precip = np.where(storm, rng.gamma(1.5, 2.0, days * 24), 0.0).round(1)
        snow = np.where(storm & cold, rng.gamma(1.2, 0.8, days * 24), 0.0).round(1)
        gust = (rng.normal(25, 10, days * 24) + storm * 25).clip(0).round(1)
        rows.append(pd.DataFrame({"airport_code": code, "time": hours, "precipitation": precip, "snowfall": snow,
                                  "wind_gusts_10m": gust, "temp": rng.normal(15, 8, days * 24).round(1)}))
    return pd.concat(rows, ignore_index=True)


def open_meteo_response(hubs: pd.DataFrame, year: int, month: int) -> list[dict]:
    w = weather_for(year, month)
    out = []
    for code in hubs["airport_code"]:
        g = w[w["airport_code"] == code]
        out.append({"timezone": "America/New_York", "hourly": {
            "time": g["time"].dt.strftime("%Y-%m-%dT%H:%M").tolist(),
            "temperature_2m": g["temp"].tolist(), "precipitation": g["precipitation"].tolist(),
            "snowfall": g["snowfall"].tolist(), "wind_speed_10m": (g["wind_gusts_10m"] * 0.6).round(1).tolist(),
            "wind_gusts_10m": g["wind_gusts_10m"].tolist(), "cloud_cover": [50] * len(g),
            "weather_code": [3] * len(g)}})
    return out


def bts_month(year: int, month: int, rows: int = 20000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed + year * 100 + month)
    airports = _airports()
    w = weather_for(year, month).set_index(["airport_code", "time"])
    days = calendar.monthrange(year, month)[1]
    idx_o = rng.integers(0, len(airports), rows)
    idx_d = (idx_o + rng.integers(1, len(airports), rows)) % len(airports)
    day = rng.integers(1, days + 1, rows)
    hour = rng.choice(np.arange(5, 23), rows)
    minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55], rows)
    carriers = rng.choice(list(CARRIERS), rows)
    dates = pd.to_datetime(dict(year=year, month=month, day=day))

    origin = [airports[i][0] for i in idx_o]
    key = pd.MultiIndex.from_arrays([origin, dates + pd.to_timedelta(hour, "h")])
    precip = w["precipitation"].reindex(key).fillna(0).to_numpy()
    snow = w["snowfall"].reindex(key).fillna(0).to_numpy()
    gust = w["wind_gusts_10m"].reindex(key).fillna(20).to_numpy()

    # probability of a 15+ min delay: base + hour of day + carrier + weather
    p = (0.12 + (hour - 5) * 0.008 + np.array([CARRIERS[c] for c in carriers])
         + np.minimum(precip, 10) * 0.03 + snow * 0.15 + (gust > 50) * 0.12).clip(0.02, 0.9)
    delayed = rng.random(rows) < p
    dep_delay = np.where(delayed, rng.gamma(1.6, 30, rows) + 15, rng.normal(-3, 5, rows)).round()
    p_cancel = (0.012 + snow * 0.05 + np.minimum(precip, 10) * 0.004).clip(0, 0.5)
    cancelled = rng.random(rows) < p_cancel
    diverted = (~cancelled) & (rng.random(rows) < 0.002)
    arr_delay = (dep_delay + rng.normal(-4, 8, rows)).round()
    distance = rng.integers(150, 2600, rows)
    arr_del15 = (arr_delay >= 15).astype(float)

    # delay causes only for arrivals 15+ min late; split the arrival delay across causes
    late = (arr_delay >= 15) & ~cancelled & ~diverted
    weather_share = np.clip(np.minimum(precip, 10) * 0.06 + snow * 0.3, 0, 0.8)
    split = rng.dirichlet([2, 0.3, 1.5, 0.05, 2.2], rows)
    split[:, 1] = np.maximum(split[:, 1], weather_share)
    split = split / split.sum(axis=1, keepdims=True)
    causes = np.where(late[:, None], (split * np.maximum(arr_delay, 0)[:, None]).round(), np.nan)

    crs_dep = hour * 100 + minute
    dep_time = ((hour * 60 + minute + np.nan_to_num(dep_delay)) % 1440)
    dep_time = (dep_time // 60 * 100 + dep_time % 60)
    crs_elapsed = (distance / 7.5 + 35).round()

    df = pd.DataFrame({
        "Year": year, "Quarter": (month - 1) // 3 + 1, "Month": month, "DayofMonth": day,
        "DayOfWeek": dates.dt.dayofweek + 1, "FlightDate": dates.dt.strftime("%Y-%m-%d"),
        "Reporting_Airline": carriers, "DOT_ID_Reporting_Airline": 19805,
        "Tail_Number": [f"N{n}{c}" for n, c in zip(rng.integers(100, 999, rows), carriers)],
        "Flight_Number_Reporting_Airline": rng.integers(1, 7000, rows),
        "OriginAirportID": 10000 + idx_o, "Origin": origin,
        "OriginCityName": [airports[i][1] for i in idx_o], "OriginState": [airports[i][2] for i in idx_o],
        "DestAirportID": 10000 + idx_d, "Dest": [airports[i][0] for i in idx_d],
        "DestCityName": [airports[i][1] for i in idx_d], "DestState": [airports[i][2] for i in idx_d],
        "CRSDepTime": [f"{v:04d}" for v in crs_dep],
        "DepTime": np.where(cancelled, np.nan, dep_time),
        "DepDelay": np.where(cancelled, np.nan, dep_delay),
        "DepDel15": np.where(cancelled, np.nan, (dep_delay >= 15).astype(float)),
        "DepTimeBlk": [f"{h:02d}00-{h:02d}59" for h in hour],
        "TaxiOut": np.where(cancelled, np.nan, rng.gamma(4, 4, rows).round()),
        "TaxiIn": np.where(cancelled | diverted, np.nan, rng.gamma(3, 2.5, rows).round()),
        "CRSArrTime": [f"{((h * 60 + m + int(e)) % 1440) // 60 * 100 + ((h * 60 + m + int(e)) % 60):04d}"
                       for h, m, e in zip(hour, minute, crs_elapsed)],
        "ArrTime": np.where(cancelled | diverted, np.nan, 1200.0),
        "ArrDelay": np.where(cancelled | diverted, np.nan, arr_delay),
        "ArrDel15": np.where(cancelled | diverted, np.nan, arr_del15),
        "ArrTimeBlk": "1200-1259",
        "Cancelled": cancelled.astype(float),
        "CancellationCode": np.where(cancelled, np.where(snow + precip > 0, "B", rng.choice(["A", "C"], rows)), ""),
        "Diverted": diverted.astype(float),
        "CRSElapsedTime": crs_elapsed,
        "ActualElapsedTime": np.where(cancelled | diverted, np.nan, crs_elapsed + (arr_delay - dep_delay)),
        "AirTime": np.where(cancelled | diverted, np.nan, crs_elapsed - 25),
        "Flights": 1.0, "Distance": distance.astype(float), "DistanceGroup": distance // 250 + 1,
        "CarrierDelay": causes[:, 0], "WeatherDelay": causes[:, 1], "NASDelay": causes[:, 2],
        "SecurityDelay": causes[:, 3], "LateAircraftDelay": causes[:, 4],
    })
    return df


def bts_zip_bytes(year: int, month: int, rows: int = 20000) -> bytes:
    csv = bts_month(year, month, rows).to_csv(index=False)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_{year}_{month}.csv", csv)
        zf.writestr("readme.html", "<html>BTS</html>")
    return buf.getvalue()
