from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import admin_auth
from app.db.models import MessageTemplate
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/admin/templates", tags=["templates"])


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


class TemplateIn(BaseModel):
    key: str
    language: str = "ru"
    text: str
    is_active: bool = True


class TemplateUpdate(BaseModel):
    text: str | None = None
    is_active: bool | None = None


@router.get("", dependencies=[Depends(admin_auth)])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[dict]:
    res = await db.execute(select(MessageTemplate).order_by(MessageTemplate.key, MessageTemplate.language))
    items = res.scalars().all()
    return [
        {
            "id": t.id,
            "key": t.key,
            "language": t.language,
            "is_active": t.is_active,
            "version": t.version,
            "updated_at": t.updated_at,
        }
        for t in items
    ]


@router.post("", dependencies=[Depends(admin_auth)])
async def create_template(payload: TemplateIn, db: AsyncSession = Depends(get_db)) -> dict:
    exists = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.key == payload.key, MessageTemplate.language == payload.language
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Template key+language already exists")

    t = MessageTemplate(
        key=payload.key,
        language=payload.language,
        text=payload.text,
        is_active=payload.is_active,
        version=1,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return {"id": t.id, "key": t.key, "language": t.language, "version": t.version}


@router.put("/{template_id}", dependencies=[Depends(admin_auth)])
async def update_template(template_id: int, payload: TemplateUpdate, db: AsyncSession = Depends(get_db)) -> dict:
    res = await db.execute(select(MessageTemplate).where(MessageTemplate.id == template_id))
    t = res.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")

    changed = False
    if payload.text is not None and payload.text != t.text:
        t.text = payload.text
        t.version += 1
        changed = True
    if payload.is_active is not None and payload.is_active != t.is_active:
        t.is_active = payload.is_active
        changed = True

    if changed:
        await db.commit()
        await db.refresh(t)

    return {"id": t.id, "key": t.key, "language": t.language, "is_active": t.is_active, "version": t.version}
