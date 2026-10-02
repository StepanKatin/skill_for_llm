"""FastAPI app: skills registry + DeepSeek meeting assistant."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.assistant import process_meeting
from src.deepseek import DeepSeekClient, DeepSeekError
from src.protocol import ProtocolParseError, parse_protocol, protocol_to_docx
from src.skills import SkillRegistry

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DOCX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@lru_cache
def get_registry() -> SkillRegistry:
    skills_dir = Path(os.getenv("SKILLS_DIR", "skills"))
    if not skills_dir.is_absolute():
        skills_dir = ROOT / skills_dir
    return SkillRegistry(skills_dir)


@lru_cache
def get_llm() -> DeepSeekClient:
    return DeepSeekClient()


app = FastAPI(
    title="Meeting Skills Assistant",
    description="Заметки встречи → скилл → протокол → Word (DeepSeek)",
    version="1.0.0",
)


class ProcessRequest(BaseModel):
    text: str = Field(..., min_length=1)
    export_docx: bool = Field(
        default=True,
        description=(
            "true — вернуть готовый .docx файлом (скачивается в Swagger). "
            "false — вернуть JSON с skill_name / reason / protocol_markdown."
        ),
    )


class ProcessResponse(BaseModel):
    skill_name: str | None
    reason: str
    protocol_markdown: str | None


class ExportRequest(BaseModel):
    protocol_markdown: str = Field(..., min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/skills")
def list_skills(q: str | None = Query(default=None)) -> list[dict]:
    return [skill.to_meta() for skill in get_registry().list_skills(q)]


@app.post("/skills/reload")
def reload_skills() -> dict:
    registry = get_registry()
    registry.reload()
    skills = registry.list_skills()
    return {"reloaded": len(skills), "skills": [s.to_meta() for s in skills]}


@app.post("/export/docx")
def export_docx(payload: ExportRequest) -> Response:
    try:
        content = protocol_to_docx(parse_protocol(payload.protocol_markdown))
    except ProtocolParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="protocol.docx"'},
    )


@app.post(
    "/assistant/process",
    response_model=None,
    responses={
        200: {
            "description": (
                "При export_docx=true — файл .docx. "
                "При export_docx=false или если скилл не выбран — JSON."
            ),
            "content": {
                DOCX_MEDIA: {"schema": {"type": "string", "format": "binary"}},
                "application/json": {"schema": ProcessResponse.model_json_schema()},
            },
        }
    },
)
async def assistant_process(payload: ProcessRequest):
    llm = get_llm()
    if not llm.is_configured:
        raise HTTPException(
            status_code=503,
            detail="DeepSeek is not configured. Set DEEPSEEK_API_KEY.",
        )
    try:
        result = await process_meeting(
            payload.text,
            registry=get_registry(),
            llm=llm,
            export_docx=payload.export_docx,
        )
    except ProtocolParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Model returned protocol that failed parsing: {exc}",
        ) from exc
    except DeepSeekError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Основной UX: сразу скачать Word из этой же ручки.
    if payload.export_docx and result.docx_bytes is not None:
        reason = quote(result.reason[:300], safe="")
        return Response(
            content=result.docx_bytes,
            media_type=DOCX_MEDIA,
            headers={
                "Content-Disposition": 'attachment; filename="meeting.docx"',
                "X-Skill-Name": result.skill_name or "",
                "X-Skill-Reason": reason,
            },
        )

    return ProcessResponse(
        skill_name=result.skill_name,
        reason=result.reason,
        protocol_markdown=result.protocol_markdown,
    )
