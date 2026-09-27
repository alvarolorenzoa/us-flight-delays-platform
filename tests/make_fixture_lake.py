"""Build a small offline lake from synthetic source files, through the real ingestion code.

    python tests/make_fixture_lake.py --lake data/fixture_lake --rows 3000 --months 3
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingestion import bts, weather  # noqa: E402
import synthetic  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lake", default="data/fixture_lake")
    p.add_argument("--rows", type=int, default=3000)
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--last", default="2025-06", help="last month YYYY-MM")
    a = p.parse_args()
    lake = Path(a.lake).resolve()
    y, m = map(int, a.last.split("-"))
    months = bts.month_range((y, m), a.months)
    hubs = weather.load_hubs()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp)
        for yy, mm in months:
            (src / Path(bts.month_url(yy, mm)).name).write_bytes(synthetic.bts_zip_bytes(yy, mm, a.rows))
            bts.ingest_month(yy, mm, lake=lake, source_dir=src, force=True)
            weather.ingest_month(yy, mm, lake=lake, hubs=hubs, force=True,
                                 fetch=lambda h, s, e, yy=yy, mm=mm: synthetic.open_meteo_response(h, yy, mm))
    print(f"Fixture lake ready at {lake}")


if __name__ == "__main__":
    main()
