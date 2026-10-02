"""Skill model, filesystem loader and thread-safe registry."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
CLASSIFIER_DESCRIPTION_LIMIT = 250


class SkillValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    caption: str
    body: str
    source_dir: str
    has_files: bool = False
    extra_files: tuple[str, ...] = field(default_factory=tuple)

    @property
    def classifier_description(self) -> str:
        text = self.description.strip()
        if len(text) <= CLASSIFIER_DESCRIPTION_LIMIT:
            return text
        return text[: CLASSIFIER_DESCRIPTION_LIMIT - 1].rstrip() + "…"

    def to_meta(self) -> dict[str, object]:
        return {
            "name": self.name,
            "caption": self.caption,
            "description": self.description,
            "has_files": self.has_files,
        }


def validate_skill_fields(*, name: str, description: str | None, body: str) -> None:
    if not name or not NAME_PATTERN.fullmatch(name) or len(name) > MAX_NAME_LENGTH:
        raise SkillValidationError(
            f"Invalid skill name '{name}': expected kebab-case, max {MAX_NAME_LENGTH} chars"
        )
    if description is None or not str(description).strip():
        raise SkillValidationError("description is required")
    if len(str(description).strip()) > MAX_DESCRIPTION_LENGTH:
        raise SkillValidationError(
            f"description exceeds {MAX_DESCRIPTION_LENGTH} characters"
        )
    if not body.strip():
        raise SkillValidationError("skill body must be non-empty")


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    text = raw.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise SkillValidationError("frontmatter must be a mapping")
    return meta, parts[2].strip()


def _collect_extra_files(skill_dir: Path) -> tuple[str, ...]:
    extras: list[str] = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file() and path.name != "SKILL.md":
            extras.append(path.relative_to(skill_dir).as_posix())
    return tuple(extras)


def load_skill_dir(skill_dir: Path) -> Skill:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise SkillValidationError(f"SKILL.md not found in {skill_dir}")

    meta, body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = str(meta.get("name") or skill_dir.name).strip()
    description = meta.get("description")
    if isinstance(description, str):
        description = description.strip()
    caption = str(meta.get("caption") or name).strip()

    validate_skill_fields(name=name, description=description, body=body)
    extras = _collect_extra_files(skill_dir)
    return Skill(
        name=name,
        description=str(description).strip(),
        caption=caption,
        body=body,
        source_dir=str(skill_dir),
        has_files=bool(extras),
        extra_files=extras,
    )


def load_skills(skills_root: Path) -> dict[str, Skill]:
    loaded: dict[str, Skill] = {}
    if not skills_root.exists():
        logger.warning("Skills directory does not exist: %s", skills_root)
        return loaded

    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            skill = load_skill_dir(entry)
        except SkillValidationError as exc:
            logger.warning("Skipping invalid skill in %s: %s", entry.name, exc)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping broken skill in %s: %s", entry.name, exc)
            continue
        loaded[skill.name] = skill
    return loaded


class SkillRegistry:
    """In-memory registry; reload() swaps snapshot under a lock."""

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self._lock = threading.RLock()
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        snapshot = load_skills(self._skills_dir)
        with self._lock:
            self._skills = snapshot

    def list_skills(self, query: str | None = None) -> list[Skill]:
        with self._lock:
            skills = list(self._skills.values())
        if query:
            needle = query.casefold()
            skills = [
                s
                for s in skills
                if needle in s.name.casefold() or needle in s.caption.casefold()
            ]
        return sorted(skills, key=lambda item: item.name)

    def get(self, name: str) -> Skill | None:
        with self._lock:
            return self._skills.get(name)
