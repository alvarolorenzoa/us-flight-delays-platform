"""Unit tests for the ingestion layer (offline: synthetic files in the real source formats)."""
import datetime as dt

import pandas as pd
import pytest

from ingestion import bts, lake, weather
import synthetic


@pytest.fixture(scope="module")
def zip_bytes():
    return synthetic.bts_zip_bytes(2025, 3, rows=500)


def test_parse_zip_keeps_and_renames_columns(zip_bytes):
    df = bts.parse_zip(zip_bytes)
    assert list(df.columns) == list(bts.COLUMNS.values())
    assert len(df) == 500
    assert "Year" not in df.columns  # unused BTS columns are dropped


def test_hhmm_times_are_integers(zip_bytes):
    df = bts.parse_zip(zip_bytes)
    assert str(df["crs_dep_time"].dtype) == "Int16"
    assert df["crs_dep_time"].between(0, 2400).all()


def test_cancelled_flights_have_no_arrival_delay(zip_bytes):
    df = bts.parse_zip(zip_bytes)
    assert df.loc[df["cancelled"] == 1, "arr_delay"].isna().all()


def test_month_range_crosses_year_boundary():
    assert bts.month_range((2025, 2), 4) == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]


def test_month_url_format():
    assert bts.month_url(2025, 1).endswith("1987_present_2025_1.zip")


def test_ingest_month_is_idempotent(tmp_path, zip_bytes):
    src = tmp_path / "src"
    src.mkdir()
    (src / "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_3.zip").write_bytes(zip_bytes)
    lake_dir = tmp_path / "lake"
    assert bts.ingest_month(2025, 3, lake=lake_dir, source_dir=src) == 500
    assert bts.ingest_month(2025, 3, lake=lake_dir, source_dir=src) == 0  # already there -> skipped
    written = pd.read_parquet(bts.bronze_path(lake_dir, 2025, 3))
    assert {"_ingested_at", "_source_file"} <= set(written.columns)


def test_weather_flattening_one_row_per_hub_and_hour():
    hubs = weather.load_hubs().head(3)
    frame = weather.to_frame(synthetic.open_meteo_response(hubs, 2025, 2), hubs)
    assert frame["airport_code"].nunique() == 3
    assert len(frame) == 3 * 28 * 24
    assert set(weather.HOURLY_VARS) <= set(frame.columns)


def test_weather_ingest_uses_injected_fetcher(tmp_path):
    hubs = weather.load_hubs().head(2)
    calls = []

    def fake_fetch(h, start, end):
        calls.append((start, end))
        return synthetic.open_meteo_response(h, 2024, 2)

    weather.ingest_month(2024, 2, lake=tmp_path, hubs=hubs, fetch=fake_fetch)
    assert calls == [("2024-02-01", "2024-02-29")]  # leap year handled


def test_hubs_seed_has_valid_coordinates():
    hubs = weather.load_hubs()
    assert hubs["airport_code"].is_unique and len(hubs) == 30
    assert hubs["latitude"].between(18, 72).all() and hubs["longitude"].between(-170, -60).all()


def test_lake_sync_is_noop_without_azure(monkeypatch, tmp_path):
    monkeypatch.setattr("ingestion.config.AZURE_CONNECTION_STRING", "")
    assert lake.upload("bronze", lake=tmp_path) == 0
    assert lake.download("bronze", lake=tmp_path) == 0


def test_latest_published_month_walks_back(monkeypatch):
    published = {(2025, 6)}
    monkeypatch.setattr(bts, "is_published", lambda y, m, s=None: (y, m) in published)
    assert bts.latest_published_month(today=dt.date(2025, 9, 15)) == (2025, 6)


def test_open_meteo_is_requested_in_batches(monkeypatch):
    hubs = weather.load_hubs()  # 30 hubs
    calls = []

    def fake_get(params, retries=5):
        n = len(params["latitude"].split(","))
        calls.append(n)
        return [{"hourly": {}}] * n

    monkeypatch.setattr(weather, "_get_with_retries", fake_get)
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)
    out = weather.fetch_open_meteo(hubs, "2025-01-01", "2025-01-31")
    assert calls == [10, 10, 10] and len(out) == 30


def test_open_meteo_retries_on_timeout(monkeypatch):
    import requests
    attempts = {"n": 0}

    class Ok:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"hourly": {}}

    def flaky_get(*a, **k):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise requests.Timeout("slow")
        return Ok()

    monkeypatch.setattr(weather.requests, "get", flaky_get)
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)
    assert weather._get_with_retries({}) == [{"hourly": {}}]
    assert attempts["n"] == 3
