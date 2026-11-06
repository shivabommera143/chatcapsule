import asyncio
from pathlib import Path

import pytest

from app.extractors.chatgpt import (
    ChatGPTExtractor,
    ExtractionError,
    ExtractionTimeoutError,
    UpstreamBlockedError,
    validate_share_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_url():
    assert validate_share_url("https://chatgpt.com/share/abc").startswith(
        "https://chatgpt.com"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://chatgpt.com/share/a",
        "https://example.com/share/a",
        "https://chatgpt.com:444/share/a",
        "https://127.0.0.1/share/a",
        "https://chatgpt.com/share/",
        "https://chatgpt.com/share/a/extra",
        "https://chatgpt.com/share/a/",
        "https://chatgpt.com/share/a%2Fb",
        "https://chatgpt.com/share/a@b",
        "https://user@chatgpt.com/share/a",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(ExtractionError):
        validate_share_url(url)


def test_parse_fixture():
    html = (FIXTURES / "sample.html").read_text(encoding="utf-8")
    conversation = ChatGPTExtractor().parse_html(html, "https://chatgpt.com/share/a")
    assert conversation.title == "Parser project"
    assert len(conversation.messages) == 3
    assert "```python" in conversation.messages[1].content
    assert "https://example.com" in conversation.messages[0].content


def test_parse_current_turbo_stream_fixture():
    html = (FIXTURES / "turbo_stream.html").read_text(encoding="utf-8")

    conversation = ChatGPTExtractor().parse_html(html, "https://chatgpt.com/share/a")

    assert conversation.title == "Turbo stream fixture"
    assert [message.content for message in conversation.messages] == [
        "Hello from the turbo stream.",
        "A response from the turbo stream.",
    ]


def test_turbo_stream_parts_null_fixture_skips_empty_message():
    html = (FIXTURES / "turbo_parts_null.html").read_text(encoding="utf-8")

    conversation = ChatGPTExtractor().parse_html(html, "https://chatgpt.com/share/a")

    assert conversation.title == "Null parts fixture"
    assert [message.content for message in conversation.messages] == [
        "This message should remain."
    ]


def test_access_challenge_is_reported_as_upstream_block():
    with pytest.raises(UpstreamBlockedError, match="access challenge"):
        ChatGPTExtractor().parse_html(
            "<html><title>Just a moment...</title></html>",
            "https://chatgpt.com/share/a",
        )


def test_curl_subprocess_is_terminated_on_cancellation(monkeypatch):
    class FakeProcess:
        returncode = None

        def __init__(self):
            self.started = asyncio.Event()
            self.finished = asyncio.Event()
            self.terminated = False

        async def communicate(self):
            self.started.set()
            await self.finished.wait()
            return b"", b""

        def terminate(self):
            self.terminated = True
            self.returncode = -15
            self.finished.set()

        async def wait(self):
            return self.returncode

    async def run_test():
        process = FakeProcess()

        async def create_subprocess(*args, **kwargs):
            return process

        monkeypatch.setattr("app.extractors.chatgpt.shutil.which", lambda _: "curl")
        monkeypatch.setattr(
            "app.extractors.chatgpt.asyncio.create_subprocess_exec",
            create_subprocess,
        )

        request = asyncio.create_task(
            ChatGPTExtractor()._fetch_browser_compatible("https://chatgpt.com/share/a")
        )
        await process.started.wait()
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert process.terminated

    asyncio.run(run_test())


def test_curl_timeout_is_reported(monkeypatch):
    class FakeProcess:
        returncode = None

        async def communicate(self):
            return b"", b""

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return self.returncode

    async def run_test():
        process = FakeProcess()

        async def create_subprocess(*args, **kwargs):
            return process

        async def wait_for(awaitable, timeout):
            if asyncio.isfuture(awaitable):
                raise TimeoutError
            return await awaitable

        monkeypatch.setattr("app.extractors.chatgpt.shutil.which", lambda _: "curl")
        monkeypatch.setattr(
            "app.extractors.chatgpt.asyncio.create_subprocess_exec",
            create_subprocess,
        )
        monkeypatch.setattr("app.extractors.chatgpt.asyncio.wait_for", wait_for)

        with pytest.raises(ExtractionTimeoutError):
            await ChatGPTExtractor()._fetch_browser_compatible(
                "https://chatgpt.com/share/a"
            )

    asyncio.run(run_test())
