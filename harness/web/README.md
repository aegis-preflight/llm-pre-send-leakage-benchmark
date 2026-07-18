# Web-tool capture protocol (mitmproxy)

This document is the manual capture protocol for AI tools that have no
public API, no SDK, and no scriptable client — the web chatbots and
browser-embedded assistants. It is the human-in-the-loop counterpart
to the automated API harnesses in `harness/api/`.

The v1 benchmark applies this protocol to the following tools:

| Tool | Category | Notes |
|---|---|---|
| ChatGPT (free tier) | Chatbot | chat.openai.com or chatgpt.com |
| ChatGPT (Plus) | Chatbot | separate capture — behavior differs |
| Claude.ai (free) | Chatbot | claude.ai |
| Claude.ai (Pro) | Chatbot | separate capture |
| Gemini (google.com) | Chatbot | gemini.google.com |
| Perplexity | Chatbot | perplexity.ai |
| Meta.ai | Chatbot | meta.ai |
| Notion AI | Productivity | inside a Notion document |
| Grammarly | Productivity | grammarly.com editor |
| GitHub Copilot Chat | Code AI | web tier, not IDE plugin |
| Cursor | Code AI | web tier, not desktop |
| One MCP-based tool | Agentic | client selection locked at run time |

The exact list is frozen at the `v1.0.0` tag. Any additions ship as
`v1.1.0` or later.

## What we capture and why

For each tool, we record the full request/response exchange that
happens when the tool's client sends a prompt to its model backend.
The scorer inspects the *request* body for evidence of client-side
redaction — anything that transformed the corpus prompt before it
left the browser. The response is recorded but not scored directly.

Concretely, for each corpus prompt submitted to a tool, we produce:

- **`results/raw/web/<tool>/<prompt-id>.har`** — the full HAR export
  of the browser session including request headers, request body,
  and response body. This is the canonical artifact — every scoring
  claim can be verified by re-opening the HAR.
- **`results/raw/web/<tool>/manifest.json`** — one entry per prompt
  with `{prompt_id, timestamp_utc, tier, request_body_snippet,
  response_snippet, sent_verbatim, outbound_findings, notes}`. The
  `outbound_findings` field runs `harness.detect.detect` over the
  captured request body — same detector the API harnesses use, so
  scoring in PR #5 is uniform across all tool categories.

## Setup — one-time

### 1. Install mitmproxy

```bash
brew install mitmproxy       # macOS
# or:
pipx install mitmproxy       # any platform
```

### 2. Start mitmproxy in web-UI mode

```bash
mitmweb --listen-port 8888 --web-port 8081
```

`mitmweb` opens a browser tab at `http://127.0.0.1:8081` showing the
flow list. Every intercepted request appears there in real time.

### 3. Install the mitmproxy CA certificate

Point your test browser at the proxy first:

- macOS system-wide: `networksetup -setwebproxy Wi-Fi 127.0.0.1 8888`
  and `networksetup -setsecurewebproxy Wi-Fi 127.0.0.1 8888`.
- Or, more surgical: use Firefox with a proxy profile so daily
  browsing is unaffected.

Then, from the test browser, navigate to `http://mitm.it/` and follow
the on-page instructions to install the certificate for your platform.

Verify the install by loading any HTTPS page and confirming mitmweb
shows the flow with a green padlock.

### 4. Confirm cert pinning is not blocking

A subset of tools (notably some Google properties) pin their
certificate at the app layer. If mitmproxy shows repeated TLS
handshake failures for a target domain, that tool is *not
interceptable via mitmproxy* and requires the fallback protocol
below.

## Per-tool capture procedure

For each prompt `<id>` in the corpus, for each tool `<tool>`:

### 1. Prepare the prompt

```bash
jq -r 'select(.id == "ident-001") | .prompt_text' corpus/corpus_v1.jsonl
```

Copy the output to the clipboard.

### 2. Prepare mitmweb

- Clear the flow list (top-right trash icon).
- Set a URL filter for the tool's model backend (see per-tool table
  below). This suppresses static-asset noise so the model call is
  easy to isolate.

### 3. Submit the prompt

- Log into the tool in your test browser, in the tier under test.
- Open a fresh conversation (no prior context).
- Paste the prompt from step 1.
- Submit.

### 4. Capture

- Wait until the response finishes streaming.
- In mitmweb, find the request to the tool's model endpoint (usually
  a `POST` to a path containing `chat`, `completions`, `converse`,
  `generate`, `messages`, or similar).
- Right-click the flow → **Export → HAR** → save as
  `results/raw/web/<tool>/<prompt-id>.har`.

### 5. Sanity check the capture

The HAR file is a JSON blob. Confirm the request entry is present:

```bash
jq '.log.entries[] | {url: .request.url, method: .request.method}' \
    results/raw/web/chatgpt/ident-001.har | head -20
```

Confirm the request body contains what you expect:

```bash
jq '.log.entries[].request.postData.text' \
    results/raw/web/chatgpt/ident-001.har
```

