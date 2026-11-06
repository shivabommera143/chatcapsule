# ChatCapsule

**Turn a long ChatGPT conversation into portable context.**

[Open ChatCapsule](https://chatcapsule.onrender.com/) to paste a public shared-conversation link and generate a concise capsule you can reuse in another conversation or tool.

## What it does

- Extracts messages from public ChatGPT shared links, including legacy `chat.openai.com` links.
- Builds a structured context capsule with requirements, decisions, constraints, facts, open questions, next steps, code blocks, links, and detected topics.
- Preserves useful Markdown, links, and code when extracting conversation content.
- Lets you copy the capsule or download it as Markdown or JSON.
- Uses deterministic, rule-based processing; it does not call an AI API to summarize conversations.

## Run locally

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On macOS or Linux, activate the virtual environment with `source .venv/bin/activate` instead. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) and paste a public ChatGPT shared link.

Run the test suite with:

```bash
pytest
```

## API

`GET /health` returns `{"status":"ok"}` when the app is running.

`POST /api/capsule` accepts a JSON body containing a public ChatGPT share URL:

```json
{
  "url": "https://chatgpt.com/share/your-share-id"
}
```

The response contains the extracted `conversation`, structured `capsule`, rendered `markdown`, and `statistics` such as message counts and capsule length. Invalid or unsupported URLs return HTTP 400. Upstream access, availability, or parsing failures return HTTP 502; timeouts return HTTP 504.

## Privacy and compatibility

ChatCapsule does not require an account and does not persist conversation content in an application database. The server fetches the shared page to process it, so use only links you are comfortable sending to the service and its hosting provider. Shared links must be public and accessible without signing in.

The extractor uses HTTPX first. If the returned page cannot be parsed, it can use the host's `curl` executable as a temporary compatibility fallback; this fallback is optional. Fetches are limited to validated ChatGPT share URLs and responses are size-limited. ChatGPT may block automated requests, remove a shared page, or change its page format, so extraction is best-effort.

## Project structure

- `app/extractors/chatgpt.py` validates share URLs, fetches pages, and extracts conversation content.
- `app/extractors/turbo.py` decodes the embedded turbo-stream payload.
- `app/processor.py` applies transparent, rule-based heuristics to build structured context.
- `app/capsule.py` renders Markdown and calculates statistics.
- `app/templates/` and `app/static/` provide the web interface.
- `tests/` contains the API, extractor, and processor tests.
