"""End-to-end pipeline: Azure -> ingest new months -> dbt build -> Azure.

    python -m ingestion.pipeline                 # last MONTHS published months (default 12)
    python -m ingestion.pipeline --months 3      # smaller run
    python -m ingestion.pipeline --skip-dbt      # ingestion only
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time

from ingestion import bts, config, lake, weather

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("pipeline")
logging.getLogger("azure").setLevel(logging.WARNING)  # the Azure SDK logs every HTTP request at INFO


def run_dbt() -> None:
    env = {**os.environ, "LAKE_PATH": str(config.LAKE_PATH), "DUCKDB_PATH": str(config.DUCKDB_PATH)}
    (config.LAKE_PATH / "gold").mkdir(parents=True, exist_ok=True)
    config.DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    for cmd in (["dbt", "seed"], ["dbt", "build"]):
        log.info("Running: %s", " ".join(cmd))
        subprocess.run(cmd + ["--project-dir", str(config.DBT_DIR), "--profiles-dir", str(config.DBT_DIR)],
                       env=env, check=True)


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=config.MONTHS)
    p.add_argument("--skip-dbt", action="store_true")
    args = p.parse_args(argv)
    t0 = time.perf_counter()

    lake.download("bronze")                                    # 1. restore history from the cloud
    last = bts.latest_published_month()                        # 2. find what BTS has published
    months = bts.month_range(last, args.months)
    log.info("Target window: %d-%02d .. %d-%02d", *months[0], *months[-1])

    new_rows = 0
    for y, m in months:                                        # 3. incremental ingestion
        new_rows += bts.ingest_month(y, m)
        try:
            if weather.ingest_month(y, m):
                time.sleep(20)  # stay well under Open-Meteo's per-minute limit
        except Exception as exc:  # weather is an enrichment: never block the flights pipeline
            log.warning("Weather %d-%02d skipped (%s); it will be retried on the next run", y, m, exc)
    log.info("New flight rows ingested: %s", f"{new_rows:,}")

    lake.upload("bronze")                                      # 4. persist raw data
    if not args.skip_dbt:
        run_dbt()                                              # 5. transform + test
        lake.upload("gold")                                    # 6. publish analytics tables
    log.info("Pipeline finished in %.0f s", time.perf_counter() - t0)


if __name__ == "__main__":
    sys.exit(main())
