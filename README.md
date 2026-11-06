# ChatCapsule

ChatCapsule turns a ChatGPT shared-conversation link into a compact Markdown and JSON context capsule. It uses deterministic heuristics only—no AI APIs, accounts, database, analytics, or permanent storage.

## Features

- Safe allowlisted fetching of ChatGPT share URLs
- Best-effort HTML extractor with Markdown/code/link preservation and a separate turbo-stream decoder
- Rule-based requirements, decisions, constraints, questions, code and link extraction
- Copy plus Markdown and JSON downloads

## Fetching and compatibility

The extractor first requests the public share page with HTTPX. As a temporary compatibility fallback, if the returned HTML cannot be parsed, it uses the `curl` executable available on the host (`curl.exe` on Windows). This fallback is optional, is limited to the validated ChatGPT share URL, and has request and response-size limits. Install curl if your environment does not provide it; without curl, the app still works whenever HTTPX receives a parseable page. The fallback is OS-dependent and may be replaced with a supported browser-compatible fetch strategy in a future version.

Upstream timeouts return HTTP 504. Access blocks, unavailable pages, and page-format parsing failures return distinct messages with HTTP 502; malformed or unsupported share URLs return HTTP 400.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`, paste a `https://chatgpt.com/share/...` or legacy `https://chat.openai.com/share/...` URL, and generate a capsule. Run tests with `pytest`.

## API

`GET /health` returns `{"status":"ok"}`. `POST /api/capsule` accepts `{"url":"https://chatgpt.com/share/..."}` and returns normalized conversation data, JSON capsule, Markdown and statistics.

## Architecture and privacy

`app/extractors/chatgpt.py` owns fetching, URL validation, and HTML parsing. `app/extractors/turbo.py` decodes the page's embedded turbo-stream payload. `processor.py` uses transparent rule-based heuristics; `capsule.py` renders output. Requests are processed only in memory and content is not logged or stored by the application.

## Limitations and future work

ChatGPT shared-page HTML can change over time. The extractor and turbo-stream decoder are isolated from the rest of the application and may require updates if the platform changes its page structure. The curl fallback is temporary and host-dependent. The MVP deliberately omits accounts, databases, browser extensions, cloud deployment and semantic AI summarization. Additional providers can be introduced by implementing another extractor.
