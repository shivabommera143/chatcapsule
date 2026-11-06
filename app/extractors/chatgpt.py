from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import shutil
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.extractors.base import ConversationExtractor
from app.extractors.turbo import conversation_payload_from_turbo, messages_from_payload
from app.models import Conversation, Message

ALLOWED_HOSTS = {"chatgpt.com", "chat.openai.com"}
MAX_RESPONSE_BYTES = 5_000_000
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
}


class ExtractionError(ValueError):
    pass


class InvalidShareURL(ExtractionError):
    pass


class ExtractionTimeoutError(ExtractionError):
    pass


class UpstreamBlockedError(ExtractionError):
    pass


class UpstreamUnavailableError(ExtractionError):
    pass


class ConversationParseError(ExtractionError):
    pass


def validate_share_url(value: str) -> str:
    try:
        parsed = urlparse(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise InvalidShareURL(
            "Unsupported conversation URL. Paste a valid ChatGPT shared link."
        ) from exc

    host = (parsed.hostname or "").lower().rstrip(".")
    share_path = re.fullmatch(r"/share/([A-Za-z0-9][A-Za-z0-9_-]{0,127})", parsed.path)
    if (
        parsed.scheme != "https"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or host not in ALLOWED_HOSTS
        or share_path is None
    ):
        raise InvalidShareURL(
            "Unsupported conversation URL. Paste a valid ChatGPT shared link."
        )
    return parsed.geturl()


def _markdown_from_node(node: Tag) -> str:
    for code in node.select("pre code"):
        language = ""
        for cls in code.get("class", []):
            if cls.startswith("language-"):
                language = cls.removeprefix("language-")
        code.replace_with(
            "\n```"
            + language
            + "\n"
            + code.get_text("", strip=False).strip()
            + "\n```\n"
        )
    for link in node.select("a[href]"):
        label, href = link.get_text(" ", strip=True), link["href"]
        link.replace_with(f"[{label}]({href})" if label else href)
    for heading in node.select("h1,h2,h3,h4"):
        level = int(heading.name[1])
        heading.replace_with(
            "\n" + "#" * level + " " + heading.get_text(" ", strip=True) + "\n"
        )
    for item in node.select("li"):
        item.insert_before("\n- ")
    text = node.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class ChatGPTExtractor(ConversationExtractor):
    """Best-effort parser; selectors are deliberately isolated here."""

    async def extract(self, url: str) -> Conversation:
        try:
            async with asyncio.timeout(30):
                return await self._extract(url)
        except TimeoutError as exc:
            raise ExtractionTimeoutError(
                "Timed out while fetching the shared conversation. Please try again."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExtractionTimeoutError(
                "Timed out while fetching the shared conversation. Please try again."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise self._http_error(exc.response.status_code) from exc
        except httpx.RequestError as exc:
            raise UpstreamUnavailableError(
                "Could not connect to the ChatGPT shared page. Check the link and try again."
            ) from exc

    async def _extract(self, url: str) -> Conversation:
        safe_url = validate_share_url(url)
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _ in range(4):
                await self._assert_public_host(safe_url)
                async with client.stream(
                    "GET", safe_url, headers=REQUEST_HEADERS
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise UpstreamUnavailableError(
                                "The shared page returned an invalid redirect."
                            )
                        safe_url = validate_share_url(
                            str(httpx.URL(safe_url).join(location))
                        )
                        continue
                    if response.is_error:
                        raise self._http_error(response.status_code)
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise UpstreamUnavailableError(
                                "The shared conversation page is too large to process."
                            )
                        chunks.append(chunk)
                    html = b"".join(chunks).decode("utf-8", errors="replace")
                    try:
                        return self.parse_html(html, safe_url)
                    except ConversationParseError:
                        fallback_html = await self._fetch_browser_compatible(safe_url)
                        if fallback_html is None:
                            raise
                        return self.parse_html(fallback_html, safe_url)
            raise UpstreamUnavailableError("The shared page redirected too many times.")

    @staticmethod
    def _http_error(status_code: int) -> ExtractionError:
        if status_code in {401, 403, 429}:
            return UpstreamBlockedError(
                "ChatGPT is blocking automated access to this shared page. Try again later."
            )
        if status_code in {404, 410}:
            return UpstreamUnavailableError(
                "The shared conversation was not found or is no longer available."
            )
        return UpstreamUnavailableError(
            f"ChatGPT could not provide the shared page (HTTP {status_code})."
        )

    async def _fetch_browser_compatible(self, url: str) -> str | None:
        """Temporary curl fallback for shared pages with bot-specific HTTPX HTML."""
        curl = shutil.which("curl") or shutil.which("curl.exe")
        if not curl:
            return None
        try:
            process = await asyncio.create_subprocess_exec(
                curl,
                "--silent",
                "--show-error",
                "--max-time",
                "20",
                "--max-filesize",
                str(MAX_RESPONSE_BYTES),
                "--user-agent",
                REQUEST_HEADERS["User-Agent"],
                "--write-out",
                "\n%{http_code}",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise UpstreamUnavailableError(
                "The temporary curl fallback could not be started."
            ) from exc
        communication = asyncio.create_task(process.communicate())
        try:
            stdout, _ = await asyncio.wait_for(
                asyncio.shield(communication), timeout=22
            )
        except TimeoutError as exc:
            await self._stop_subprocess(process, communication)
            raise ExtractionTimeoutError(
                "Timed out while fetching the shared conversation. Please try again."
            ) from exc
        except asyncio.CancelledError:
            await self._stop_subprocess(process, communication)
            raise

        body, separator, status_text = stdout.rpartition(b"\n")
        if not separator or not status_text.isdigit():
            if process.returncode == 28:
                raise ExtractionTimeoutError(
                    "Timed out while fetching the shared conversation. Please try again."
                )
            raise UpstreamUnavailableError(
                "Could not download the ChatGPT shared page. Please try again."
            )
        status_code = int(status_text)
        if status_code >= 400:
            raise self._http_error(status_code)
        if process.returncode != 0:
            if process.returncode == 28:
                raise ExtractionTimeoutError(
                    "Timed out while fetching the shared conversation. Please try again."
                )
            raise UpstreamUnavailableError(
                "Could not download the ChatGPT shared page. Please try again."
            )
        if len(body) > MAX_RESPONSE_BYTES:
            raise UpstreamUnavailableError(
                "The shared conversation page is too large to process."
            )
        return body.decode("utf-8", errors="replace")

    @staticmethod
    async def _stop_subprocess(
        process: asyncio.subprocess.Process,
        communication: asyncio.Task[tuple[bytes, bytes]],
    ) -> None:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        if not communication.done():
            await communication

    async def _assert_public_host(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        try:
            records = await asyncio.get_running_loop().getaddrinfo(
                host, 443, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise UpstreamUnavailableError(
                "Unable to resolve the ChatGPT shared-page host."
            ) from exc
        for record in records:
            address = ipaddress.ip_address(record[4][0])
            if not address.is_global:
                raise UpstreamUnavailableError(
                    "The ChatGPT shared-page host resolved to a non-public address."
                )

    def parse_html(self, html: str, source_url: str) -> Conversation:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else None
        title_lower = (title or "").lower()
        if soup.select_one(
            "#challenge-form, #cf-challenge-running, input[name='cf-turnstile-response']"
        ) or any(
            marker in title_lower
            for marker in ("just a moment", "access denied", "verify you are human")
        ):
            raise UpstreamBlockedError(
                "ChatGPT is showing an access challenge for this shared page. Try again later."
            )
        title_node = soup.select_one("[data-testid='conversation-title'], h1")
        if title_node:
            title = title_node.get_text(" ", strip=True)
        messages: list[Message] = []
        selectors = "[data-message-author-role], [data-role], article[data-message-id]"
        for node in soup.select(selectors):
            raw_role = (
                node.get("data-message-author-role")
                or node.get("data-role")
                or "unknown"
            ).lower()
            role = (
                raw_role if raw_role in {"user", "assistant", "system"} else "unknown"
            )
            content = _markdown_from_node(node)
            if content and not any(
                m.content == content and m.role == role for m in messages
            ):
                messages.append(
                    Message(role=role, content=content, index=len(messages))
                )
        if not messages:
            payload = conversation_payload_from_turbo(html)
            if payload:
                title = str(payload.get("title") or title or "").strip() or None
                messages = messages_from_payload(payload)
        if not messages:
            for script in soup.select("script[type='application/json']"):
                try:
                    data = json.loads(script.string or "{}")
                except json.JSONDecodeError:
                    continue
                for role, content in self._walk_messages(data):
                    messages.append(
                        Message(role=role, content=content, index=len(messages))
                    )
        if not messages:
            raise ConversationParseError(
                "The shared page loaded, but no conversation messages could be parsed. "
                "ChatGPT may have changed its page format."
            )
        return Conversation(title=title, source_url=source_url, messages=messages)

    def _walk_messages(self, value: object):
        if isinstance(value, dict):
            author, content = value.get("author"), value.get("content")
            if isinstance(author, dict) and isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    role = author.get("role", "unknown")
                    text = "\n".join(
                        str(part) for part in parts if isinstance(part, str)
                    ).strip()
                    if role in {"user", "assistant", "system"} and text:
                        yield role, text
            for child in value.values():
                yield from self._walk_messages(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk_messages(child)
