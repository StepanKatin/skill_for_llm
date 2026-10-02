"""Test helpers."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_PROTOCOL = """# Протокол встречи

## Метаданные
- Дата: 18.03.2026
- Участники: Анна, Борис

## Обсуждение
Обсудили этапы проекта и контракт API.

## Решения
1. Не двигать дату релиза.

## Задачи
| Задача | Ответственный | Срок |
|--------|---------------|------|
| Подготовить OpenAPI | Борис | 20.03 |
| Обновить Jira | Анна | Не указан |
"""

PROTOCOL_WITH_GAPS = """# Протокол встречи

## Метаданные
- Дата: Не указан
- Участники: Не указан

## Обсуждение
Нет данных

## Решения
Нет данных

## Задачи
| Задача | Ответственный | Срок |
|--------|---------------|------|
| Разослать итоги | Не указан | Не указан |
"""


@pytest.fixture
def skills_dir() -> Path:
    return ROOT / "skills"


@pytest.fixture
def sample_protocol() -> str:
    return SAMPLE_PROTOCOL


@pytest.fixture
def protocol_with_gaps() -> str:
    return PROTOCOL_WITH_GAPS
