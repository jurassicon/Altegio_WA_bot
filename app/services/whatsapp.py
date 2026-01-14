from __future__ import annotations

import httpx

from app.core.config import settings


class WhatsAppClient:
    def __init__(self) -> None:
        self.base = settings.WHATSAPP_API_BASE.rstrip("/")
        self.ver = settings.WHATSAPP_API_VERSION
        self.token = settings.WHATSAPP_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID

    def send_text(self, to_phone_e164: str, text: str) -> str:
        """
        Минимальный каркас отправки.
        Для продакшена обычно используют approved templates, а не raw text,
        если пишем клиенту вне 24-часового окна.
        """
        if not self.token or not self.phone_number_id:
            raise RuntimeError("WhatsApp credentials are not configured")

        url = f"{self.base}/{self.ver}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone_e164,
            "type": "text",
            "text": {"body": text},
        }

        with httpx.Client(timeout=20) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        # В ответе обычно приходит id сообщения.
        # Верни строку id, чтобы сохранить в БД.
        msg_id = ""
        try:
            msg_id = data["messages"][0]["id"]
        except Exception:
            msg_id = ""

        return msg_id
