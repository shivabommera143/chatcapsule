from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.capsule import render_markdown, statistics
from app.extractors.chatgpt import (
    ChatGPTExtractor,
    ConversationParseError,
    ExtractionError,
    ExtractionTimeoutError,
    InvalidShareURL,
    UpstreamBlockedError,
    UpstreamUnavailableError,
)
from app.models import CapsuleRequest
from app.processor import ContextProcessor

app = FastAPI(title="ChatCapsule")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/capsule")
async def create_capsule(payload: CapsuleRequest):
    try:
        conversation = await ChatGPTExtractor().extract(payload.url)
        capsule = ContextProcessor().process(conversation)
        markdown = render_markdown(capsule)
        return {
            "conversation": conversation.model_dump(),
            "capsule": capsule,
            "markdown": markdown,
            "statistics": statistics(conversation, markdown),
        }
    except InvalidShareURL as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExtractionTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except UpstreamBlockedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (UpstreamUnavailableError, ConversationParseError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
