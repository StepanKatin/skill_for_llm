"""Thin DeepSeek chat client (OpenAI-compatible)."""

from __future__ import annotations

import logging

import httpx

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        cfg = settings or get_settings()
        self._api_key = (api_key if api_key is not None else cfg.deepseek_api_key).strip()
        self._base_url = (base_url or cfg.deepseek_base_url).rstrip("/")
        self._model = model or cfg.deepseek_model
        self._timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def complete(self, *, system: str, user: str) -> str:
        if not self.is_configured:
            raise DeepSeekError("DEEPSEEK_API_KEY is not configured")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("DeepSeek error: %s", response.text)
                raise DeepSeekError(
                    f"DeepSeek request failed with status {response.status_code}"
                ) from exc

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("Unexpected DeepSeek response shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek returned empty content")
        return content.strip()
