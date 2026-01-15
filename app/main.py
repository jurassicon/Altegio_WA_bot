from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import all_routers
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(title=settings.APP_NAME)

for r in all_routers:
    app.include_router(r)
