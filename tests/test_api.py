from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.extractors.chatgpt import (
    ChatGPTExtractor,
    ConversationParseError,
    ExtractionTimeoutError,
    UpstreamBlockedError,
    UpstreamUnavailableError,
)
from app.main import app

client = TestClient(app)


def test_home_and_health():
    assert client.get("/").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


def test_invalid_api_url():
    response = client.post("/api/capsule", json={"url": "https://example.com/share/a"})
    assert response.status_code == 400
    assert "valid ChatGPT shared link" in response.json()["detail"]


def test_successful_api_response(monkeypatch):
    html = (Path(__file__).parent / "fixtures" / "sample.html").read_text(
        encoding="utf-8"
    )
    conversation = ChatGPTExtractor().parse_html(
        html, "https://chatgpt.com/share/example"
    )

    async def return_conversation(self, url):
        return conversation

    monkeypatch.setattr("app.main.ChatGPTExtractor.extract", return_conversation)
    response = client.post(
        "/api/capsule",
        json={"url": "https://chatgpt.com/share/example"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["conversation"]["title"] == "Parser project"
    assert data["capsule"]["conversation"]["message_count"] == 3
    assert data["markdown"].startswith("# AI CONTEXT CAPSULE")
    assert data["statistics"]["message_count"] == 3


@pytest.mark.parametrize(
    ("error", "status_code", "message"),
    [
        (
            ExtractionTimeoutError("The upstream request timed out."),
            504,
            "timed out",
        ),
        (
            UpstreamBlockedError("ChatGPT is blocking access."),
            502,
            "blocking",
        ),
        (
            UpstreamUnavailableError("The conversation is unavailable."),
            502,
            "unavailable",
        ),
        (
            ConversationParseError("No conversation messages could be parsed."),
            502,
            "parsed",
        ),
    ],
)
def test_upstream_errors_are_reported(monkeypatch, error, status_code, message):
    async def fail_extract(self, url):
        raise error

    monkeypatch.setattr("app.main.ChatGPTExtractor.extract", fail_extract)
    response = client.post(
        "/api/capsule", json={"url": "https://chatgpt.com/share/example"}
    )

    assert response.status_code == status_code
    assert message in response.json()["detail"].lower()
