from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import settings


def admin_auth(x_admin_token: str | None = Header(default=None)) -> None:
    if not x_admin_token or x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
