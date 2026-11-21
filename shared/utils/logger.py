import logging
import sys
import os

class CorrelationFilter(logging.Filter):
    def filter(self, record):
        from shared.utils.observability import correlation
        context = correlation()
        record.correlation = ' '.join(f'{key}={value}' for key,value in context.items() if value is not None)
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a standardized logger."""
    log = logging.getLogger(name)
    if not log.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        log.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(correlation)s | %(message)s"
        )
        handler.setFormatter(fmt)
        handler.addFilter(CorrelationFilter())
        log.addHandler(handler)
    return log
