import logging
import logging.handlers
import sys


def setup_logger(log_file: str) -> logging.Logger:
    logger = logging.getLogger("wifi_hopper")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    rotating = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_048_576, backupCount=3, encoding="utf-8"
    )
    rotating.setLevel(logging.DEBUG)
    rotating.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(rotating)
    return logger
