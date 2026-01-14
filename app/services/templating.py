from __future__ import annotations

from jinja2 import Environment, BaseLoader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MessageTemplate


_jinja = Environment(loader=BaseLoader(), autoescape=False)


def render_template(db: Session, key: str, language: str, context: dict) -> tuple[str, int]:
    """
    Returns (rendered_text, template_version).
    Шаблон хранится в БД как Jinja2-текст, например:
    "Привет, {{ client_name }}! Вы записаны на {{ date }} в {{ time }}."
    """
    t = db.execute(
        select(MessageTemplate).where(
            MessageTemplate.key == key,
            MessageTemplate.language == language,
            MessageTemplate.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if not t:
        raise RuntimeError(f"Template not found or inactive: {key}/{language}")

    tpl = _jinja.from_string(t.text)
    rendered = tpl.render(**context)
    return rendered, t.version
