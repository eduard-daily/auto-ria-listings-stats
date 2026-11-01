import logging
from logging.handlers import RotatingFileHandler

from ria_stats.db import DB_PATH

LOGS_DIR = DB_PATH.parents[1] / "logs"
LOG_FILE = LOGS_DIR / "ria_stats.log"


def setup_logging() -> None:
    """Log to the console (docker logs) and to logs/ria_stats.log, rotated at 5 MB, 5 files kept."""
    LOGS_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
        ],
    )
