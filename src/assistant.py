"""Classify → invoke skill → build protocol → optional docx."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.deepseek import DeepSeekClient
from src.protocol import parse_protocol, protocol_to_docx
from src.skills import Skill, SkillRegistry

CLASSIFIER_SYSTEM_PROMPT = """\
Ты классификатор скилов LLM-ассистента.
Тебе дан список скилов (name + description). Выбери ровно один подходящий скил
для запроса пользователя либо верни none.

Ответь строго JSON без markdown:
{"skill":"<name-or-none>","reason":"<кратко>"}
"""


@dataclass(slots=True)
class AssistantResult:
    skill_name: str | None
    reason: str
    protocol_markdown: str | None
    docx_bytes: bytes | None = None


async def process_meeting(
    user_text: str,
    *,
    registry: SkillRegistry,
    llm: DeepSeekClient,
    export_docx: bool = True,
) -> AssistantResult:
    skills = registry.list_skills()
    skill_name, reason = await _classify(user_text, skills, llm)

    if skill_name is None:
        return AssistantResult(None, reason, None, None)

    skill = registry.get(skill_name)
    if skill is None:
        return AssistantResult(
            None,
            f"classified skill '{skill_name}' is not in registry",
            None,
            None,
        )

    protocol_markdown = await llm.complete(
        system=_skill_prompt(skill),
        user=user_text,
    )
    docx_bytes = None
    if export_docx:
        docx_bytes = protocol_to_docx(parse_protocol(protocol_markdown))

    return AssistantResult(skill.name, reason, protocol_markdown, docx_bytes)


async def _classify(
    user_text: str,
    skills: list[Skill],
    llm: DeepSeekClient,
) -> tuple[str | None, str]:
    catalog = "\n".join(
        f"- name: {skill.name}\n  description: {skill.classifier_description}"
        for skill in skills
    )
    raw = await llm.complete(
        system=CLASSIFIER_SYSTEM_PROMPT,
        user=f"Скилы:\n{catalog or '- (пусто)'}\n\nЗапрос пользователя:\n{user_text}",
    )
    return parse_classifier_response(raw, {skill.name for skill in skills})


def parse_classifier_response(
    raw: str,
    known_skills: set[str],
) -> tuple[str | None, str]:
    payload = raw.strip()
    fenced = re.search(r"\{.*\}", payload, re.DOTALL)
    if fenced:
        payload = fenced.group(0)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None, f"unable to parse classifier response: {raw[:200]}"

    skill = data.get("skill")
    reason = str(data.get("reason") or "").strip() or "no reason provided"
    if skill is None or str(skill).strip().casefold() in {"", "none", "null"}:
        return None, reason
    name = str(skill).strip()
    if name not in known_skills:
        return None, f"unknown skill '{name}': {reason}"
    return name, reason


def _skill_prompt(skill: Skill) -> str:
    chunks = [skill.body]
    for relative in skill.extra_files:
        if not relative.startswith("references/") or not relative.endswith(".md"):
            continue
        try:
            content = open(f"{skill.source_dir}/{relative}", encoding="utf-8").read().strip()
        except OSError:
            continue
        if content:
            chunks.append(f"\n\n# File: {relative}\n{content}")
    return "\n".join(chunks).strip()
