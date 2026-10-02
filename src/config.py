"""Application settings from environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DOCX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class Settings:
    def __init__(self) -> None:
        self.deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.deepseek_base_url: str = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ).rstrip("/")
        self.deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.skills_dir: Path = self._resolve_skills_dir(
            os.getenv("SKILLS_DIR", "skills")
        )

    @staticmethod
    def _resolve_skills_dir(value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = ROOT / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
