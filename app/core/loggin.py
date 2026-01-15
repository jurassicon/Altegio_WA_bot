from __future__ import annotations

import logging
from pythonjsonlogger import jsonlogger

from app.core.config import settings


def setup_logging() -> None:
    logger = logging.getLogger()
    logger.setLevel(settings.LOG_LEVEL)

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d"
    )
    handler.setFormatter(formatter)

    logger.handlers = [handler]
