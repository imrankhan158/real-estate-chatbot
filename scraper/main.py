"""
Scraper entry point – runs both DarGlobal and Wasalt scrapers,
writes results to /app/data/*.json shared volume.
"""

import json
import logging
import os
import sys
from pathlib import Path

import darglobal
import wasalt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scraper.main")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
MAX_PAGES = int(os.environ.get("SCRAPE_MAX_PAGES", "5"))


def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── DarGlobal ──────────────────────────────────────────────
    dg_output = DATA_DIR / "darglobal.json"
    if dg_output.exists() and dg_output.stat().st_size > 100:
        logger.info(f"DarGlobal: cached file found at {dg_output}, skipping scrape")
        with open(dg_output) as f:
            dg_props = json.load(f)
    else:
        logger.info("DarGlobal: starting scrape...")
        try:
            dg_props = darglobal.scrape(max_pages=MAX_PAGES)
        except Exception as e:
            logger.error(f"DarGlobal scrape failed: {e}")
            dg_props = darglobal._sample_darglobal_data()

        with open(dg_output, "w", encoding="utf-8") as f:
            json.dump(dg_props, f, ensure_ascii=False, indent=2)
        logger.info(f"DarGlobal: saved {len(dg_props)} records to {dg_output}")

    # ── Wasalt ────────────────────────────────────────────────
    ws_output = DATA_DIR / "wasalt.json"
    if ws_output.exists() and ws_output.stat().st_size > 100:
        logger.info(f"Wasalt: cached file found at {ws_output}, skipping scrape")
        with open(ws_output) as f:
            ws_props = json.load(f)
    else:
        logger.info("Wasalt: starting scrape...")
        try:
            ws_props = wasalt.scrape(max_pages=MAX_PAGES)
        except Exception as e:
            logger.error(f"Wasalt scrape failed: {e}")
            ws_props = wasalt._sample_wasalt_data()

        with open(ws_output, "w", encoding="utf-8") as f:
            json.dump(ws_props, f, ensure_ascii=False, indent=2)
        logger.info(f"Wasalt: saved {len(ws_props)} records to {ws_output}")

    logger.info(
        f"Scraping complete. "
        f"DarGlobal: {len(dg_props)} | Wasalt: {len(ws_props)} | "
        f"Total: {len(dg_props) + len(ws_props)}"
    )


if __name__ == "__main__":
    run()
