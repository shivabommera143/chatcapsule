import hashlib

from app.extractors.chatgpt import ChatGPTExtractor
from app.models import Conversation, Message
from app.processor import ContextProcessor


def test_context_processing():
    with open("tests/fixtures/sample.html") as fixture:
        html = fixture.read()
    c = ChatGPTExtractor().parse_html(html, "https://chatgpt.com/share/a")
    x = ContextProcessor().process(c)
    assert sum("I need a parser" in item for item in x["requirements"]) == 1
    assert (
        x["decisions"]
        and x["constraints"]
        and x["open_questions"]
        and x["code_blocks"]
        and x["links"]
    )


def test_facts_are_limited_to_the_first_eight_unique_sentences():
    conversation = Conversation(
        source_url="https://chatgpt.com/share/a",
        messages=[
            Message(
                role="assistant",
                content=f"This is a distinct factual sentence {hashlib.sha256(str(i).encode()).hexdigest()}.",
                index=i,
            )
            for i in range(1000)
        ],
    )

    facts = ContextProcessor().process(conversation)["facts"]

    assert len(facts) == 8
    assert hashlib.sha256(b"0").hexdigest() in facts[0]
    assert hashlib.sha256(b"7").hexdigest() in facts[-1]
