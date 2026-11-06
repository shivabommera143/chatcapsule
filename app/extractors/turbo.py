from __future__ import annotations

import json
import re

from app.models import Message


def conversation_payload_from_turbo(html: str) -> dict | None:
    stream = _js_stream(html)
    if not stream:
        return None
    try:
        root = _TurboDecoder(stream).get(0)
    except (ValueError, json.JSONDecodeError):
        return None

    def walk(value: object, depth: int = 0) -> dict | None:
        if depth > 16:
            return None
        if isinstance(value, dict):
            response = value.get("serverResponse")
            if isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, dict):
                    return data
            if isinstance(value.get("mapping"), dict):
                return value
            for child in value.values():
                found = walk(child, depth + 1)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child, depth + 1)
                if found:
                    return found
        return None

    return walk(root)


def messages_from_payload(payload: dict) -> list[Message]:
    nodes = payload.get("linear_conversation")
    if not isinstance(nodes, list):
        mapping, current = payload.get("mapping"), payload.get("current_node")
        nodes = []
        if isinstance(mapping, dict):
            if not isinstance(current, str) or current not in mapping:
                current = next(
                    (
                        key
                        for key, node in mapping.items()
                        if isinstance(node, dict) and not node.get("children")
                    ),
                    None,
                )
            chain, seen = [], set()
            while (
                isinstance(current, str) and current in mapping and current not in seen
            ):
                seen.add(current)
                node = mapping[current]
                chain.append(node)
                current = node.get("parent") if isinstance(node, dict) else None
            nodes = list(reversed(chain))

    result: list[Message] = []
    for node in nodes:
        message = node.get("message") if isinstance(node, dict) else None
        if not isinstance(message, dict):
            continue
        author = message.get("author")
        role = author.get("role") if isinstance(author, dict) else None
        content = message.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            parts = []
        channel, recipient = message.get("channel"), message.get("recipient", "all")
        if (
            role not in {"user", "assistant"}
            or (role == "assistant" and channel not in {None, "", "final"})
            or recipient not in {None, "", "all"}
        ):
            continue
        text = "\n\n".join(
            part
            if isinstance(part, str)
            else (
                "*[Image]*"
                if isinstance(part, dict)
                and part.get("content_type") == "image_asset_pointer"
                else str(part.get("text", ""))
                if isinstance(part, dict)
                else ""
            )
            for part in parts
        ).strip()
        text = re.sub(
            r"<CodeBlock\b[^>]*language=[\"']?([^\"' >]*)[^>]*>\s*(.*?)\s*</CodeBlock>",
            lambda match: f"```{match.group(1)}\n{match.group(2)}\n```",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(r"[\ue200-\ue2ff]|【\d+(?::\d+)?†[^】]*】", "", text).strip()
        if text:
            result.append(Message(role=role, content=text, index=len(result)))
    return result


def _js_stream(html: str) -> str | None:
    """Collect React Router streamController.enqueue JSON string arguments."""
    needle, cursor, pieces = "streamController.enqueue(", 0, []
    while (start := html.find(needle, cursor)) >= 0:
        quote = start + len(needle)
        while quote < len(html) and html[quote].isspace():
            quote += 1
        if quote >= len(html) or html[quote] != '"':
            cursor = quote + 1
            continue
        end = quote + 1
        while end < len(html):
            if html[end] == "\\":
                end += 2
                continue
            if html[end] == '"':
                break
            end += 1
        try:
            value = json.loads(html[quote : end + 1])
            if isinstance(value, str):
                pieces.append(value)
        except json.JSONDecodeError:
            pass
        cursor = end + 1
    return "".join(pieces) or None


class _TurboDecoder:
    """Small data-only decoder for React Router v7 turbo-stream value tables."""

    def __init__(self, stream: str):
        self.values: list[object] = []
        self.cache: dict[int, object] = {}
        self.active: set[int] = set()
        self.promises: dict[int, int] = {}
        for line in stream.splitlines():
            if not line:
                continue
            if not self.values:
                root = json.loads(line)
                if not isinstance(root, list):
                    raise ValueError("invalid turbo stream")
                self.values = root
                continue
            match = re.match(r"^[PE](\d+):(.*)$", line, re.DOTALL)
            if match:
                data = json.loads(match.group(2))
                ident = int(match.group(1))
                if isinstance(data, int):
                    self.promises[ident] = data
                elif isinstance(data, list):
                    self.promises[ident] = len(self.values)
                    self.values.extend(data)
        if not self.values:
            raise ValueError("empty turbo stream")

    def get(self, index: object) -> object:
        if not isinstance(index, int):
            return index
        if index < 0 or index >= len(self.values):
            return None
        if index in self.cache:
            return self.cache[index]
        if index in self.active:
            return None
        self.active.add(index)
        raw = self.values[index]
        if isinstance(raw, dict):
            result = {self._key(key): self.get(value) for key, value in raw.items()}
        elif isinstance(raw, list):
            result = self._array(raw)
        else:
            result = raw
        self.active.remove(index)
        self.cache[index] = result
        return result

    def _key(self, key: str) -> str:
        match = re.fullmatch(r"_(\d+)", key)
        if match:
            value = self.values[int(match.group(1))]
            if isinstance(value, (str, int, float, bool)):
                return str(value).lower() if isinstance(value, bool) else str(value)
        return key

    def _array(self, raw: list[object]) -> object:
        if not raw:
            return []
        if not isinstance(raw[0], str):
            return [self.get(item) for item in raw]
        tag = raw[0]
        if tag in {"D", "B", "U", "Y", "R", "E"}:
            return raw[1] if len(raw) > 1 else None
        if tag == "P" and len(raw) > 1 and isinstance(raw[1], int):
            return self.get(self.promises.get(raw[1], -1))
        if tag == "N" and len(raw) > 1:
            return (
                {self._key(str(key)): self.get(value) for key, value in raw[1].items()}
                if isinstance(raw[1], dict)
                else self.get(raw[1])
            )
        if tag == "M":
            return {
                str(self.get(raw[index])): self.get(raw[index + 1])
                for index in range(1, len(raw) - 1, 2)
            }
        if tag in {"S", "Z"}:
            return [self.get(item) for item in raw[1:]]
        return None