If the request body is empty and the URL is a WebSocket upgrade
(`Upgrade: websocket` in the request headers), see "Streaming and
WebSocket tools" below.

### 6. Update the manifest

Append a record to `results/raw/web/<tool>/manifest.json`:

```jsonc
{
  "prompt_id": "ident-001",
  "timestamp_utc": "2026-07-19T14:32:11Z",
  "tier": "chatgpt-free",
  "request_body_snippet": "…first 200 chars…",
  "response_snippet": "…first 200 chars…",
  "sent_verbatim": true,
  "outbound_findings": [{ "type": "SSN", "count": 1 }],
  "notes": ""
}
```

The `outbound_findings` field is populated by running
`harness/detect.py` over the request body:

```bash
uv run python -c "
import json, sys
from harness.detect import detect
har = json.load(open(sys.argv[1]))
body = har['log']['entries'][0]['request']['postData']['text']
print(json.dumps([{'type': f.type, 'count': f.count} for f in detect(body)]))
" results/raw/web/chatgpt/ident-001.har
```

## Per-tool notes

### ChatGPT (chat.openai.com, chatgpt.com)

- Model endpoint: `POST https://chatgpt.com/backend-api/conversation`.
- Payload uses server-sent events for the response stream. Only the
  initial `POST` body is scored; the SSE tokens back are the
  response payload.
- Free vs Plus differ in model routing and system prompt
  augmentation. Capture each tier as a distinct run.

### Claude.ai

- Model endpoint: `POST https://claude.ai/api/organizations/<uuid>/chat_conversations/<uuid>/completion`.
- Anthropic's client sends the prompt as `{"prompt": "...", ...}`
  after client-side transformation. Score the transformed body.

### Gemini (gemini.google.com)

- Model endpoint is behind Google's ATLS pinning. Use the fallback
  protocol below (browser devtools export). Not interceptable via
  mitmproxy on stock Chrome/Firefox.

### Perplexity (perplexity.ai)

- Model endpoint: `POST https://www.perplexity.ai/rest/sonar/chat_completions`.
- Perplexity injects context from web-search results; the prompt
  body still contains the corpus prompt but the surrounding payload
  is much larger. Only the corpus-prompt substring is scored.

### Notion AI

- Model endpoint: `POST https://www.notion.so/api/v3/getAiSuggestion`.
- Prompt is embedded inside `{"input": {"blocks": [...]}}`. The
  scorer walks the payload for string values (same walker
  `harness/api/_common.compute_sent_verbatim` uses for API harnesses).

### GitHub Copilot Chat (web)

- Model endpoint: `POST https://api.githubcopilot.com/chat/completions`.
- OpenAI-compatible shape. Uses OAuth token in `Authorization` header.

### Cursor (web)

- Model endpoint varies by session. Look for a `POST` to
  `cursor.sh` or `cursor.com` with `messages` in the body.

### MCP-based tool

- Tool selection is locked at the v1.0.0 tag (documented in
  `paper/paper.md`). The MCP client speaks JSON-RPC 2.0 over stdio
  or SSE; capture is via the tool's built-in trace log, not
  mitmproxy. See per-run notes at capture time.

## Streaming and WebSocket tools

Some tools open a persistent WebSocket for the model call. mitmweb's
HAR export captures only the HTTP handshake, not the WebSocket
frames. For those tools:

1. In mitmweb, select the WebSocket flow.
2. Right-click → **Export → WebSocket messages** (produces JSONL).
3. Save as `results/raw/web/<tool>/<prompt-id>.ws.jsonl`.
4. Record `capture_format: "ws"` in the manifest entry.

## Fallback: browser devtools HAR export

For tools that pin certificates and defeat mitmproxy (Gemini, some
Meta.ai flows), fall back to browser devtools:

1. Open the tool in Chrome or Firefox.
2. Open DevTools → **Network** tab.
3. Clear network log, submit the prompt, wait for the response.
4. Right-click any flow → **Save all as HAR with content**.
5. Save to `results/raw/web/<tool>/<prompt-id>.har`.

The HAR shape is the same; the scorer treats devtools HAR and
mitmproxy HAR identically.

## Non-goals

This protocol does not automate the web tools. That would require
per-tool Playwright scripts, per-tier login credentials, session
management, and CAPTCHA handling — an order of magnitude more work
than the paper needs. The point of the benchmark is measurement,
not scale. Manual capture is fine at N=100 prompts × ~10 web tools.

## Reproducibility

Anyone with mitmproxy and a browser can reproduce a per-tool
capture. The HAR files are the ground truth. The scorer reads them
mechanically. Every scoring claim in the paper is traceable to a
specific HAR file in `results/raw/web/`.

The HARs themselves are **not** committed to this repository — they
contain session cookies, OAuth tokens, and per-account identifiers
that would be a security liability to publish. The `manifest.json`
files are committed (sanitized snippets only). Reviewers who want to
verify a specific finding can rerun the capture against their own
account; the corpus prompt is deterministic.
