from __future__ import annotations

from app.api.routes.health import router as health_router
from app.api.routes.templates import router as templates_router
from app.api.routes.webhook_altegio import router as webhook_router

all_routers = [health_router, templates_router, webhook_router]
