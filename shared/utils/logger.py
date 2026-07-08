import logging
import sys
import os


def get_logger(name: str) -> logging.Logger:
    """Return a standardized logger."""
    log = logging.getLogger(name)
    if not log.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        log.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        handler.setFormatter(fmt)
        log.addHandler(handler)
    return log
