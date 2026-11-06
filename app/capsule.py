from __future__ import annotations


def render_markdown(capsule: dict) -> str:
    def section(name: str, items: list[str]) -> str:
        return (
            f"## {name}\n"
            + (
                "\n".join(f"- {x}" for x in items)
                if items
                else "- None identified deterministically."
            )
            + "\n"
        )

    source, convo = capsule["source"], capsule["conversation"]
    out = [
        "# AI CONTEXT CAPSULE",
        "",
        "## Source",
        f"Platform: {source['platform'].title()}",
        f"Original conversation: {source['url']}",
        "",
        "## Conversation Summary",
        f"Title: {convo.get('title') or 'Untitled'}",
        f"Messages: {convo['message_count']}",
        "",
        "## Primary Objective",
        capsule["objective"] or "Not identified deterministically.",
        "",
    ]
    for key, title in [
        ("requirements", "User Requirements"),
        ("preferences", "User Preferences"),
        ("facts", "Important Facts"),
        ("decisions", "Decisions Made"),
        ("constraints", "Constraints"),
        ("completed_work", "Work Completed"),
    ]:
        out.extend([section(title, capsule[key]), ""])
    out += [
        "## Current State",
        capsule["current_state"] or "Not identified.",
        "",
        section("Open Questions", capsule["open_questions"]),
        "",
        section("Next Steps", capsule["next_steps"]),
        "",
        "## Important Code",
    ]
    if capsule["code_blocks"]:
        for block in capsule["code_blocks"]:
            out.extend([f"```{block['language']}", block["code"], "```"])
    else:
        out.append("None identified.")
    out += [
        "",
        section("Important Links", capsule["links"]),
        "",
        "## Conversation Notes",
        "Topics detected: " + (", ".join(capsule.get("topics", [])) or "none") + ".",
    ]
    return "\n".join(out)


def statistics(conversation, markdown: str) -> dict:
    original = sum(len(m.content) for m in conversation.messages)
    generated = len(markdown)
    return {
        "message_count": len(conversation.messages),
        "user_messages": sum(m.role == "user" for m in conversation.messages),
        "assistant_messages": sum(m.role == "assistant" for m in conversation.messages),
        "original_length": original,
        "capsule_length": generated,
        "compression_ratio": round(original / generated, 2) if generated else 0,
    }
