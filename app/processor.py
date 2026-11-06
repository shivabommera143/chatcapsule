from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from app.models import Conversation

STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "have",
    "will",
    "into",
    "your",
    "you",
    "are",
    "was",
    "but",
    "not",
    "they",
    "their",
    "about",
    "should",
    "would",
    "could",
    "what",
    "when",
    "where",
    "please",
    "make",
}
PATTERNS = {
    "requirements": (
        "i need",
        "i want",
        "requirement",
        "must",
        "should",
        "do not",
        "don't",
        "avoid",
        "make sure",
    ),
    "decisions": (
        "we decided",
        "let's use",
        "we'll use",
        "chosen",
        "final decision",
        "we agreed",
        "go with",
    ),
    "constraints": (
        "must",
        "cannot",
        "can't",
        "don't",
        "without",
        "only",
        "limited to",
        "deadline",
        "budget",
    ),
    "completed_work": (
        "implemented",
        "completed",
        "finished",
        "done",
        "created",
        "added",
        "fixed",
    ),
    "next_steps": ("next step", "next steps", "todo", "to do", "follow up"),
}


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    return [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", compact) if len(s.strip()) > 3
    ]


def _dedupe(items: list[str], limit: int | None = None) -> list[str]:
    result, normalized_items, seen = [], [], set()
    for item in items:
        normalized = re.sub(r"\W+", " ", item.lower()).strip()
        if normalized in seen:
            continue
        duplicate = False
        for previous in normalized_items:
            matcher = SequenceMatcher(None, normalized, previous)
            if matcher.quick_ratio() > 0.82 and matcher.ratio() > 0.82:
                duplicate = True
                break
        if not duplicate:
            result.append(item)
            normalized_items.append(normalized)
            seen.add(normalized)
            if limit is not None and len(result) >= limit:
                break
    return result


class ContextProcessor:
    def process(self, conversation: Conversation) -> dict:
        groups = {key: [] for key in PATTERNS}
        questions, code_blocks, links, facts = [], [], [], []
        for message in conversation.messages:
            text = message.content
            for language, code in re.findall(
                r"```([^\n`]*)\n(.*?)```", text, re.DOTALL
            ):
                code_blocks.append(
                    {
                        "language": language.strip() or "text",
                        "code": code.strip(),
                        "context": text[:160],
                    }
                )
            links.extend(re.findall(r"https?://[^\s)\]>]+", text))
            for sentence in _sentences(text):
                lower = sentence.lower()
                if message.role == "user" and sentence.endswith("?"):
                    questions.append(sentence)
                for name, phrases in PATTERNS.items():
                    if any(phrase in lower for phrase in phrases):
                        groups[name].append(sentence)
                if (
                    message.role in {"assistant", "system"}
                    and len(sentence) > 25
                    and not sentence.startswith("```")
                ):
                    facts.append(sentence)
        words = re.findall(
            r"[a-zA-Z][a-zA-Z-]{3,}",
            " ".join(m.content.lower() for m in conversation.messages),
        )
        topics = [
            word
            for word, count in Counter(
                w for w in words if w not in STOPWORDS
            ).most_common(8)
            if count > 1
        ]
        objective = (
            groups["requirements"][0]
            if groups["requirements"]
            else (
                conversation.messages[0].content[:280] if conversation.messages else ""
            )
        )
        return {
            "version": "1.0",
            "source": {"platform": "chatgpt", "url": conversation.source_url},
            "conversation": {
                "title": conversation.title,
                "message_count": len(conversation.messages),
            },
            "objective": objective,
            "requirements": _dedupe(groups["requirements"]),
            "preferences": [],
            "facts": _dedupe(facts, limit=8),
            "decisions": _dedupe(groups["decisions"]),
            "constraints": _dedupe(groups["constraints"]),
            "completed_work": _dedupe(groups["completed_work"]),
            "current_state": conversation.messages[-1].content[:500]
            if conversation.messages
            else "",
            "open_questions": _dedupe(questions),
            "next_steps": _dedupe(groups["next_steps"]),
            "code_blocks": code_blocks,
            "links": _dedupe(links),
            "topics": topics,
        }
