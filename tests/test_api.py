"""API smoke tests without DeepSeek calls."""

from fastapi.testclient import TestClient

from src.app import app, get_llm, get_registry


def _client() -> TestClient:
    get_registry.cache_clear()
    get_llm.cache_clear()
    return TestClient(app)


def test_list_skills() -> None:
    response = _client().get("/skills")
    assert response.status_code == 200
    assert any(item["name"] == "meeting-minutes" for item in response.json())


def test_export_docx(sample_protocol: str) -> None:
    response = _client().post("/export/docx", json={"protocol_markdown": sample_protocol})
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


def test_process_requires_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    get_registry.cache_clear()
    get_llm.cache_clear()
    response = TestClient(app).post(
        "/assistant/process",
        json={"text": "Сделай протокол встречи"},
    )
    assert response.status_code == 503
