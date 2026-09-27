"""Sync the local lake folder with Azure Blob Storage / ADLS Gen2.

Layout (same locally and in the cloud container):
    bronze/flights/year=YYYY/month=MM/flights.parquet   raw monthly extracts
    bronze/weather/year=YYYY/month=MM/weather.parquet
    gold/<mart>.parquet                                  analytics-ready tables built by dbt
"""
from __future__ import annotations

import logging
from pathlib import Path

from ingestion import config

log = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(config.AZURE_CONNECTION_STRING)


def _container():
    from azure.storage.blob import ContainerClient  # imported lazily: optional dependency locally
    c = ContainerClient.from_connection_string(config.AZURE_CONNECTION_STRING, config.AZURE_CONTAINER)
    if not c.exists():
        c.create_container()
        log.info("Created container %s", config.AZURE_CONTAINER)
    return c


def download(prefix: str, lake: Path = config.LAKE_PATH) -> int:
    """Download blobs under `prefix` that are missing locally (e.g. bronze history on a fresh CI runner)."""
    if not enabled():
        return 0
    c, n = _container(), 0
    for blob in c.list_blobs(name_starts_with=prefix):
        local = lake / blob.name
        if local.exists() and local.stat().st_size == blob.size:
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        with open(local, "wb") as fh:
            fh.write(c.download_blob(blob.name).readall())
        n += 1
    log.info("Azure -> local: %d files from %s/", n, prefix)
    return n


def upload(prefix: str, lake: Path = config.LAKE_PATH) -> int:
    """Upload local files under `prefix` that are new or changed."""
    if not enabled():
        return 0
    c, n = _container(), 0
    remote = {b.name: b.size for b in c.list_blobs(name_starts_with=prefix)}
    for path in sorted((lake / prefix).rglob("*.parquet")):
        name = path.relative_to(lake).as_posix()
        if remote.get(name) == path.stat().st_size and prefix != "gold":
            continue  # bronze files are immutable; gold is always refreshed
        with open(path, "rb") as fh:
            c.upload_blob(name, fh, overwrite=True)
        n += 1
    log.info("local -> Azure: %d files to %s/", n, prefix)
    return n
