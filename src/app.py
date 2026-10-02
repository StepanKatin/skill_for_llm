"""FastAPI app: skills registry + DeepSeek meeting assistant."""

from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache
from pathlib import Path

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
    export_docx: bool = True


class ProcessResponse(BaseModel):
    skill_name: str | None
    reason: str
    protocol_markdown: str | None
    docx_base64: str | None = None


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
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": 'attachment; filename="protocol.docx"'},
    )


@app.post("/assistant/process", response_model=ProcessResponse)
async def assistant_process(payload: ProcessRequest) -> ProcessResponse:
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

    docx_b64 = None
    if result.docx_bytes is not None:
        docx_b64 = base64.b64encode(result.docx_bytes).decode("ascii")

    return ProcessResponse(
        skill_name=result.skill_name,
        reason=result.reason,
        protocol_markdown=result.protocol_markdown,
        docx_base64=docx_b64,
    )
